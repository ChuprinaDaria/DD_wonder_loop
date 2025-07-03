import aiohttp
import logging
import re
import asyncio
import os

logger = logging.getLogger(__name__)

def normalize_phone(phone: str) -> str:
    if not phone or phone.strip() == "":
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10 and digits.startswith("0"):
        return "38" + digits
    elif len(digits) == 12 and digits.startswith("380"):
        return digits
    elif len(digits) == 9:
        return "380" + digits
    return digits if len(digits) >= 9 else None

class TrustedUserUpdater:
    def __init__(self, db_pool, api_url, bot):
        self.pool = db_pool
        self.api_url = api_url.rstrip("/")
        self.bot = bot
        self.api_token = None

    async def fetch_token(self):
        try:
            login = os.getenv("API_LOGIN")
            password = os.getenv("API_PASSWORD")
            logger.debug(f"🔐 Спроба логіну з: {login=}, {password=}")

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.api_url}/auth/", json={
                    "login": login,
                    "password": password
                }) as resp:
                    if resp.status != 200:
                        raise Exception(f"Помилка логіну: {resp.status}")
                    data = await resp.json()
                    if data.get("status") == "OK":
                        self.api_token = data["response"].get("token")
                        logger.info("🔐 Токен успішно отримано")
                    else:
                        msg = data.get("response", {}).get("message", "Невідома помилка")
                        raise Exception(f"Помилка логіну: {msg}")
        except Exception as e:
            logger.error(f"❌ Не вдалося отримати токен: {e}")

    async def fetch_users(self):
        login = os.getenv("API_LOGIN")
        password = os.getenv("API_PASSWORD")
        logger.debug(f"🔐 Авторизація з логіном: {login}, паролем: {password}")

        if not self.api_token:
            await self.fetch_token()
            if not self.api_token:
                return []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.api_url}/users/export/", json={
                    "token": self.api_token
                }) as resp:
                    if resp.status == 401:
                        logger.warning("🔁 Токен недійсний — спроба оновити...")
                        self.api_token = None
                        await self.fetch_token()
                        return await self.fetch_users()

                    if resp.status != 200:
                        raise Exception(f"Помилка HTTP: {resp.status}")

                    data = await resp.json()

                # 🐞 Лог відповіді API
                    logger.debug(f"📦 API відповів: {data}")

                    if data.get("status") != "OK":
                        msg = data.get("response", {}).get("message", "Невідома помилка")
                        raise Exception(f"Статус відповіді API: {data.get('status')} — {msg}")

                    users = data.get("response", {}).get("users", [])
                    logger.info(f"✅ Отримано {len(users)} користувачів з API")
                    return users

        except Exception as e:
            logger.error(f"❌ Помилка при отриманні користувачів з API: {e}")
            return []

    async def update_trusted(self):
        api_users = await self.fetch_users()
        if not api_users:
            logger.warning("⚠️ Не отримано користувачів з API")
            return {"processed": 0, "added": 0, "notified": 0}

        async with self.pool.acquire() as conn:
            processed_count = 0
            added_to_trusted = 0
            updated_existing = 0

            for user in api_users:
                if not isinstance(user, dict):
                    continue

                raw_phone = user.get("phone")
                raw_email = user.get("email")

                normalized_phone = normalize_phone(raw_phone)
                email = raw_email.strip().lower() if raw_email else None

                if not normalized_phone and not email:
                    continue

                processed_count += 1

                # 🔍 Перевірка trusted_exists — без глюків з NULL
                trusted_exists = None

                if normalized_phone and email:
                    trusted_exists = await conn.fetchrow("""
                        SELECT id FROM trusted_users
                        WHERE regexp_replace(phone, '\\D', '', 'g') = regexp_replace($1, '\\D', '', 'g')
                        OR LOWER(email) = LOWER($2)
                    """, normalized_phone, email)

                elif normalized_phone:
                    trusted_exists = await conn.fetchrow("""
                        SELECT id FROM trusted_users
                        WHERE regexp_replace(phone, '\\D', '', 'g') = regexp_replace($1, '\\D', '', 'g')
                    """, normalized_phone)

                elif email:
                    trusted_exists = await conn.fetchrow("""
                        SELECT id FROM trusted_users
                        WHERE LOWER(email) = LOWER($1)
                    """, email)

                if not trusted_exists:
                    await conn.execute("""
                        INSERT INTO trusted_users (phone, email)
                        VALUES ($1, $2)
                    """, raw_phone, raw_email)
                    added_to_trusted += 1

                # 🔁 Оновлюємо статус у users
                await conn.execute("""
                    UPDATE users
                    SET trusted = 'true', daily_limit = 10
                    WHERE trusted = 'false' AND (
                        (regexp_replace(phone, '\\D', '', 'g') = regexp_replace($1, '\\D', '', 'g') AND $1 IS NOT NULL)
                        OR (LOWER(email) = LOWER($2) AND $2 IS NOT NULL)
                    )
                """, normalized_phone, email)

                # 📩 Надсилаємо повідомлення
                updated_user_ids = await conn.fetch("""
                    SELECT telegram_id FROM users
                    WHERE trusted = 'true' AND (
                        (regexp_replace(phone, '\\D', '', 'g') = regexp_replace($1, '\\D', '', 'g') AND $1 IS NOT NULL)
                        OR (LOWER(email) = LOWER($2) AND $2 IS NOT NULL)
                )
                """, normalized_phone, email)

                for user_row in updated_user_ids:
                    if user_row["telegram_id"]:
                        try:
                            await self.bot.send_message(
                                chat_id=user_row["telegram_id"],
                                text="🌟 Ваш статус оновлено! Ви стали довіреним користувачем, Wonder Trust 🎉"
                            )            
                            updated_existing += 1
                        except Exception as e:
                            logger.warning(f"⚠️ Не вдалося надіслати повідомлення {user_row['telegram_id']}: {e}")


            logger.info(f"✅ Оброблено: {processed_count}")
            logger.info(f"➕ Додано до trusted_users: {added_to_trusted}")
            logger.info(f"🔔 Повідомлень надіслано: {updated_existing}")

            return {
                "processed": processed_count,
                "added": added_to_trusted,
                "notified": updated_existing
            }
