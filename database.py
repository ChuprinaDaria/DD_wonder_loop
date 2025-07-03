import asyncio
import asyncpg
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Менеджер бази даних"""
    print("✅ database.py LOADED")

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = None
    
    async def init_db(self):
        """Ініціалізація з'єднання з БД та створення таблиць"""
        self.pool = await asyncpg.create_pool(self.database_url)
        await self.create_tables()
    
    async def close(self):
        """Закриття з'єднання з БД"""
        if self.pool:
            await self.pool.close()

    async def clear_pending_lots(self) -> int:
        """Видалення всіх лотів у статусі 'pending'"""
        async with self.pool.acquire() as conn:
            deleted = await conn.execute("DELETE FROM lots WHERE status = 'pending'")
            logger.info(f"Очистили чергу, видалено: {deleted}")
            return int(deleted.split(" ")[-1])
    
        
    async def delete_rejected_lots(self) -> int:
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM lots WHERE status = 'rejected'")
            return int(result.split()[-1])

    async def create_tables(self):
        """Створення таблиць"""
        async with self.pool.acquire() as conn:
            # Таблиця користувачів
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    phone VARCHAR(20),
                    email VARCHAR(255),
                    trusted VARCHAR(10) DEFAULT 'false',
                    daily_limit INTEGER DEFAULT 5,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    username VARCHAR(255)
                )
            """)
        
            # Таблиця довірених користувачів
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS trusted_users (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(20),
                    email VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        
            # Таблиця лотів
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS lots (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    title VARCHAR(255) NOT NULL,
                    left_percent INTEGER,
                    opened_at VARCHAR(100),
                    expire_at VARCHAR(100),
                    reason TEXT,
                    skin_type VARCHAR(100),
                    price_buy DECIMAL(10,2),
                    price_sell DECIMAL(10,2),
                    category VARCHAR(100),
                    city VARCHAR(100),
                    delivery TEXT,
                    status VARCHAR(50) DEFAULT 'pending',
                    images TEXT[],
                    generated_text TEXT,
                    message_id BIGINT,
                    exchange TEXT,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        
            # Таблиця статистики користувачів
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id),
                    total_posts INTEGER DEFAULT 0,
                    total_sales INTEGER DEFAULT 0,
                    rating DECIMAL(3,2) DEFAULT 0.0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        
            # Таблиця реакцій
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS reactions (
                    id SERIAL PRIMARY KEY,
                    type VARCHAR(50),
                    text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    # === КОРИСТУВАЧІ ===
    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Отримання користувача"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1", telegram_id
            )
            if row:
                return dict(row)
            else:
                logger.warning(f"❗ Користувача з telegram_id={telegram_id} не знайдено")
                return None

    
            
    async def get_all_users(self) -> list[dict]:
        """Отримання всіх користувачів з username"""
        async with self.pool.acquire() as conn:
            try:
                rows = await conn.fetch("""
                    SELECT id AS id, telegram_id, phone, email, trusted, daily_limit, created_at, username
                    FROM users
                    ORDER BY created_at DESC
                """)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"❌ Помилка при отриманні всіх користувачів: {e}")
                return []


    async def find_user_by_email_or_phone(self, identifier: str) -> Optional[Dict]:
        # Перевірка на None або пустий рядок
        if not identifier:
            logger.warning("❗ Передано порожній або None identifier")
            return None
    
        identifier = identifier.strip().lstrip("@")  # ⬅️ прибираємо @ якщо є
    
        # Додаткова перевірка після обробки
        if not identifier:
            logger.warning("❗ Identifier порожній після обробки")
            return None
    
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow("""
                    SELECT id, telegram_id, phone, email, trusted, username
                    FROM users
                    WHERE phone = $1 OR email = $1 OR username = $1
                """, identifier)
                return dict(row) if row else None
            except Exception as e:
                logger.error(f"❌ Помилка при пошуку користувача: {e}")
                return None




    async def set_user_trusted(self, telegram_id: int, trusted: str = 'true'):
        """Позначити користувача як довіреного або навпаки"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    "UPDATE users SET trusted = $1 WHERE telegram_id = $2",
                    trusted, telegram_id
                )
                logger.info(f"✅ Змінено статус trusted={trusted} для користувача {telegram_id}")
            except Exception as e:
                logger.error(f"❌ Не вдалося оновити trusted для {telegram_id}: {e}")




    async def get_telegram_id_by_user_id(self, user_id: int) -> Optional[int]:
        """Отримати telegram_id за user_id"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT telegram_id FROM users WHERE id = $1", user_id
            )
            if row:
                return row["telegram_id"]
            else:
                logger.warning(f"❗ telegram_id не знайдено для user_id={user_id}")
                return None

    async def get_user_rating(self, user_id: int) -> float:
        """Отримання рейтингу користувача. Якщо відсутній — 0.0"""
        query = """
            SELECT rating
            FROM user_stats
            WHERE user_id = $1
        """
        row = await self.pool.fetchrow(query, user_id)
        return float(row['rating']) if row and row['rating'] is not None else 0.0

 

    
    async def create_user(self, telegram_id: int, phone: str, email: str, username: str = None) -> Dict:
        """Створення користувача або повернення існуючого, якщо вже є"""
        is_trusted = await self.check_trusted_user(phone, email)
        is_trusted_str = "true" if is_trusted else "false"  # 🔧 конвертуємо bool → str
        daily_limit = 10 if is_trusted else 5

        async with self.pool.acquire() as conn:
            try:
                # Вставка або оновлення username
                row = await conn.fetchrow("""
                    INSERT INTO users (telegram_id, phone, email, trusted, daily_limit, username)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (telegram_id) DO UPDATE SET
                        phone = EXCLUDED.phone,
                        email = EXCLUDED.email,
                        trusted = EXCLUDED.trusted,
                        daily_limit = EXCLUDED.daily_limit,
                        username = EXCLUDED.username
                    RETURNING *
                """, telegram_id, phone, email, is_trusted_str, daily_limit, username)

                if row:
                    await conn.execute("""
                        INSERT INTO user_stats (user_id, total_posts, total_sales, rating)
                        VALUES ($1, 0, 0, 0.0)
                        ON CONFLICT DO NOTHING
                    """, row['id'])
                    return dict(row)

                # fallback (має бути рідко)
                existing_user = await conn.fetchrow("""
                    SELECT * FROM users WHERE telegram_id = $1
                """, telegram_id)
                return dict(existing_user) if existing_user else None

            except Exception as e:
                logger.error(f"❌ Помилка при створенні користувача {telegram_id}: {e}")
                raise



    async def check_trusted_user(self, phone: str, email: str) -> bool:
        """Перевірка чи є користувач довіреним"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id FROM trusted_users 
                WHERE phone = $1 OR email = $2
            """, phone, email)
            return row is not None
    
    # === ДОВІРЕНІ КОРИСТУВАЧІ ===
    async def update_trusted_users_from_csv(self, csv_data: str):
        """Оновлення довірених користувачів з CSV"""
        try:
            # Парсинг CSV
            import io
            df = pd.read_csv(io.StringIO(csv_data))
            
            async with self.pool.acquire() as conn:
                # Очищення старих записів (опціонально)
                # await conn.execute("DELETE FROM trusted_users")
                
                for _, row in df.iterrows():
                    phone = row.get('phone', '')
                    email = row.get('email', '')
                    
                    # Перевірка чи вже існує
                    exists = await conn.fetchrow("""
                        SELECT id FROM trusted_users 
                        WHERE phone = $1 OR email = $2
                    """, phone, email)
                    
                    if not exists:
                        await conn.execute("""
                            INSERT INTO trusted_users (phone, email)
                            VALUES ($1, $2)
                        """, phone, email)
                
                # Оновлення статусу існуючих користувачів
                await conn.execute("""
                    UPDATE users SET trusted = 'true', daily_limit = 10
                    WHERE phone IN (SELECT phone FROM trusted_users)
                    OR email IN (SELECT email FROM trusted_users)
                """)
                
            logger.info("Довірені користувачі успішно оновлені")
            
        except Exception as e:
            logger.error(f"Помилка при оновленні довірених користувачів: {e}")
            raise

    # === БАН КОРИСТУВАЧІВ ===   
    async def update_user_ban(self, user_id: int, trusted: str):
        """Оновити статус блокування користувача (trusted)"""
        async with self.pool.acquire() as conn:
            query = """
                UPDATE users
                SET trusted = $1
                WHERE id = $2
            """
            await conn.execute(query, trusted, user_id)




    # === ЛОТИ ===
    async def create_lot(self, lot_data: Dict) -> int:
        """Створення лоту"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO lots (
                    user_id, title, left_percent, opened_at, expire_at,
                    reason, skin_type, price_buy, price_sell, category,
                    city, delivery, images, generated_text,
                    exchange, description
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    $9, $10, $11, $12, $13, $14, $15, $16
                )
                RETURNING id
            """,
                lot_data['user_id'], lot_data['title'], lot_data['left_percent'],
                lot_data['opened_at'], lot_data['expire_at'], lot_data['reason'],
                lot_data['skin_type'], lot_data['price_buy'], lot_data['price_sell'],
                lot_data['category'], lot_data['city'], lot_data['delivery'],
                lot_data['images'], lot_data['generated_text'],
                lot_data['exchange'], lot_data['description']
            )

            # Оновлення статистики
            await conn.execute("""
                UPDATE user_stats SET total_posts = total_posts + 1
                WHERE user_id = $1
            """, lot_data['user_id'])

            return row['id']

    
    async def get_user_lots(self, user_id: int) -> List[Dict]:
        """Отримання лотів користувача"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM lots WHERE user_id = $1 ORDER BY created_at DESC
            """, user_id)
            return [dict(row) for row in rows]
    
    async def update_lot_status(self, lot_id: int, status: str):
        """Оновлення статусу лоту"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE lots SET status = $1 WHERE id = $2
            """, status, lot_id)
            
            # Якщо продано - оновлюємо статистику
            if status == 'sold':
                lot = await conn.fetchrow("SELECT user_id FROM lots WHERE id = $1", lot_id)
                if lot:
                    await conn.execute("""
                        UPDATE user_stats SET total_sales = total_sales + 1
                        WHERE user_id = $1
                    """, lot['user_id'])
                    
                    # Перерахунок рейтингу
                    await self.update_user_rating(lot['user_id'])
    
    async def get_lot(self, lot_id: int) -> Optional[Dict]:
        """Отримання лоту за ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM lots WHERE id = $1", lot_id)
            return dict(row) if row else None
    
    async def set_lot_message_id(self, lot_id: int, message_id: int):
        """Встановлення ID повідомлення для лоту"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE lots SET message_id = $1 WHERE id = $2
            """, message_id, lot_id)
    
    async def get_pending_lots(self) -> List[Dict]:
        """Отримання лотів на модерації"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT l.*, u.telegram_id, u.phone, u.email 
                FROM lots l
                JOIN users u ON l.user_id = u.id
                WHERE l.status = 'pending'
                ORDER BY l.created_at ASC
            """)
            return [dict(row) for row in rows]
    
    async def check_daily_limit(self, user_id: int) -> bool:
        """Перевірка денного ліміту користувача"""
        async with self.pool.acquire() as conn:
            # Отримання ліміту
            user = await conn.fetchrow("SELECT daily_limit FROM users WHERE id = $1", user_id)
            if not user:
                return False
            
            # Підрахунок постів за останні 24 години
            yesterday = datetime.now() - timedelta(days=1)
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM lots 
                WHERE user_id = $1 AND created_at > $2
            """, user_id, yesterday)
            
            return count < user['daily_limit']
    

    async def get_lots_by_status(self, status: str) -> List[Dict]:
            """Отримання лотів за статусом"""
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT l.*, u.telegram_id, u.phone, u.email 
                    FROM lots l
                    JOIN users u ON l.user_id = u.id
                    WHERE l.status = $1
                    ORDER BY l.created_at ASC
                """, status)
                return [dict(row) for row in rows]    


    # === СТАТИСТИКА ===
    async def update_user_rating(self, user_id: int):
        """Оновлення рейтингу користувача (від 0 до 5 з округленням)"""
        async with self.pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT total_posts, total_sales FROM user_stats WHERE user_id = $1
            """, user_id)

            if stats and stats['total_posts'] > 0:
                # Розрахунок рейтингу як частка продажів від постів, масштабована на 5
                raw_rating = (stats['total_sales'] / stats['total_posts']) * 5
                rating = round(min(raw_rating, 5.0), 2)

                await conn.execute("""
                    UPDATE user_stats SET rating = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = $2
                """, rating, user_id)

    
    async def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """Отримання статистики користувача"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM user_stats WHERE user_id = $1
            """, user_id)
            return dict(row) if row else None
        
    async def get_user_by_internal_id(self, internal_id: int) -> Optional[Dict]:
        """Отримання користувача за id (не telegram_id)"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1", internal_id
            )
            if row:
                return dict(row)
            else:
                logger.warning(f"❗ Користувача з id={internal_id} не знайдено")
                return None
    
    async def get_general_stats(self) -> Dict:
        """Загальна статистика системи"""
        async with self.pool.acquire() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            total_lots = await conn.fetchval("SELECT COUNT(*) FROM lots")
            total_sold = await conn.fetchval("SELECT COUNT(*) FROM lots WHERE status = 'sold'")
            trusted_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE trusted = 'true'")
            
            return {
                'total_users': total_users,
                'total_lots': total_lots,
                'total_sold': total_sold,
                'trusted_users': trusted_users
            }
    
    async def add_lot_message(self, lot_id: int, message_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO lot_messages (lot_id, message_id) VALUES ($1, $2)",
                lot_id, message_id
            )
    async def get_lot_messages(self, lot_id: int) -> list[int]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT message_id FROM lot_messages WHERE lot_id = $1",
                lot_id
                )
            return [row["message_id"] for row in rows]


    async def delete_lot(self, lot_id: int):
        """Повне видалення лоту з бази даних (PostgreSQL + asyncpg)"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("DELETE FROM lots WHERE id = $1", lot_id)
                logger.info(f"✅ Лот {lot_id} видалено з БД")
        except Exception as e:
            logger.error(f"❌ Помилка при видаленні лоту з БД: {e}")
            raise
