from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot
from typing import Optional


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Головна клавіатура"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✉️ Додати лот")],
            [KeyboardButton(text="📃 Мої лоти"), KeyboardButton(text="✍️ Правила")],
        ],
        resize_keyboard=True,
        persistent=True
    )
    return keyboard

def get_phone_keyboard() -> ReplyKeyboardMarkup:
    """Клавіатура для запиту номера телефону"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поділитися номером", request_contact=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавіатура зі скасуванням"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Скасувати")],
        ],
        resize_keyboard=True
    )
    return keyboard

def get_skin_type_keyboard() -> ReplyKeyboardMarkup:
    """Клавіатура для типу шкіри"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Суха"), KeyboardButton(text="Жирна")],
            [KeyboardButton(text="Комбінована"), KeyboardButton(text="Нормальна")],
            [KeyboardButton(text="Чутлива"), KeyboardButton(text="Всі типи")],
            [KeyboardButton(text="❌ Скасувати")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

def get_category_keyboard() -> ReplyKeyboardMarkup:
    """Клавіатура для категорій"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧴 Догляд за обличчям"),KeyboardButton(text="🧼 Догляд за тілом")],
            [KeyboardButton(text="💆‍♀️ Догляд за волоссям"),KeyboardButton(text="⚙️ Гаджети"),],
            [KeyboardButton(text="❌ Скасувати")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

def get_city_keyboard() -> ReplyKeyboardMarkup:
    """Клавіатура для міст"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Київ"), KeyboardButton(text="Харків")],
            [KeyboardButton(text="Одеса"), KeyboardButton(text="Дніпро")],
            [KeyboardButton(text="Львів"), KeyboardButton(text="Запоріжжя")],
            [KeyboardButton(text="Вінниця"), KeyboardButton(text="Інше місто")],
            [KeyboardButton(text="❌ Скасувати")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

def get_exchange_or_sell_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄Обмін")],
            [KeyboardButton(text="💸Продаж")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )



def get_delivery_keyboard() -> ReplyKeyboardMarkup:
    """Клавіатура для способів доставки"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Нова Пошта"), KeyboardButton(text="📮 Укрпошта")],
            [KeyboardButton(text="🚗 Самовивіз"), KeyboardButton(text="🚚 Кур'єр")],
            [ KeyboardButton(text="💬 Домовимось")],
            [KeyboardButton(text="❌ Скасувати")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавіатура підтвердження лоту"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Підтвердити", callback_data="confirm_lot"),
                
            ],
            [
                InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")
            ]
        ]
    )
    return keyboard

def get_moderation_keyboard(lot_id: int) -> InlineKeyboardMarkup:
    """Клавіатура для модерації"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Схвалити", callback_data=f"mod_approve_{lot_id}"),
                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"mod_reject_{lot_id}")
            ],
            [
                InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"mod_edit_{lot_id}")
            ]
        ]
    )
    return keyboard

def get_contact_seller_keyboard(user_id: int, username: Optional[str] = None) -> InlineKeyboardMarkup:
    """Клавіатура для зв'язку з продавцем (адаптована під десктоп і мобілки)"""
    if username:
        url = f"https://t.me/{username}"
    else:
        url = f"tg://user?id={user_id}"  # fallback для мобілок без username

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 Зв'язатися з продавцем",
                    url=url
                )
            ]
        ]
    )


def get_status_buttons(lot_id: int, current_status: str) -> InlineKeyboardMarkup:
    buttons = []

    if current_status == 'active':
        buttons.append(InlineKeyboardButton(text="🔁 Заброньовано", callback_data=f"status:reserved:{lot_id}"))
        buttons.append(InlineKeyboardButton(text="✅ Продано", callback_data=f"status:sold:{lot_id}"))

    return InlineKeyboardMarkup(inline_keyboard=[buttons])

def status_human(status: str) -> str:
    mapping = {
        "active": "Активний",
        "reserved": "Заброньовано",
        "sold": "Продано",
        "inactive": "Неактуальний"  # ← додаємо сюди
    }
    return mapping.get(status, "Невідомо")


async def render_stars(user_id: int, bot: Bot) -> str:
    rating = await bot.db.get_user_rating(user_id)

    if rating is None:
        return "⭐️ Немає оцінок"

    full_stars = int(round(rating))  # округлення до найближчого цілого
    empty_stars = 5 - full_stars

    stars = "⭐️" * full_stars + "▫️" * empty_stars
    return f"👤 Рейтинг продавця:\n{stars} ({rating:.1f}/5)"




