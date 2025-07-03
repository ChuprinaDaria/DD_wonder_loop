from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InputMediaPhoto
from utils.TrustedUserUpdater import TrustedUserUpdater
from utils.messages import (
    get_moderation_rejected_message,
    get_moderation_approved_message,
)
from utils.keyboards import get_contact_seller_keyboard, render_stars
from typing import Optional
from utils.text_utils import clean_surrogates
import asyncio
import logging
from aiogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram import F
from aiogram.types import ForceReply
from datetime import datetime, timedelta
admin_router = Router()


class AdminUtils:
    def __init__(self, bot):
        self.bot = bot

    async def approve_lot(self, lot_id: int):
        print(f"\n🔎 [approve_lot] Починаємо обробку лота ID: {lot_id}")

        lot = await self.bot.db.get_lot(lot_id)
        print(f"📦 Лот з БД: {lot}")

        if not lot:
            print(f"❌ Лот {lot_id} не знайдено")
            return

        user_id = lot.get('user_id')
        print(f"👤 ID користувача з лота: {user_id}")

        if user_id is None:
            print(f"❌ У лота {lot.get('id')} відсутній user_id!")
            return

        user = await self.bot.db.get_user_by_internal_id(user_id)
        print(f"👥 Отриманий користувач: {user}")

        if not user:
            print(f"❌ Користувач з ID {user_id} не знайдений у базі!")
            all_users = await self.bot.db.get_all_users()
            print(f"🗂 Всі користувачі: {all_users}")
            return

        if str(user.get("trusted")).lower() == 'true':

            print("🔁 Trusted-юзер: лот уже опубліковано. Пропускаємо approve_lot.")
            return

        user_telegram_id = user.get('telegram_id')
        print(f"📲 Telegram ID користувача: {user_telegram_id}")

        if not user_telegram_id:
            print(f"❌ У користувача {user.get('id')} немає telegram_id")
            return
            
        if lot.get("status") == "active":
            print("📌 Лот уже активний — нічого не робимо.")
            return


        # Витягуємо зображення
        images = lot.get('images') or []
        print(f"🖼 Фото в лоті: {images}")

        if not images:
            print(f"❌ Немає фото в лоті! Публікацію скасовано.")
            return

        caption = f"🔁 {lot.get('generated_text', '')}"
        caption = clean_surrogates(caption) 
        print(f"📝 Згенерований текст: {caption}")

        try:
            # СПОЧАТКУ оновлюємо статус лота на 'active'
            await self.bot.db.update_lot_status(lot_id, 'active')
            print("🛠 Оновлено статус лота на 'active'")

            if len(images) == 1:
                print(f"📤 Надсилаємо одне фото...")

                # 1. Фото з описом
                photo_msg = await self.bot.send_photo(
                    chat_id=self.bot.config.CHANNEL_ID,
                    photo=images[0],
                    caption=caption,
                    parse_mode="Markdown"
                )
                print(f"✅ Фото надіслано. ID: {photo_msg.message_id}")
                await self.bot.db.set_lot_message_id(lot_id, photo_msg.message_id)
                await self.bot.db.add_lot_message(lot_id, photo_msg.message_id)

                # 2. Зірочки + кнопка
                stars = await render_stars(user_id, self.bot)
                contact_msg = await self.bot.send_message(
                    chat_id=self.bot.config.CHANNEL_ID,
                    text=f"{stars}",
                    reply_markup=get_contact_seller_keyboard(user_id=user_telegram_id)
                )
                print(f"✅ Додаткове повідомлення з кнопкою. ID: {contact_msg.message_id}")
                await self.bot.db.add_lot_message(lot_id, contact_msg.message_id)


            else:
                print(f"📤 Надсилаємо {len(images)} фото як медіа-групу...")

                media = [InputMediaPhoto(media=img) for img in images]
                media[0].caption = caption
                media[0].parse_mode = "Markdown"

                media_msgs = await self.bot.send_media_group(
                    chat_id=self.bot.config.CHANNEL_ID,
                    media=media
                )
                print(f"✅ Медіа-група надіслана. Кількість повідомлень: {len(media_msgs)}")

                # Зберігаємо ID першого повідомлення
                if media_msgs:
                    await self.bot.db.set_lot_message_id(lot_id, media_msgs[0].message_id)
                    for msg in media_msgs:
                        await self.bot.db.add_lot_message(lot_id, msg.message_id)

                await asyncio.sleep(2)  # трішки чекаємо

                try:
                            # ⬇️ Зірочки + кнопка продавця
                    stars = await render_stars(user_id, self.bot)
                    contact_msg = await self.bot.send_message(
                        chat_id=self.bot.config.CHANNEL_ID,
                        text=f"{stars}",
                        reply_markup=get_contact_seller_keyboard(user_id=user_telegram_id)
                    )
                    await self.bot.db.add_lot_message(lot_id, contact_msg.message_id)
                    print(f"✅ Надіслано зірочки з кнопкою продавця. ID: {contact_msg.message_id}")

                except Exception as e:
                    print(f"❌ Помилка при відправці кнопки для медіа-групи: {e}")
                    print(f"👤 user_telegram_id: {user_telegram_id}")
                    print(f"📢 CHANNEL_ID: {self.bot.config.CHANNEL_ID}")

                approved_text = get_moderation_approved_message()
                await self.bot.send_message(chat_id=user_telegram_id, text=approved_text)
                print("📨 Надіслано повідомлення про успішну модерацію")


        except Exception as e:
            print(f"❌ Помилка при публікації лота {lot.get('id', lot_id) if lot else lot_id}: {e}")
            # Якщо помилка, повертаємо статус назад
            await self.bot.db.update_lot_status(lot_id, 'pending')
            print(f"📸 images: {images}")
            print(f"🧾 generated_text: {caption}")
            print(f"👤 user: {user}")

    async def reject_lot(self, lot_id: int, reason: str = None):
        lot = await self.bot.db.get_lot(lot_id)
        if not lot:
            print(f"❌ Лот {lot_id} не знайдено для відхилення")
            return
        
        user = await self.bot.db.get_user_by_internal_id(lot['user_id'])

        text = get_moderation_rejected_message(reason)
        await self.bot.send_message(chat_id=user['telegram_id'], text=text)
        await self.bot.db.update_lot_status(lot_id, 'rejected')


