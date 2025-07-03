from aiogram.types import InputMediaPhoto
from utils.keyboards import get_contact_seller_keyboard
from utils.text_utils import clean_surrogates  # якщо потрібно





class LotProcessor:
    def __init__(self, bot):
        self.bot = bot
    
    async def create_lot(self, data: dict) -> int:
        """Створює лот та вирішує, публікувати одразу чи чекати модерації"""

        lot_data = {
            'user_id': data['user_id'],
            'title': data['title'],
            'left_percent': data['left_percent'],
            'opened_at': data['opened_at'],
            'expire_at': data['expire_at'],
            'reason': data['reason'],
            'skin_type': data['skin_type'],
            'price_buy': data.get('price_buy'),
            'price_sell': data.get('price_sell'),
            'category': data['category'],
            'city': data['city'],
            'delivery': data['delivery'],
            'images': data['images'],
            'generated_text': data['generated_text'],
            'exchange': data.get('exchange', False),  # 👈 ОБОВ’ЯЗКОВО
            'description': data.get('user_description', '')  # 👈 ОБОВ’ЯЗКОВО
        }

        lot_id = await self.bot.db.create_lot(lot_data)

        user = await self.bot.db.get_user(data['user_id'])
        if user and user.get('trusted'):
            images = data['images']
            caption = f"🔁 {data['generated_text']}"
            caption = clean_surrogates(caption)

            try:
                if len(images) == 1:
                    msg = await self.bot.send_photo(
                        chat_id=self.bot.config.CHANNEL_ID,
                        photo=images[0],
                        caption=caption,
                        reply_markup=get_contact_seller_keyboard(user_id=data['user_id'])
                    )
                    await self.bot.db.set_lot_message_id(lot_id, msg.message_id)

                elif len(images) > 1:
                    media = [InputMediaPhoto(media=img) for img in images]
                    media[0].caption = caption

                    msgs = await self.bot.send_media_group(
                        chat_id=self.bot.config.CHANNEL_ID,
                        media=media
                    )
                    first_msg_id = msgs[0].message_id if msgs else None
                    await self.bot.db.set_lot_message_id(lot_id, first_msg_id)

                    await self.bot.send_message(
                        chat_id=self.bot.config.CHANNEL_ID,
                        text="📩 Зв'язатися з продавцем:",
                        reply_markup=get_contact_seller_keyboard(user_id=data['user_id'])
                    )

                await self.bot.db.update_lot_status(lot_id, 'active')

            except Exception as e:
                print(f"❌ Помилка при публікації лота {lot_id}: {e}")

        return lot_id
