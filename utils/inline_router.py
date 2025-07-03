from aiogram import F, Router
from aiogram.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton
)

def escape_markdown(text: str) -> str:
    escape_chars = r"\_*[]()~`>#+-=|{}.!<>"
    return ''.join(['\\' + c if c in escape_chars else c for c in text])

inline_router = Router()

@inline_router.inline_query()
async def inline_query_handler(query: InlineQuery):
    user_input = query.query.strip().lower()

    pool = query.bot.db.pool
    async with pool.acquire() as conn:

        # Якщо запит коротший за 2 символи — показуємо help-плитку
        if len(user_input) < 2:
            help_article = InlineQueryResultArticle(
                id="start_search",
                title="🔍 Натисни сюди, щоб знайти свою баночку",
                description="Введи назву: крем, маска, сироватка або інше",
                input_message_content=InputTextMessageContent(
                    message_text="🫙 Хочеш знайти свою баночку?\nПросто введи її назву після @Wonder_loop_bot",
                )
            )
            return await query.answer([help_article], cache_time=1)

        # Якщо є введення — робимо пошук
        rows = await conn.fetch("""
            SELECT 
                lots.id AS lot_id,
                lots.title,
                lots.left_percent,
                lots.price_sell,
                lots.user_id,
                lots.city,
                lots.delivery,
                users.telegram_id
            FROM lots
            JOIN users ON lots.user_id = users.id
            WHERE lots.status = 'active' AND lower(lots.title) LIKE $1
            ORDER BY lots.created_at DESC
            LIMIT 10
        """, f"%{user_input}%")

    results = []
    for row in rows:
        lot_id = row["lot_id"]
        title = row["title"]
        left = row["left_percent"]
        price = row["price_sell"]
        city = row["city"]
        delivery = row["delivery"]
        telegram_id = row["telegram_id"]

        contact_btn = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(
                text="✉️ Зв’язатись із продавцем",
                url=f"tg://user?id={telegram_id}"
            )]]
        )

        msg_text = (
            f"✨ *{escape_markdown(title)}*\n"
            f"• Залишок: {left}%\n"
            f"• Ціна: {price} грн\n"
            f"• Локація: {escape_markdown(city)}, доставка: {escape_markdown(delivery)}"
        )

        results.append(
            InlineQueryResultArticle(
                id=f"lot_{lot_id}",
                title=title,
                description=f"{left}% залишку • {price} грн • {city}",
                input_message_content=InputTextMessageContent(
                    message_text=msg_text,
                    parse_mode="Markdown"
                ),
                reply_markup=contact_btn
            )
        )

    await query.answer(results, cache_time=0)