# ✅ Обробники callback-кнопок

@admin_router.callback_query(F.data.startswith("mod_approve_"))
async def handle_mod_approve(callback: CallbackQuery):
    try:
        lot_id = int(callback.data.replace("mod_approve_", ""))
        await callback.bot.admin_utils.approve_lot(lot_id)
        
        # ВИПРАВЛЕНО: Перевіряємо чи є caption в повідомленні
        if callback.message.caption:
            await callback.message.edit_caption(
                caption="✅ Лот схвалено модератором.", 
                reply_markup=None
            )
        else:
            # Якщо немає caption, редагуємо текст
            await callback.message.edit_text(
                text="✅ Лот схвалено модератором.", 
                reply_markup=None
            )

        await callback.answer("Схвалено")
        
        # ВИПРАВЛЕНО: Видаляємо повідомлення через 2 секунди
        await asyncio.sleep(2)
        try:
            await callback.message.delete()
        except Exception as e:
            print(f"⚠️ Не вдалося видалити повідомлення: {e}")
            
    except Exception as e:
        await callback.answer(f"❌ Помилка: {e}", show_alert=True)


@admin_router.callback_query(F.data.startswith("mod_reject_"))
async def handle_mod_reject(callback: CallbackQuery, state: FSMContext):
    try:
        lot_id = int(callback.data.replace("mod_reject_", ""))
        await state.update_data(lot_id=lot_id)

        await callback.message.answer(
            "✍️ Напиши причину відмови (вона буде надіслана користувачу):",
            reply_markup=ForceReply()
        )

        await callback.answer()

    except Exception as e:
        await callback.answer(f"❌ Помилка: {e}", show_alert=True)

