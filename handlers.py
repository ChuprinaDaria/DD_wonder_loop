from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, InputMediaPhoto
)
import logging
import os

from utils.keyboards import (
    status_human, render_stars, get_contact_seller_keyboard,
    get_main_keyboard, get_cancel_keyboard, get_confirm_keyboard,
    get_city_keyboard, get_skin_type_keyboard, get_delivery_keyboard,
    get_category_keyboard, get_phone_keyboard
)

from utils.messages import get_welcome_message
from utils.lot_processor import LotProcessor
from utils.admin_utils import AdminUtils
from utils.text_utils import clean_surrogates

logger = logging.getLogger(__name__)

# Створюємо головний router
router = Router()

# FSM States
class RegistrationStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_email = State()

from aiogram.fsm.state import State, StatesGroup

class LotStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_left_percent = State()
    waiting_for_opened_at = State()
    waiting_for_expire_at = State()
    waiting_for_reason = State()
    waiting_for_skin_type = State()

    exchange_or_sell = State()                  # 👈 новий: вибір між обміном і продажем
    waiting_for_exchange_details = State()      # 👈 новий: умови обміну
    waiting_for_price_buy = State()
    waiting_for_price_sell = State()
    waiting_for_description = State()           # 👈 новий: короткий опис (для обміну або продажу)

    waiting_for_category = State()
    waiting_for_city = State()
    waiting_for_delivery = State()
    waiting_for_photos = State()
    confirming_lot = State()


