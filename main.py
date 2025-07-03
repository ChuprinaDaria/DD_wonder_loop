import asyncio
import logging
import os
from dotenv import load_dotenv

# ⬅ Завантажуємо .env
load_dotenv()

# Імпорти після завантаження ENV
from config import Config
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from handlers import router
from database import DatabaseManager
from utils.ai_services import OpenAIService, GoogleVisionService
from utils.admin_utils import admin_router, AdminUtils
from utils.TrustedUserUpdater import TrustedUserUpdater
from utils.inline_router import inline_router

# ⬅ Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Основна функція запуску бота"""
    try:
        print("[DEBUG] BOT_TOKEN from ENV:", os.getenv("BOT_TOKEN"))

        # ⬅ Ініціалізація конфігурації
        config = Config()

        # ⬅ Ініціалізація бота та диспетчера
        bot = Bot(token=config.BOT_TOKEN)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        # ⬅ Ініціалізація бази
        db_manager = DatabaseManager(config.DATABASE_URL)
        await db_manager.init_db()

        # ⬅ Ініціалізація AI-сервісів
        openai_service = OpenAIService(config.OPENAI_API_KEY)
        vision_service = GoogleVisionService(config.GOOGLE_VISION_KEY)

        # ⬅ Передача сервісів в обʼєкт бота
        bot.db = db_manager
        bot.openai = openai_service
        bot.vision = vision_service
        bot.config = config
        bot.admin_utils = AdminUtils(bot)

        # ⬅ TrustedUserUpdater (викликаємо раз на 2 години)
        async def run_trusted_updater():
            updater = TrustedUserUpdater(
                db_pool=db_manager.pool,
                api_url=config.API_BASE_URL,
                bot=bot
            )
            while True:
                logger.info("⏳ Оновлення довірених користувачів...")
                await updater.update_trusted()
                logger.info("✅ Оновлення довірених завершено.")
                await asyncio.sleep(60 * 60 * 2)



        asyncio.create_task(run_trusted_updater())

        # ⬅ Реєстрація роутерів
        dp.include_router(admin_router)
        dp.include_router(inline_router)
        dp.include_router(router)

        logger.info("🚀 Бот запускається...")
        await dp.start_polling(bot, skip_updates=True)

    except Exception as e:
        logger.error(f"❌ Помилка при запуску бота: {e}")

    finally:
        if 'db_manager' in locals():
            await db_manager.close()

        print(f"[DEBUG] Зареєстровані callback-хендлери: {dp.callback_query.outer_middleware}")


if __name__ == "__main__":
    asyncio.run(main())