@admin_router.message(F.reply_to_message, F.reply_to_message.text.startswith("✍️ Напиши причину відмови"))
async def process_reject_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    lot_id = data.get("lot_id")
    reason = message.text.strip()

    # Відмічаємо лот як відхилений
    await message.bot.admin_utils.reject_lot(lot_id, "Відхилено модератором")

    # Отримуємо лот і user_id
    lot = await message.bot.db.get_lot(lot_id)
    user_id = lot["user_id"]

    # Отримуємо telegram_id за user_id
    telegram_id = await message.bot.db.get_telegram_id_by_user_id(user_id)

    # Надсилаємо повідомлення користувачу
    if telegram_id:
        try:
            await message.bot.send_message(
                chat_id=telegram_id,
                text=f"Ваш лот було відхилено модерацією.\n\nПричина: {reason} Можете спробувати створити новий лот, виправивши помилки."
            )
        except Exception as e:
            print(f"⚠️ Не вдалося надіслати повідомлення юзеру: {e}")
    else:
        print(f"⚠️ Не вдалося знайти telegram_id для user_id={user_id}")

    await message.reply("✅ Відхилено та повідомлено користувача.")
    await state.clear()


class AdminUserStates(StatesGroup):
    waiting_for_identifier = State()  # пошук по емейл/телефону
    waiting_for_warning_text = State()  # текст попередження



@admin_router.callback_query(F.data == "admin_users")
async def handle_user_management(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🔍 Введи @username або телефон користувача:")
    await state.set_state(AdminUserStates.waiting_for_identifier)
    await callback.answer()


@admin_router.message(AdminUserStates.waiting_for_identifier)
async def find_user(message: Message, state: FSMContext):
    text = message.text.strip()
    user = await message.bot.db.find_user_by_email_or_phone(text)

    if not user:
        await message.answer("❌ Користувача не знайдено.")
        await state.clear()
        return

    # Зберігаємо користувача в FSM
    await state.update_data(found_user=user)

    # Кнопки дій
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Додати в довірені", callback_data="admin_trust")],
        [InlineKeyboardButton(text="⚠️ Попередити", callback_data="admin_warn")],
        [InlineKeyboardButton(text="🚫 Заблокувати", callback_data="admin_ban_perm")],
        
        [InlineKeyboardButton(text="🔓 Розблокувати", callback_data="admin_unban")]
    ])


    info = (
        f"👤 Користувач знайдений:\n"
        f"ID: {user['id']}\n"
        f"Telegram ID: {user['telegram_id']}\n"
        f"📞 Телефон: {user['phone']}\n"
        f"📧 Email: {user['email']}\n"
        f"✅ Довірений: {'Так' if user['trusted'] else 'Ні'}"
    )

    await message.answer(info, reply_markup=kb)


@admin_router.callback_query(F.data == "admin_warn")
async def warn_user_start(callback: CallbackQuery, state: FSMContext):
    # Отримуємо дані знайденого користувача з FSM
    data = await state.get_data()
    found_user = data.get('found_user')
    
    if not found_user:
        await callback.message.answer("❌ Не вдалося знайти інформацію про користувача.")
        await callback.answer()
        return
    
    # Зберігаємо дані користувача для подальшого використання
    await state.update_data(
        warn_target_message=callback.message,
        target_user_id=found_user['id'],  # ID з бази даних
        target_telegram_id=found_user['telegram_id']  # Telegram ID для надсилання
    )
    
    await callback.message.answer("✍ Введи текст попередження для користувача:")
    await state.set_state(AdminUserStates.waiting_for_warning_text)
    await callback.answer()

@admin_router.message(AdminUserStates.waiting_for_warning_text)
async def send_warning(message: Message, state: FSMContext):
    # Отримуємо дані з FSM
    data = await state.get_data()
    found_user = data.get('found_user')
    target_telegram_id = data.get('target_telegram_id')
    
    # Перевірка на наявність даних
    if not found_user or not target_telegram_id:
        await message.answer("❌ Не вдалося знайти інформацію про користувача.")
        await state.clear()
        return
    
    try:
        # Надсилаємо попередження користувачу
        await message.bot.send_message(
            chat_id=target_telegram_id,
            text=f"⚠️ Попередження від адміна:\n\n{message.text}"
        )
        
        # Показуємо інформацію про користувача та успішне надсилання
        user_info = f"👤 {found_user.get('username', 'N/A')} (ID: {found_user['id']})"
        await message.answer(f"✅ Попередження надіслано користувачу:\n{user_info}")
        
    except Exception as e:
        logger.error(f"❌ Помилка при надсиланні попередження: {e}")
        await message.answer("❌ Не вдалося надіслати повідомлення користувачу.")
    
    # Очистити дані
    await state.clear()