class AdminStates(StatesGroup):
    
    waiting_for_broadcast = State()

    # === ОСНОВНІ КОМАНДИ ===

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обробка команди /start"""
    bot = message.bot

    # Перевіряємо чи користувач вже зареєстрований
    user = await bot.db.get_user(message.from_user.id)

    banner_path = bot.config.BANNER_PATH
    photo = FSInputFile(banner_path) if banner_path and os.path.exists(banner_path) else None

    if user:
        # Користувач вже зареєстрований
        if photo:
            await message.answer_photo(
                photo=photo,
                caption=get_welcome_message(user['trusted']),
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer(
                get_welcome_message(user['trusted']),
                reply_markup=get_main_keyboard()
            )
    else:
        # Потрібна реєстрація
        await message.answer(
            "👋 Вітаємо в Wonder_Loop !\n\n"
            "Для початку роботи потрібно пройти швидку реєстрацію.\n"
            "📱 Будь ласка, поділіться своїм номером телефону:",
            reply_markup=get_phone_keyboard()
        )
        await state.set_state(RegistrationStates.waiting_for_phone)

@router.message(RegistrationStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обробка номера телефону"""
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text
    
    await state.update_data(phone=phone)
    await message.answer(
        "📧 Тепер введіть вашу електронну пошту:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(RegistrationStates.waiting_for_email)

@router.message(RegistrationStates.waiting_for_email)
async def process_email(message: Message, state: FSMContext):
    """Обробка email та завершення реєстрації"""
    email = message.text.strip()
    data = await state.get_data()
    username = message.from_user.username or None

    try:
        # Створюємо користувача з username
        user = await message.bot.db.create_user(
            telegram_id=message.from_user.id,
            phone=data['phone'],
            email=email,
            username=username
        )

        await state.clear()

        # ✅ Явне приведення trusted → bool
        is_trusted = str(user.get("trusted")).lower() == "true"

        # Повідомлення про статус
        status_text = (
            "✅ тепер можна виставляти свої банки"
            if is_trusted
            else "⏳ тепер можна виставляти свої банки — але з невеликим нюансом:"
        )

        await message.answer_photo(
            photo=FSInputFile(message.bot.config.BANNER_PATH)
            if message.bot.config.BANNER_PATH else None,
            caption=(
                "✅ ви в системі. реєстрацію пройдено.\n\n"
                f"{status_text}\n\n" +
                get_welcome_message(is_trusted)
            ),
            reply_markup=get_main_keyboard()
        )

    except Exception as e:
        logger.error(f"❌ Помилка при реєстрації: {e}")
        await message.answer("❌ Помилка при реєстрації. Спробуйте ще раз.")



# === ОСНОВНЕ МЕНЮ ===

@router.message(F.text == "✉️ Додати лот")
async def start_lot_creation(message: Message, state: FSMContext):
    """Початок створення лоту"""
    bot = message.bot
    user = await bot.db.get_user(message.from_user.id)
    
    if not user:
        await message.answer("❌ Спочатку пройдіть реєстрацію командою /start")
        return

    # Перевірка на блокування користувача
    if user.get("trusted") in ['banperm', 'bantime']:
        if user.get("trusted") == 'bantime' and user.get('banned_until') and datetime.utcnow() < user['banned_until']:
            await message.answer("🚫 Ви тимчасово заблоковані і не можете створювати лоти.")
            return
        if user.get("trusted") == 'banperm':
            await message.answer("🚫 Ви заблоковані назавжди і не можете створювати лоти.")
            return

    # 🟡 ВСТАВЛЯЄМО СЮДИ: оновлюємо стан user_id
    await state.update_data(user_id=user['id'])

    # Перевірка денного ліміту
    if not await bot.db.check_daily_limit(user['id']):
        limit = user['daily_limit']
        await message.answer(f"⏰ Ви досягли денного ліміту в {limit} постів. Спробуйте завтра!")
        return
    
    await message.answer(
        "📝 Почнемо створення вашого лоту!\n\n"
        "🧴 Назва продукту - повна:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(LotStates.waiting_for_title)


@router.message(F.text == "📃 Мої лоти")
async def show_lot_categories(message: Message):
    """Меню категорій лотів"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✨ Активні", callback_data="my_lots_active"),
            InlineKeyboardButton(text="✅ Продані", callback_data="my_lots_sold")
        ],
        [
            InlineKeyboardButton(text="🔒 Заброньовані", callback_data="my_lots_reserved"),
            InlineKeyboardButton(text="📴 Неактуальні", callback_data="my_lots_inactive")
        ]
    ])

    await message.answer("📦 Обери категорію лотів:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("my_lots_"))
async def show_lots_by_status(callback: CallbackQuery):
    status_map = {
        "my_lots_active": "active",
        "my_lots_sold": "sold",
        "my_lots_reserved": "reserved",
        "my_lots_inactive": "inactive"
    }

    key = callback.data
    status = status_map.get(key)
    user = await callback.bot.db.get_user(callback.from_user.id)

    if not user:
        await callback.answer("❌ Користувача не знайдено", show_alert=True)
        return

    lots = await callback.bot.db.get_user_lots(user_id=user['id'])
    filtered = [lot for lot in lots if lot['status'] == status]

    if not filtered:
        await callback.message.answer("📭 Лотів із цим статусом поки немає.")
        return

    for lot in filtered[:10]:
        status_emoji = get_status_emoji(lot['status'])
        text = (
            f"{status_emoji} **{lot['title']}**\n"
            f"💰 {lot['price_sell']} грн\n"
            f"📅 {lot['created_at'].strftime('%d.%m.%Y')}\n"
            f"📊 Статус: {get_status_text(lot['status'])}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Актуально", callback_data=f"lot_status_{lot['id']}_active"),
                InlineKeyboardButton(text="🔒 Заброньовано", callback_data=f"lot_status_{lot['id']}_reserved")
            ],
            [
                InlineKeyboardButton(text="✅ Продано", callback_data=f"lot_status_{lot['id']}_sold"),
                InlineKeyboardButton(text="📴 Неактуально", callback_data=f"lot_status_{lot['id']}_inactive")
            ]
        ])
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@router.message(F.text == "✍️ Правила")
async def show_rules(message: Message):
    """Показ правил"""
    rules_text = """
📋 WONDER_LOOP
safe-space в Telegram для тих, хто мазав - але не зійшлось
❗️ порушив правила → 1 попередження → бан

☝️ ваш username має бути відкритим — щоб з вами могли зв’язатись покупці. інакше — шанси продати здулись.

🛠️ оновлюйте статус лота в боті вчасно: “бронь”, “продано” — усе міняється вручну в адмінці.
самостійно пости не видаляються — це робить система, коли ви позначаєте їх як “продано”.

ЩО МОЖНА: 
✔️ вживаний догляд: обличчя, тіло, волосся — якщо користувались і не зайшло 
✔️ гаджети для обличчя — ролери, щіточки, дарсонвалі, маски — якщо справні 
✔️ банки з відкритим доступом — тільки якщо норм стан і видно залишок 
✔️ мініки, саше, тревел-формати — ок, якщо вже ваші і не з готелю у Шарм-еш-Шейху з 2019 року
✔️ обмін — якщо хочете поміняти на щось інше, кажіть чесно, що шукаєте

ЩО НЕ МОЖНА:
❌ нові продукти (новеньке — в інсту, а не сюди)
❌ засоби з рф/білорусі
❌ рецептурні штуки, антибіотики, БАДи, їжа — це не той чат
❌ парфуми, декоративка — інше поле бою
❌ реклама, марафони, фолов-бек, курси, “я візажист” → миттєвий бан

🎯 РЕЙТИНГ:
Ваш рейтинг залежить від кількості успішних продажів!

✅ЯК ВИСТАВИТИ ЛОТ:
📸 фото — чіткі, свої, на світлому фоні і не на фоні пледа, ніг або чужої спини
🧴 назва продукту — повна
📅 дата відкриття або batch-код
💧 залишок — словесно і візуально (1 із 3 фото має це показувати)
📖 короткий опис + ✍️ причина продажу, якщо хочеться виговоритись
🧠 тип шкіри і чому не підійшло (будьте чесним — нам не треба ідеальна репутація банок)
📍 місто та спосіб передачі / доставки
💰 ціна або умови обміну

🗓ФОРМАТ ПУБЛІКАЦІЇ:
– 1 пост = 1 засіб, максимум 3 фото
– якщо набір (продається разом), тоді всі банки на одному фото, без колажів
- максимум 5 на день (клієнтам DD — 10 😉)
для гаджетів: 
– обов’язково: що це, скільки користувались, чи працює, чи є інструкція/коробка 
– і, будь ласка, протріть та почистіть перед фото 

🔁 ЯК ОНОВИТИ ЛОТ?
нічого вручну писати не треба — просто зайдіть у свій розділ “мої лоти” в боті, виберіть потрібний — і змініть його статус [актуально, не актуально, бронь та продано] і  бот сам усе підправить у каналі: і напис, і статус.
💬 якщо щось неясно — краще спитайте, ніж поруште. бо друге — це бан.

✅ <b>Повний перелік правил:</b> <a href="https://drive.google.com/file/d/14cY8PD9fut8BNZnUWHFI5to5_jptxkgW/view?usp=sharing">відкрити PDF</a>
"""
    await message.answer(rules_text, parse_mode="HTML")


# === СТВОРЕННЯ ЛОТУ ===



# === СКАСУВАННЯ ===

@router.message(F.text == "❌ Скасувати")
@router.callback_query(F.data == "cancel")
async def cancel_action(update, state: FSMContext):
    """Скасування поточної дії та повернення в головне меню"""
    
    current_state = await state.get_state()
    await state.clear()  # скидаємо FSM у будь-якому випадку

    if isinstance(update, Message):
        text = "❌ Дію скасовано. Ви повернулись у головне меню."
        await update.answer(text, reply_markup=get_main_keyboard())
    else:
        # Якщо це callback — оновлюємо повідомлення і відкриваємо нове з меню
        await update.message.edit_text("❌ Дію скасовано.")
        await update.message.answer("👇 Оберіть дію:", reply_markup=get_main_keyboard())
        await update.answer()



@router.message(LotStates.waiting_for_title)
async def process_title(message: Message, state: FSMContext):
    current = await state.get_state()
    if current != LotStates.waiting_for_title:
        return

    """Обробка назви товару"""
    await state.update_data(title=message.text)
    await message.answer(
    "💧 Залишок — словесно <i>від 1 до 100</i> і візуально <i>1 із 3 фото має це показувати</i>:",
    parse_mode="HTML"
    )
    await state.set_state(LotStates.waiting_for_left_percent)

@router.message(LotStates.waiting_for_left_percent)
async def process_left_percent(message: Message, state: FSMContext):
    current = await state.get_state()
    if current != LotStates.waiting_for_left_percent:
        return  # FSM уже могла бути скинута, не продовжуємо
    """Обробка відсотку що залишився"""
    try:
        percent = int(message.text)
        if not 1 <= percent <= 100:
            raise ValueError
        
        await state.update_data(left_percent=percent)
        await message.answer(
            "📅 Коли було відкрито баночку дата, місяць?\n"
            "<i>(напишіть тільки дату або “не відкрито”  або batch-код)</i>",
            parse_mode="HTML"
        )

        await state.set_state(LotStates.waiting_for_opened_at)
        
    except ValueError:
        await message.answer("❌ Введіть число від 1 до 100")

@router.message(LotStates.waiting_for_opened_at)
async def process_opened_at(message: Message, state: FSMContext):
    current = await state.get_state()
    if current != LotStates.waiting_for_opened_at:
        return  # FSM скинута або інший стан — ігноруємо
    """Обробка часу відкриття"""
    await state.update_data(opened_at=message.text)
    await message.answer(
        "🗓 Строк придатності, тільки дата, місяць:"
    )
    await state.set_state(LotStates.waiting_for_expire_at)

@router.message(LotStates.waiting_for_expire_at)
async def process_expire_at(message: Message, state: FSMContext):
    current = await state.get_state()
    if current != LotStates.waiting_for_expire_at:
        return  # FSM скинута або змінився стан — нічого не робимо

    """Обробка терміну придатності"""
    await state.update_data(expire_at=message.text)
    await message.answer(
        "✍️ Причина продажу, опишіть кількома словами\n<i>(будьте чесним — нам не треба ідеальна репутація банки)</i>",
        parse_mode="HTML"
    )

    await state.set_state(LotStates.waiting_for_reason)

@router.message(LotStates.waiting_for_reason)
async def process_reason(message: Message, state: FSMContext):
    current = await state.get_state()
    if current != LotStates.waiting_for_reason:
        return

    """Обробка причини продажу"""
    await state.update_data(reason=message.text)
    await message.answer(
        "🧠 Для якого типу шкіри засіб",
        reply_markup=get_skin_type_keyboard()
    )
    await state.set_state(LotStates.waiting_for_skin_type)

# Після типу шкіри: запит — обмін чи продаж
@router.message(LotStates.waiting_for_skin_type)
async def process_skin_type(message: Message, state: FSMContext):
    await state.update_data(skin_type=message.text)
    await message.answer(
        "🔁 Ви хочете обмін чи продаж?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Обмін")], [KeyboardButton(text="Продаж")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    await state.set_state(LotStates.exchange_or_sell)


# Обробка вибору обмін / продаж
@router.message(LotStates.exchange_or_sell)
async def process_exchange_or_sell(message: Message, state: FSMContext):
    choice = message.text.strip().lower()

    if "обмін" in choice:
        await state.update_data(exchange=True)
        await message.answer("✏️ Опишіть умови обміну, кількома словами:", reply_markup=get_cancel_keyboard())
        await state.set_state(LotStates.waiting_for_exchange_details)

    elif "продаж" in choice:
        await state.update_data(exchange=False)
        await message.answer("💰 За скільки купували? (введіть суму в гривнях):", reply_markup=get_cancel_keyboard())
        await state.set_state(LotStates.waiting_for_price_buy)

    else:
        await message.answer("❌ Виберіть Обмін або Продаж.")


# Якщо обмін: отримуємо умови
@router.message(LotStates.waiting_for_exchange_details)
async def process_exchange_details(message: Message, state: FSMContext):
    await state.update_data(exchange_details=message.text)
    await message.answer("📖 Короткий опис, кількома словами :", reply_markup=get_cancel_keyboard())
    await state.set_state(LotStates.waiting_for_description)


# Якщо продаж: ціна купівлі
@router.message(LotStates.waiting_for_price_buy)
async def process_price_buy(message: Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(price_buy=price)
        await message.answer("💸 За скільки продаєте? (введіть суму в гривнях):")
        await state.set_state(LotStates.waiting_for_price_sell)
    except ValueError:
        await message.answer("❌ Введіть коректну суму")


# Якщо продаж: ціна продажу
@router.message(LotStates.waiting_for_price_sell)
async def process_price_sell(message: Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(price_sell=price)
        await message.answer("📖 Короткий опис, кількома словами :", reply_markup=get_cancel_keyboard())
        await state.set_state(LotStates.waiting_for_description)
    except ValueError:
        await message.answer("❌ Введіть коректну суму")


# Після обміну або продажу: опис
@router.message(LotStates.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("🗂 Виберіть категорію:", reply_markup=get_category_keyboard())
    await state.set_state(LotStates.waiting_for_category)


@router.message(LotStates.waiting_for_category)
async def process_category(message: Message, state: FSMContext):
    current = await state.get_state()
    if current != LotStates.waiting_for_category:
        return

    """Обробка категорії"""
    await state.update_data(category=message.text)
    await message.answer(
        "📍 Місто",
        reply_markup=get_city_keyboard()
    )
    await state.set_state(LotStates.waiting_for_city)

@router.message(LotStates.waiting_for_city)
async def process_city(message: Message, state: FSMContext):
    current = await state.get_state()
    if current != LotStates.waiting_for_city:
        return
    """Обробка міста"""
    await state.update_data(city=message.text)
    await message.answer(
        "🚚 Яка доставка?\n<i>(наприклад: 'Нова Пошта', 'Укрпошта', 'самовивіз')</i>",
        reply_markup=get_delivery_keyboard(),
        parse_mode="HTML"
    )

    await state.set_state(LotStates.waiting_for_delivery)

@router.message(LotStates.waiting_for_delivery)
async def process_delivery(message: Message, state: FSMContext):
    current = await state.get_state()
    if current != LotStates.waiting_for_delivery:
        return

    """Обробка доставки"""
    await state.update_data(delivery=message.text)
    await message.answer(
        "📸 Тепер надішліть 3 фото товару по черзі.\n\n"
        "⚠️ Важливо:\n"
        "• Чітке, своє, не на фоні пледа, ніг чи чужого живота\n"
        "• Одне з 3 фото має показувати залишок продукту\n"
        "• Формат — квадрат або 4:5 (як в інсті)\n"
        "• Фото на білому або нейтральному світлому фоні\n"
        "• Без сторонніх предметів і частин тіла\n"
        "• Гарне освітлення, будь ласка 🙏\n\n"
        "Надішліть перше фото:",
        reply_markup=get_cancel_keyboard()
    )

    await state.update_data(images=[])
    await state.set_state(LotStates.waiting_for_photos)


@router.message(LotStates.waiting_for_photos, F.photo)
async def process_photos(message: Message, state: FSMContext):
    current = await state.get_state()
    if current != LotStates.waiting_for_photos:
        return
     
    """Обробка фотографій"""
    data = await state.get_data()
    images = data.get('images', [])
    photo_message_ids = data.get('photo_message_ids', [])
    photo_message_ids.append(message.message_id)
    
    # Отримуємо найкращу якість фото
    photo = message.photo[-1]
    
    # Перевіряємо фото через Google Vision
    vision_service = message.bot.vision
    try:
        is_valid, reason = await vision_service.validate_photo(photo.file_id, message.bot)
        
        if not is_valid:
            await message.answer(
                "❌ Фото не пройшло перевірку!\n\n"
                f"Причина: {reason}\n\n"
                "Переконайтеся що:\n"
                "• Фото чітке і не розмите\n"
                "• Немає людей або частин тіла\n"
                "• Товар добре видно\n"
                "• Відсутній неприпустимий контент\n\n"
                "Надішліть інше фото:"
            )
            return
            
        print(f"✅ [Handler] Фото пройшло перевірку: {reason}")
        
    except Exception as e:
        logger.error(f"Помилка при перевірці фото: {e}")
        print(f"⚠️ [Handler] Перевірка недоступна, пропускаємо: {e}")
        # Продовжуємо без перевірки якщо сервіс недоступний
    
    # Додаємо водяний знак
    try:
        processed_photo = await vision_service.add_watermark_from_file_id(photo.file_id, message.bot)
        images.append(processed_photo)
        print(f"✅ [Handler] Додано ватермарк до фото")
    except Exception as e:
        logger.error(f"Помилка при додаванні водяного знаку: {e}")
        images.append(photo.file_id)
        print(f"⚠️ [Handler] Використовуємо оригінальне фото без ватермарку")
    
    await state.update_data(images=images, photo_message_ids=photo_message_ids)
    
    # Підтверджуємо прийняття фото
    await message.answer(
        f"✅ Фото #{len(images)} додано!\n\n"
        
    )
   

    # Кнопки навігації
    if len(images) < 3:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Достатньо фото", callback_data="photos_done")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
        ])
        await message.answer(
            f"✅ Фото {len(images)}/3 додано!\n\n"
            f"Можете надіслати ще {3-len(images)} фото або завершити:",
            reply_markup=keyboard
        )
    else:
        await finish_photo_upload(message, state)


@router.callback_query(F.data == "photos_done")
async def finish_photo_upload_callback(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current != LotStates.waiting_for_photos:
        return

    """Обробка кнопки '✅ Достатньо фото'"""
    await callback.answer()  # відповідаємо одразу, щоб уникнути помилок
    logger.info(f"➡️ Користувач {callback.from_user.id} (@{callback.from_user.username}) натиснув '✅ Достатньо фото'")
    
    await callback.message.edit_text("⏳ Генеруємо текст поста, зачекай кілька секунд…")
    await finish_photo_upload(callback.message, state)


async def finish_photo_upload(message: Message, state: FSMContext):
    """Завершення завантаження фото та генерація превью"""
    data = await state.get_data()
    user_id = message.from_user.id
    username = message.from_user.username or "без username"

    logger.info(f"🛠 Генерація поста для користувача {user_id} (@{username})")

    try:
        openai_service = message.bot.openai
        generated_text = await openai_service.generate_post_text(data)
        logger.info(f"✅ Успішно згенеровано текст для {user_id}")
    except Exception as e:
        logger.error(f"❌ Помилка при генерації тексту для {user_id}: {e}")
        generated_text = create_default_post_text(data)

    await state.update_data(generated_text=generated_text)

    images = data.get('images', [])

    try:
        if images:
            if len(images) > 1:
                media = [InputMediaPhoto(media=img) for img in images]
                media[0].caption = generated_text
                media[0].parse_mode = "Markdown"

                await message.answer("📸 Ось як виглядатиме твій пост:")
                await message.bot.send_media_group(chat_id=message.chat.id, media=media)

            else:
                await message.answer_photo(
                    photo=images[0],
                    caption=generated_text,
                    parse_mode="Markdown"
                )

            # Кнопка підтвердження окремо
            await message.answer(
                "✅ Якщо все виглядає добре — натисни кнопку нижче, щоб підтвердити публікацію:",
                reply_markup=get_confirm_keyboard()
            )
        else:
            await message.answer(
                generated_text,
                reply_markup=get_confirm_keyboard(),
                parse_mode="Markdown"
            )

    except TelegramBadRequest as e:
        logger.error(f"❌ TelegramBadRequest при відправці превʼю: {e}")
        await message.answer("❌ Сталася помилка при показі превʼю. Перевір фото або текст.")

    await state.set_state(LotStates.confirming_lot)


@router.callback_query(F.data == "confirm_lot")
async def confirm_lot(callback: CallbackQuery, state: FSMContext):
    """Підтвердження створення лоту"""
    await callback.answer()
    data = await state.get_data()

    # 🧠 Обробка exchange / price логіки
    if data.get("exchange") is True:
        data["exchange_option"] = data.get("exchange_details", "").strip()
    else:
        data["exchange_option"] = "пропустити"

    exchange_option = data.get('exchange_option', '').strip().lower()
    is_exchange = bool(exchange_option and exchange_option != 'пропустити')

    # 🔍 Перевірка на всі обов'язкові поля
    base_required_fields = [
        'title', 'left_percent', 'opened_at', 'expire_at', 'reason',
        'skin_type', 'category', 'city', 'delivery', 'images', 'generated_text'
    ]

    if not is_exchange:
        base_required_fields += ['price_buy', 'price_sell']

    missing = [key for key in base_required_fields if key not in data or data.get(key) in [None, '']]
    if missing:
        logger.error(f"❌ Відсутні обов'язкові поля: {missing}")
        try:
            await callback.message.edit_caption("❌ Помилка: відсутні деякі дані. Спробуй створити лот ще раз.")
        except TelegramBadRequest:
            await callback.message.answer("❌ Помилка: відсутні деякі дані. Спробуй створити лот ще раз.")
        await state.clear()
        return

    # 👤 Отримання даних користувача з БД
    try:
        user = await callback.bot.db.get_user(callback.from_user.id)
        user_id = user['id']
        username = callback.from_user.username or "без username"
    except Exception as e:
        logger.error(f"❌ Не вдалося отримати користувача з БД: {e}")
        await callback.message.answer("❌ Помилка при перевірці користувача.")
        await state.clear()
        return

    logger.info(f"📩 Користувач {user_id} (@{username}) підтверджує створення лоту")
    data['user_id'] = user_id
    data['exchange'] = is_exchange

    # 📦 Створення лоту
    try:
        lot_processor = LotProcessor(callback.bot)
        lot_id = await lot_processor.create_lot(data)
        logger.info(f"✅ Лот #{lot_id} створено користувачем {user_id}")
        await state.clear()

        # 🧽 Видаляємо попереднє повідомлення (кнопки/медіа)
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"⚠️ Не вдалося видалити попереднє повідомлення: {e}")

        # 📢 Повідомлення залежно від статусу користувача
        # 📢 Повідомлення залежно від статусу користувача
        if user.get('trusted') is True or str(user.get('trusted')).lower() == 'true':

            user_telegram_id = callback.from_user.id
    
            # Детальне логування
            print(f"📲 Raw user data: {user}")
            print(f"📲 Telegram ID користувача: {user_telegram_id}")
            print(f"📲 Тип telegram_id: {type(user_telegram_id)}")
    
            # Перевірка на валідність
            if not user_telegram_id or not isinstance(user_telegram_id, int) or user_telegram_id <= 0:
                logger.error(f"❌ Невалідний telegram_id: {user_telegram_id}")
                await callback.message.answer("❌ Помилка з ідентифікатором користувача.")
                return

            try:
                # Тестування кнопки перед відправкою
                test_keyboard = get_contact_seller_keyboard(user_id=user_telegram_id)
                print(f"🔧 Створена кнопка: {test_keyboard}")
                print(f"🔧 URL кнопки: tg://user?id={user_telegram_id}")
        
                # Публікуємо лот у канал
                images = data['images']
                caption = f"🔁 {data['generated_text']}"
                caption = clean_surrogates(caption)

                if len(images) == 1:
                    # Відправляємо фото з текстом
                    msg = await callback.bot.send_photo(
                        chat_id=callback.bot.config.CHANNEL_ID,
                        photo=images[0],
                        caption=caption
                    )
                    await callback.bot.db.set_lot_message_id(lot_id, msg.message_id)
            
                    # Отримуємо рейтинг користувача
                    stars = await render_stars(user['id'], callback.bot)  # використовуємо внутрішній ID для БД
            
                    # Відправляємо повідомлення з рейтингом та кнопкою контакту
                    await callback.bot.send_message(
                        chat_id=callback.bot.config.CHANNEL_ID,
                        text=f"{stars}\n\n⭐️Лот від Wonder Trust⭐️:",
                        reply_markup=get_contact_seller_keyboard(user_id=user_telegram_id, username=username)

                    )

                elif len(images) > 1:
                    # Відправляємо медіа-групу
                    media = [InputMediaPhoto(media=img) for img in images]
                    media[0].caption = caption

                    msgs = await callback.bot.send_media_group(
                        chat_id=callback.bot.config.CHANNEL_ID,
                        media=media
                    )
                    first_msg_id = msgs[0].message_id if msgs else None
                    await callback.bot.db.set_lot_message_id(lot_id, first_msg_id)
            
                    # Отримуємо рейтинг користувача
                    stars = await render_stars(user['id'], callback.bot)  # використовуємо внутрішній ID для БД
            
                    # Відправляємо повідомлення з рейтингом та кнопкою контакту
                    await callback.bot.send_message(
                        chat_id=callback.bot.config.CHANNEL_ID,
                        text=f"{stars}\n\n⭐️Лот від Wonder Trust⭐️:",
                        reply_markup=get_contact_seller_keyboard(user_id=user_telegram_id, username=username)

                    )

                await callback.bot.db.update_lot_status(lot_id, 'active')

            except Exception as e:
                logger.warning(f"⚠️ Помилка при публікації лота в канал: {e}")
                await callback.message.answer(f"❌ Не вдалося опублікувати лот: {e}")

                    

                await callback.bot.db.update_lot_status(lot_id, 'active')

            except Exception as e:
                logger.warning(f"⚠️ Помилка при публікації лота в канал: {e}")
                await callback.message.answer(f"❌ Не вдалося опублікувати лот: {e}")

            # Повідомлення користувачу
            text = (
                "✅ Лот створено та опубліковано в каналі!\n\n"
                "Дякуємо за використання Wonder_Loop! 💖"
            )
            await callback.message.answer(text, reply_markup=get_main_keyboard())

        else:
            text = (
                "✅ Лот створено та відправлено на модерацію!\n\n"
                "Ми розглянемо його найближчим часом та повідомимо про результат."
            )

        await callback.message.answer(
            text,
            reply_markup=get_main_keyboard()
        )

    except Exception as e:
        logger.error(f"❌ Помилка при створенні лоту: {e}")
        await callback.message.answer("❌ Щось пішло не так при створенні лоту. Спробуй пізніше.")
        await state.clear()




@router.callback_query(F.data.startswith("lot_status_"))
async def change_lot_status(callback: CallbackQuery):
    bot = callback.bot  # або додай bot аргументом, якщо хочеш
    try:
        _, _, lot_id_str, new_status = callback.data.split("_")
        lot_id = int(lot_id_str)

        lot = await bot.db.get_lot(lot_id)
        if not lot:
            await callback.answer("❌ Лот не знайдено", show_alert=True)
            return

        await bot.db.update_lot_status(lot_id, new_status)

        if lot.get("message_id"):
            lot["status"] = new_status
            await update_channel_post(bot, lot)

        status_texts = {
            'active': 'актуальним',
            'reserved': 'заброньованим',
            'sold': 'проданим',
            'inactive': 'неактуальним'
        }

        await callback.answer("✅ Статус оновлено!")
        try:
            await callback.message.edit_text(
                f"✅ Статус лоту змінено на '{status_texts.get(new_status, new_status)}'!"
            )
        except:
            pass

    except Exception as e:
        logger.error(f"❌ Помилка при оновленні статусу лота {callback.data}: {e}")
        await callback.answer("⚠️ Не вдалося оновити статус", show_alert=True)







 








@router.callback_query()
async def catch_all_callbacks(callback: CallbackQuery):
    logger.warning(f"👀 НЕСПІЙМАНИЙ CALLBACK: {callback.data}")
    await callback.answer("⛔️ Невідома дія. Спробуйте ще раз.")


# === АДМІН КОМАНДИ ===

@router.message(Command("admin"))
async def admin_panel(message: Message):
    """Адмін панель"""
    if message.from_user.id not in message.bot.config.ADMIN_IDS:
        await message.answer("❌ У вас немає доступу до адмін панелі")
        return
    
    stats = await message.bot.db.get_general_stats()
    
    text = f"""
🔧 АДМІН ПАНЕЛЬ WONDER_LOOP

📊 Статистика:
👥 Користувачів: {stats['total_users']}
✅ Довірених: {stats['trusted_users']}
📦 Лотів: {stats['total_lots']}
💰 Продано: {stats['total_sold']}

🎛 Управління:
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏳ Черга модерації", callback_data="admin_queue"),
            
        ],
        [
            InlineKeyboardButton(text="📋 Оновити довірених", callback_data="admin_trusted"),
            InlineKeyboardButton(text="📢 Розсилка", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton(text="👥 Управління юзерами", callback_data="admin_users"),
            
        ],
        [
            InlineKeyboardButton(text="🧹 Очистити чергу", callback_data="clear_queue")
        ]
    ])
    
    await message.answer(text, reply_markup=keyboard)  # без parse_mode