logger = logging.getLogger(__name__)

@admin_router.callback_query(F.data == "admin_queue")
async def handle_queue(callback: CallbackQuery):
    logger.info("➡️ Адмін натиснув 'Черга' (admin_queue)")
    
    lots = await callback.bot.db.get_lots_by_status('pending')
    logger.info(f"🥟 Знайдено {len(lots)} лот(ів) у черзі")

    if not lots:
        await callback.answer("Немає лотів у черзі", show_alert=True)
        return

    # ВИПРАВЛЕНО: Не відповідаємо на callback одразу, щоб можна було видалити повідомлення
    await callback.message.answer(f"⏳ У черзі {len(lots)} лот(ів):")

    for lot in lots:
        user = await callback.bot.db.get_user_by_internal_id(lot['user_id'])
        telegram_id = user.get('telegram_id') if user else 'N/A'
        logger.info(f"👤 Обробляємо лот ID: {lot['id']}, користувач: {telegram_id}")

        images = lot.get('images') or []
        logger.debug(f"📸 Фото: {images}")

        generated_text = lot.get('generated_text', '')
        clean_text = clean_surrogates(generated_text or "🔍 Опис відсутній.")

        buttons = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Схвалити", callback_data=f"mod_approve_{lot['id']}"),
                InlineKeyboardButton(text="🚫 Відхилити", callback_data=f"mod_reject_{lot['id']}")
            ]
        ])

        try:
            if len(images) > 1:
                # Надсилаємо галерею
                media = [InputMediaPhoto(media=img) for img in images]
                media[0].caption = f"🔍 {clean_text}"
                media[0].parse_mode = "Markdown"

                await callback.bot.send_media_group(chat_id=callback.from_user.id, media=media)
                logger.info(f"📷 Надіслано {len(images)} фото як media_group")

                await callback.bot.send_message(
                    chat_id=callback.from_user.id,
                    text="⬆️ Фото вище\n\n📋 Обери дію:",
                    reply_markup=buttons
                )
                logger.info("📢 Відправлено повідомлення з кнопками після галереї")

            elif len(images) == 1:
                # Надсилаємо одне фото з описом
                await callback.bot.send_photo(
                    chat_id=callback.from_user.id,
                    photo=images[0],
                    caption=f"🔍 {clean_text}",
                    reply_markup=buttons,
                    parse_mode="Markdown"
                )
                logger.info("📸 Відправлено одне фото з caption")

            else:
                # Якщо фото немає
                await callback.bot.send_message(
                    chat_id=callback.from_user.id,
                    text=f"⚠️ Лот без фото\n\n🔍 {clean_text}",
                    reply_markup=buttons,
                    parse_mode="Markdown"
                )
                logger.warning("⚠️ Лот без фото")

        except Exception as e:
            logger.exception(f"❌ Помилка показу лота {lot['id']}: {e}")
            await callback.bot.send_message(
                chat_id=callback.from_user.id,
                text=f"❌ Не вдалося показати лот #{lot['id']} через помилку. Деталі в логах."
            )

    # ВИПРАВЛЕНО: Видаляємо вихідне повідомлення після показу всіх лотів
    try:
        await callback.message.delete()
        logger.info("🧹 Видалено вихідне повідомлення з чергою")
    except Exception as e:
        logger.warning(f"⚠️ Не вдалося видалити вихідне повідомлення: {e}")
    
    # Відповідаємо на callback в кінці
    await callback.answer()


@admin_router.callback_query(F.data == "admin_trust")
async def add_to_trusted(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = data.get("found_user")

    if not user:
        await callback.message.answer("❌ Не знайдено користувача в стані.")
        await callback.answer()
        return

    telegram_id = user['telegram_id']
    await callback.bot.db.set_user_trusted(telegram_id, 'true')


    # Повідомлення юзеру
    try:
        await callback.bot.send_message(
            chat_id=telegram_id,
            text="🎉 Вас додано до довірених користувачів!\n"
                 "Вам доступно більше функцій та публікацій 🙌"
        )
        logger.info(f"📩 Сповіщення надіслано юзеру {telegram_id}")
    except Exception as e:
        logger.warning(f"⚠️ Не вдалося надіслати повідомлення юзеру {telegram_id}: {e}")

    await callback.message.edit_text("✅ Користувача додано до довірених.")
    await callback.answer()




@admin_router.callback_query(F.data == "admin_trusted")
async def handle_trusted(callback: CallbackQuery):
    if callback.from_user.id not in callback.bot.config.ADMIN_IDS:
        await callback.answer("⛔️ Доступ заборонено", show_alert=True)
        return

    await callback.answer("⏳ Оновлення trusted користувачів запущено...", show_alert=True)

    updater = TrustedUserUpdater(
        db_pool=callback.bot.db.pool,
        api_url=callback.bot.config.API_BASE_URL,
        bot=callback.bot
    )


    stats = await updater.update_trusted()

    text = (
        "✅ Оновлення довірених завершено\n\n"
        f"🔄 Опрацьовано: {stats['processed']}\n"
        f"➕ Додано нових: {stats['added']}\n"
        f"📨 Повідомлень надіслано: {stats['notified']}"
    )

    await callback.message.answer(text)



class BroadcastStates(StatesGroup):
    choosing_audience = State() 
    waiting_for_text = State()

# 👉 Кнопка "Розсилка"
@admin_router.callback_query(F.data == "admin_broadcast")
async def handle_broadcast(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Всім", callback_data="broadcast_all"),
            InlineKeyboardButton(text="✅ Довіреним", callback_data="broadcast_trusted"),
            InlineKeyboardButton(text="🚫 Недовіреним", callback_data="broadcast_untrusted"),
        ]
    ])
    await state.set_state(BroadcastStates.choosing_audience)
    await callback.message.answer("Кому надіслати розсилку?", reply_markup=keyboard)
    await callback.answer()

# 👉 Вибір аудиторії
@admin_router.callback_query(F.data.startswith("broadcast_"))
async def handle_audience_choice(callback: CallbackQuery, state: FSMContext):
    audience = callback.data.split("_")[1]
    await state.update_data(audience=audience)
    await state.set_state(BroadcastStates.waiting_for_text)
    await callback.message.answer("✍ Введи текст розсилки (Markdown підтримується):")
    await callback.answer()

# 👉 Обробка тексту і відправлення
@admin_router.message(BroadcastStates.waiting_for_text)
async def send_broadcast(message: Message, state: FSMContext):
    data = await state.get_data()
    audience = data.get("audience")
    text = message.text.strip()

    # Отримуємо всіх юзерів і фільтруємо
    all_users = await message.bot.db.get_all_users()
    if audience == "trusted":
        users = [u for u in all_users if u.get("trusted")]
    elif audience == "untrusted":
        users = [u for u in all_users if not u.get("trusted")]
    else:
        users = all_users

    count, fails = 0, 0

    for user in users:
        try:
            await message.bot.send_message(
                chat_id=user['telegram_id'],
                text=text,
                parse_mode="Markdown"
            )
            count += 1
        except Exception as e:
            logger.warning(f"❌ Не вдалося {user['telegram_id']}: {e}")
            fails += 1

    await message.answer(
        f"📢 Розсилка завершена.\n\n"
        f"✅ Успішно: {count} користувачів\n"
        f"❌ Фейлів: {fails}"
    )
    await state.clear()



@admin_router.callback_query(F.data == "admin_cleanup")
async def handle_cleanup(callback: CallbackQuery):
    await callback.message.answer("⚠️ Точно видалити всі відхилені лоти?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Так", callback_data="admin_cleanup_confirm")],
        [InlineKeyboardButton(text="Скасувати", callback_data="admin_cleanup_cancel")]
    ]))
    await callback.answer()