@router.callback_query(F.data == "clear_queue")
async def handle_clear_queue(callback: CallbackQuery):
    """Очистити чергу модерації (pending лоти)"""
    count = await callback.bot.db.clear_pending_lots()
    await callback.message.edit_text(f"🧹 Очистили {count} лот(ів) зі статусом 'pending'.")
    await callback.answer("Черга очищена ✅")




# === ДОПОМІЖНІ ФУНКЦІЇ ===

def get_status_emoji(status: str) -> str:
    """Отримання емодзі для статусу"""
    emojis = {
        'pending': '⏳',
        'active': '🔁',
        'reserved': '🔒',
        'sold': '✅',
        'rejected': '❌',
        'deleted': '🗑',
        'inactive': '🚫'  # 👈 або інший емоджі на твій смак
    }

    return emojis.get(status, '❓')

def get_status_text(status: str) -> str:
    """Отримання тексту для статусу"""
    statuses = {
        'pending': 'На модерації',
        'active': 'Актуально',
        'reserved': 'Заброньовано',
        'sold': 'Продано',
        'rejected': 'Відхилено',
        'deleted': 'Видалено',
        'inactive': 'Неактуально'  # 👈 ось цей рядочок
    }
    return statuses.get(status, 'Невідомо')


def create_default_post_text(data: dict) -> str:
    """Створення базового тексту поста"""
    text = f"✨ **{data['title']}**\n\n"
    text += f"📊 Залишок: {data['left_percent']}%\n"
    text += f"📅 Відкрито: {data['opened_at']}\n"
    text += f"⏰ Діє до: {data['expire_at']}\n"
    text += f"💭 Причина продажу: {data['reason']}\n"
    text += f"🧴 Тип шкіри: {data['skin_type']}\n"
    text += f"💸 Купувала за: {data['price_buy']} грн\n"
    text += f"💰 Ціна: **{data['price_sell']} грн**\n"
    text += f"📱 Категорія: {data['category']}\n"
    text += f"🏙 Місто: {data['city']}\n"
    text += f"🚚 Доставка: {data['delivery']}\n\n"
    text += "📩 Звертайтеся в особисті повідомлення!"
    
    return text


async def update_channel_post(bot, lot: dict):
    """Оновлення поста в каналі після зміни статусу"""
    try:
        status_emoji = get_status_emoji(lot['status'])
        status_text = status_human(lot['status'])

        
        

        updated_caption = (
            f"{status_emoji} {lot['generated_text']}\n\n"
            f"🔁 Статус: *{status_text}*\n"
            
        )

       

        await bot.edit_message_caption(
            chat_id=bot.config.CHANNEL_ID,
            message_id=lot['message_id'],
            caption=updated_caption,
            parse_mode="Markdown",
            
        )


    except Exception as e:
        logger.error(f"❌ Помилка при оновленні поста: {e}")