@admin_router.callback_query(F.data == "clear_queue")
async def clear_queue(callback: CallbackQuery, state: FSMContext):
    deleted_count = await callback.bot.db.clear_pending_lots()
    await callback.message.answer(f"Чергу очищено. Видалено {deleted_count} лотів ✅")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_cleanup_confirm")
async def confirm_cleanup(callback: CallbackQuery):
    deleted = await callback.bot.db.delete_rejected_lots()
    await callback.answer(f"🗑 Видалено {deleted} лотів", show_alert=True)

@admin_router.callback_query(F.data == "admin_cleanup_cancel")
async def cancel_cleanup(callback: CallbackQuery):
    await callback.answer("❌ Скасовано", show_alert=True)

@admin_router.callback_query(F.data == "admin_ban_perm")
async def ban_user_perm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = data.get("found_user")

    # Перевірка, чи є користувач
    if not user:
        await callback.message.answer("❌ Користувача не знайдено. Невірні дані!")
        return

    try:
        # Блокуємо користувача назавжди, змінюючи trusted на 'banperm'
        await callback.bot.db.update_user_ban(user['id'], trusted='banperm')

        await callback.message.answer("✅ Користувача заблоковано назавжди.")
        await callback.bot.send_message(user['telegram_id'], 
            "🚫 Вас заблоковано в @Wonder_loop_bot. Ви більше не можете створювати лоти. По всім питанням звертайтесь в чат каналу https://t.me/wonder_loop"
        )

    except Exception as e:
        logger.error(f"❌ Помилка при блокуванні користувача: {e}")
        await callback.message.answer("❌ Сталася помилка при блокуванні користувача.")

    # Очистити дані з FSM
    await state.clear()






@admin_router.callback_query(F.data == "admin_ban_temp")
async def ban_user_temp(callback: CallbackQuery, state: FSMContext):
    # Отримуємо дані з FSM
    data = await state.get_data()
    
    # Якщо користувач знайдений через email/phone/username
    identifier = data.get("identifier")  # Припускаємо, що в state є identifier
    user = await callback.bot.db.find_user_by_email_or_phone(identifier)

    # Перевірка на наявність користувача
    if not user:
        await callback.message.answer("❌ Користувача не знайдено.")
        return  # Завершуємо, якщо користувача немає

    # Встановлюємо час для тимчасового блокування
    banned_until = datetime.utcnow() + timedelta(weeks=2)

    # Оновлюємо статус блокування користувача на 2 тижні в таблиці, змінюючи trusted
    await callback.bot.db.update_user_ban(user['id'], trusted='bantime')

    # Повідомлення про тимчасове блокування
    await callback.message.answer("✅ Користувача заблоковано на 2 тижні.")
    
    # Надсилаємо повідомлення користувачу
    await callback.bot.send_message(user['telegram_id'], 
        "⏱ Ви заблоковані в @Wonder_loop_bot на 2 тижні. Після цього доступ буде автоматично відновлено. По всім питанням звертайтесь в чат каналу https://t.me/wonder_loop."
    )

    # Очищуємо стан FSM
    await state.clear()







@admin_router.callback_query(F.data == "admin_unban")
async def unban_user(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = data.get("found_user")

    # Перевірка, чи є користувач
    if not user:
        await callback.message.answer("❌ Користувача не знайдено. Невірні дані!")
        return  # Якщо користувача немає, припиняємо виконання функції

    try:
        # Розблоковуємо користувача, змінюючи trusted на 'false'
        await callback.bot.db.update_user_ban(user['id'], trusted='false')

        await callback.message.answer("✅ Користувача розблоковано.")
        await callback.bot.send_message(user['telegram_id'], 
            "🔓 Ви розблоковані⭐️. Тепер можете знову користуватись ботом."
        )
    except Exception as e:
        logger.error(f"❌ Помилка при розблокуванні користувача: {e}")
        await callback.message.answer("❌ Сталася помилка при розблокуванні користувача.")

    # Очистити стан FSM
    await state.clear()




