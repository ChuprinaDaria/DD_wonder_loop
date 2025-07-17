import openai
import random
from google.cloud import vision
import aiohttp
import tempfile
import os
from PIL import Image, ImageStat, ImageDraw, ImageFont, ImageEnhance
from aiogram.types import FSInputFile
import re
import asyncio
from aiogram import Bot
from openai import AsyncOpenAI 
import httpx
import cv2
import numpy as np


import openai
import re
import random

class OpenAIService:
    def __init__(self, api_key):
        self.http_client = httpx.AsyncClient()  # ← кастомний клієнт без проксі
        self.client = AsyncOpenAI(
            api_key=api_key,
            http_client=self.http_client
        )

    async def close(self):
        await self.http_client.aclose()  

    def _get_category_emoji(self, category: str) -> str:
        mapping = {
            "догляд за обличчям": "🧴",
            "догляд за тілом": "🧼",
            "догляд за волоссям": "🧖‍♀️",
            "гаджети": "⚙️"
        }
        return mapping.get(category.strip().lower(), "✨")

    def _clean_telegram_text(self, text: str) -> str:
        # НЕ видаляємо зірочки (*) для жирного тексту в Telegram
        cleaned = re.sub(r'[_`]', '', text)  # Видаляємо тільки підкреслення та код
        cleaned = re.sub(r'\[.+?\]\(.+?\)', '', cleaned)  # Видаляємо посилання
        return cleaned.strip()

    def _select_hashtags(self, data: dict) -> str:
        """Вибирає 3 рандомні хештеги з наявних"""
        all_tags = [
            "#з_любовʼю_відпускаю",
            "#йой_не_моє", 
            "#нюхові_травми",
            "#відкритий_але_живий",
            "#обережно_текстура",
            "#шось_непонятне_на_дотик",
            "#пережив_переїзд",
            "#впав_і_подряпався",
            "#йой_чутливі_терміни"
        ]
        
        # Вибираємо 3 випадкові хештеги для варіативності
        selected = random.sample(all_tags, min(3, len(all_tags)))
        return ' '.join(selected)

    def _format_dates_creatively(self, opened_at: str, expire_at: str) -> str:
        """Створює креативний опис дат відкриття та закінчення"""
        try:
            import re
            
            # Витягуємо роки для розрахунків
            opened_year = None
            expire_year = None
            
            # Знаходимо рік у opened_at
            opened_match = re.search(r'20\d{2}', opened_at)
            if opened_match:
                opened_year = int(opened_match.group())
            
            # Знаходимо рік у expire_at
            expire_match = re.search(r'20\d{2}', expire_at)
            if expire_match:
                expire_year = int(expire_match.group())
            
            # Використовуємо оригінальний текст клієнта + креативний жарт
            if opened_year and expire_year:
                years_left = expire_year - 2025  # поточний рік
                
                if years_left > 0:
                    joke = f"живе {years_left} {'рік' if years_left == 1 else 'роки'}"
                elif years_left == 0:
                    joke = "останній рік, тримається"
                else:
                    joke = "термін минув, але ще дихає"
                    
                return f"відкритий {opened_at}, діє до {expire_at} ({joke})"
                
            elif "закрито" in opened_at.lower() or "закрит" in opened_at.lower():
                return f"{opened_at}, до {expire_at} (спить як красуня)"
            
            elif not opened_year and not expire_year:
                # Якщо немає років взагалі
                return f"{opened_at}, до {expire_at} (в такому стилі)"
                
            else:
                # Якщо є тільки один рік
                return f"{opened_at}, до {expire_at} (тримається як може)"
                
        except Exception as e:
            # Фоллбек - повертаємо оригінальний текст
            return f"{opened_at}, до {expire_at}"

    def _determine_sale_or_exchange(self, data: dict) -> tuple[bool, bool]:
        """Визначає чи це продаж чи обмін на основі наявних даних"""
        # Перевіряємо чи є дані про ціни
        has_price_data = (
            data.get('price_buy') is not None and 
            data.get('price_sell') is not None and
            str(data.get('price_buy', '')).strip() != '' and
            str(data.get('price_sell', '')).strip() != ''
        )
        
        # Перевіряємо чи є дані про обмін
        exchange_details = data.get('exchange_details', '').strip()
        has_exchange_data = (
            exchange_details and 
            exchange_details.lower() not in ['пропустити', 'немає', '']
        )
        
        return has_price_data, has_exchange_data

    def _generate_price_line(self, data: dict) -> str:
        """Генерує рядок з ціною"""
        price_buy = data.get('price_buy', '')
        price_sell = data.get('price_sell', '')
        
        # Варіанти дотепних коментарів для ціни
        price_comments = [
            "відпущу в люди за символічну плату",
            "нехай живе у kogось іншого",
            "віддаю майже задарма",
            "хоч щось повернути",
            "краще в добрі руки ніж в шухляду",
            "продаю зі знижкою на розчарування"
        ]
        
        comment = random.choice(price_comments)
        return f"• Ціна: Купувала за {price_buy} грн, віддаю за {price_sell} грн ({comment})"

    def _generate_exchange_line(self, data: dict) -> str:
        """Генерує рядок з обміном"""
        exchange_details = data.get('exchange_details', '').strip()
        
        # Варіанти дотепних коментарів для обміну
        exchange_comments = [
            "може хтось має саме те що треба",
            "бартер як у давні часи",
            "обмін без доплат і нервів",
            "можливо комусь підійде краще",
            "шукаю взаємовигідний варіант"
        ]
        
        comment = random.choice(exchange_comments)
        return f"• Обмін: {exchange_details} ({comment})"

    async def generate_post_text(self, data: dict) -> str:
        """Генерує весь пост через GPT з збереженням структури"""
        
        # Підготовка даних
        emoji = self._get_category_emoji(data['category'])
        formatted_dates = self._format_dates_creatively(
            data.get('opened_at', ''), 
            data.get('expire_at', '')
        )
        hashtags = self._select_hashtags(data)  # Використовуємо рандомні хештеги
        
        # Визначаємо тип операції (продаж чи обмін)
        is_sale, is_exchange = self._determine_sale_or_exchange(data)
        
        # Генеруємо рядок для ціни/обміну
        if is_sale:
            price_exchange_line = self._generate_price_line(data)
        elif is_exchange:
            price_exchange_line = self._generate_exchange_line(data)
        else:
            # Fallback якщо немає ні ціни ні обміну
            price_exchange_line = "• Ціна: договірна (пишіть, домовимося)"

        system_prompt = """Ти адаптуєш дані про косметичний засіб у іронічно-розчарований стиль для продажу б/у косметики.

КРИТИЧНО ВАЖЛИВО - СТРУКТУРА ВИВОДУ:
Структура ОБОВ'ЯЗКОВА (кожен рядок крім першого з "• "):
{emoji} {назва}
• Залишок: {відсоток}% ({метафора})
• Відкрито: {креативний опис дат}
• Чому продаю: {іронічна причина}
• Про засіб: {стилізований опис користувача}
• Шкіра: {стиль типу шкіри}
{рядок з ціною або обміном - ВСТАВИТИ БЕЗ ЗМІН}
• Локація: {місто}, доставка: {доставка з гумором}

{хештеги в окремому рядку}

ФОРМАТУВАННЯ:
- Назва БЕЗ зірочок: {назва продукту}
- Хештеги завжди в окремому рядку в кінці
- Не використовувати зірочки навколо назви

СТИЛЬ:
- Іронія та легке розчарування
- Персоналізація ("моя шкіра", "особисто мене")
- Метафори з життя
- Гумор без спотворення фактів
- Збереження всієї фактичної інформації

МЕТАФОРИ ДЛЯ ЗАЛИШКУ:
95-100%: "стояла як запаска", "нова, але не зійшлись характерами"
90-95%: "все ще бойова", "майже недоторкана"
80-90%: "відкривала обережно", "пару разів спробувала"
70-80%: "мазалась декілька раз", "ще пахне інструкцією"
60-70%: "трішки користувалась", "ще нормально"
40-60%: "десь під половину", "є що використати"
20-40%: "ще є життя", "не критично"
10-20%: "не на старті, але й не в архіві"
5-10%: "банка не порожня", "залишилось на спомин"
<5%: "мінімалочка", "символічно"

ТИПИ ШКІРИ (для поля "• Шкіра:"):
- суха: "суха, як чат у робочу суботу"
- жирна: "жирна, але намагається триматись"
- змішана: "змішана, як настрій у понеділок"  
- чутлива: "чутлива, але без драми"
- нормальна: "нормальна (рідкість у наш час)"

ДАТИ: Обов'язково адаптуй дати з гумором:
- "відкритий 2023, але ще тримається до 2026" (зміни роки на ті що надані)
- "живе ще 3 роки" (рахуй різницю)
- "відкритий рік тому, термін ще не дихає на спину"

ЛОКАЦІЯ: Обов'язково додай гумористичний коментар:
- "Одеса, доставка: 📦 Нова Пошта (як завжди)"
- "Київ, доставка: 📮 Укрпошта (коли дочекаємось)"
- "Львів, доставка: 🚚 будь-яка (аби дійшла)"

ЧОМУ ПРОДАЮ: Обов'язково адаптуй причину з іронією:
- "Не користуюсь" → "стоїть і дивиться на мене з докором"
- "Набрид" → "наші стосунки зайшли в глухий кут"
- "Не моє" → "не зійшлись характерами з першого дотику"

ПРО ЗАСІБ: НЕ вигадуй рекламний текст! Стилізуй ТЕ, ЩО НАПИСАВ КОРИСТУВАЧ:
- Якщо користувач написав "Добрий крем для сухої шкіри" → "крем з амбіціями для сухої шкіри (не для моєї)"
- Якщо користувач написав "Сироватка з вітаміном С" → "сироватка з вітаміном С і великими планами"
- ЗАВЖДИ зберігай факти користувача, тільки додавай гумор

ВАЖЛИВО: Рядок з ціною/обміном ВСТАВЛЯЙ БЕЗ ЖОДНИХ ЗМІН!

ОБМЕЖЕННЯ: Весь текст разом з хештегами ≤950 символів!"""

        user_prompt = f"""Адаптуй ці дані під наш стиль:

ДАНІ:
Назва: {data['title']}
Категорія: {data['category']}
Залишок: {data.get('left_percent', 0)}%
Дати: {formatted_dates}
Причина продажу: {data.get('reason', '')}
Опис користувача: {data.get('description', '')}
Тип шкіри: {data.get('skin_type', '')}
Місто: {data.get('city', '')}
Доставка: {data.get('delivery', '')}

РЯДОК ЦІНИ/ОБМІНУ (вставити БЕЗ ЗМІН):
{price_exchange_line}

ХЕШТЕГИ (вставити в кінці в окремому рядку):
{hashtags}

Поверни ТІЛЬКИ адаптований текст у вказаній структурі, БЕЗ пояснень."""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=800,
                temperature=0.7  # Баланс між творчістю та стабільністю
            )
            
            result = response.choices[0].message.content.strip()
            
            # НЕ очищаємо зірочки для жирного тексту
            result = re.sub(r'[_`]', '', result)  # Видаляємо тільки підкреслення та код
            result = re.sub(r'\[.+?\]\(.+?\)', '', result)  # Видаляємо посилання
            
            # Додаємо емоджі до назви, якщо його немає
            if not result.startswith(emoji):
                lines = result.split('\n')
                if lines[0] and not any(e in lines[0] for e in ['🧴', '🧼', '🧖‍♀️', '⚙️', '✨']):
                    # Додаємо емоджі БЕЗ зірочок
                    lines[0] = f"{emoji} {data['title']}"
                    result = '\n'.join(lines)
            
            # Перевіряємо чи хештеги в окремому рядку в кінці
            if hashtags not in result:
                result += f"\n\n{hashtags}"
            
            # Перевіряємо довжину та скорочуємо якщо потрібно
            if len(result) > 950:
                lines = result.split('\n')
                # Скорочуємо опис засобу якщо потрібно
                for i, line in enumerate(lines):
                    if line.startswith('• Про засіб:') and len(result) > 950:
                        # Скорочуємо опис
                        desc_part = line.split(':', 1)[1].strip()
                        if len(desc_part) > 50:
                            desc_part = desc_part[:47] + '...'
                            lines[i] = f"• Про засіб: {desc_part}"
                            result = '\n'.join(lines)
                            break
                
                # Якщо все ще довгий, обрізаємо в кінці
                if len(result) > 950:
                    result = result[:947] + '...'
            
            return result
            
        except Exception as e:
            print(f"❌ Error generating post: {e}")
            return self._generate_fallback_post(data)

    def _generate_fallback_post(self, data: dict) -> str:
        """Резервний метод генерації поста"""
        emoji = self._get_category_emoji(data['category'])
        formatted_dates = self._format_dates_creatively(
            data.get('opened_at', ''), 
            data.get('expire_at', '')
        )
        
        # Базова метафора для залишку
        percent = int(data.get('left_percent', 0))
        if percent >= 95:
            condition = "стояла як запаска, але не зійшлись характерами"
        elif percent >= 80:
            condition = "відкривала обережно"
        elif percent >= 50:
            condition = "десь під половину"
        elif percent >= 20:
            condition = "ще є життя"
        else:
            condition = "залишилось на спомин"
        
        # Визначаємо тип операції
        is_sale, is_exchange = self._determine_sale_or_exchange(data)
        
        lines = [
            f"{emoji} {data['title']}",  # Назва БЕЗ зірочок
            f"• Залишок: {percent}% ({condition})",
            f"• Відкрито: {formatted_dates}",
            f"• Чому продаю: {data.get('reason', 'не моє')}",
            f"• Про засіб: {data.get('description', 'засіб з амбіціями')}",
            f"• Шкіра: {data.get('skin_type', 'різна')}"
        ]
        
        # Додаємо рядок з ціною або обміном
        if is_sale:
            lines.append(self._generate_price_line(data))
        elif is_exchange:
            lines.append(self._generate_exchange_line(data))
        else:
            lines.append("• Ціна: договірна (пишіть, домовимося)")
        
        lines.append(f"• Локація: {data.get('city', '')}, доставка: {data.get('delivery', '')}")
        
        # Додаємо порожній рядок та хештеги
        lines.append("")
        lines.append(self._select_hashtags(data))
        
        result = '\n'.join(lines)
        return result[:950] if len(result) > 950 else result






    


class GoogleVisionService:
    def __init__(self, service_account_path: str):
        self.client = vision.ImageAnnotatorClient.from_service_account_file(service_account_path)

    async def validate_photo(self, file_id: str, bot) -> tuple[bool, str]:
        """Перевірка зображення на відповідність правилам для товарів"""
        print("🔍 [Vision] Починаємо перевірку фото товару...")

        try:
            file = await bot.get_file(file_id)
            file_path = file.file_path
            photo_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"

            print(f"📥 [Vision] Завантаження фото з: {photo_url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as resp:
                    if resp.status != 200:
                        print(f"❌ [Vision] Неможливо завантажити фото. Статус: {resp.status}")
                        return False, "Помилка завантаження"
                    content = await resp.read()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                temp_file.write(content)
                image_path = temp_file.name

            # 1. Перевірка базової якості зображення
            quality_ok, quality_reason = self._check_image_quality(image_path)
            if not quality_ok:
                os.remove(image_path)
                return False, quality_reason

            # 2. Перевірка через Google Vision API на неприпустимий контент
            vision_ok, vision_reason = await self._check_with_vision_api(content)

            if not vision_ok:
                os.remove(image_path)
                return False, vision_reason

            # 3. Перевірка на людей/обличчя
            people_ok, people_reason = await self._check_for_people(content)
            if not people_ok:
                os.remove(image_path)
                return False, people_reason

            os.remove(image_path)
            print("✅ [Vision] Фото пройшло всі перевірки.")
            return True, "Фото відповідає вимогам"

        except Exception as e:
            print(f"❌ [Vision] Помилка при перевірці: {e}")
            return False, f"Технічна помилка: {str(e)}"
        
    async def _check_with_vision_api(self, content: bytes) -> tuple[bool, str]:
        """Перевірка через Google Vision API з жорсткими правилами"""
        try:
            image = vision.Image(content=content)
            response = self.client.safe_search_detection(image=image)
            safe = response.safe_search_annotation

            if response.error.message:
                return False, f"Помилка API: {response.error.message}"

            print("🔎 [Vision] SafeSearch результати:")
            print(f"    adult: {safe.adult.name}")
            print(f"    racy: {safe.racy.name}")
            print(f"    violence: {safe.violence.name}")
            print(f"    spoof: {safe.spoof.name}")
            print(f"    medical: {safe.medical.name}")

            # Жорсткі правила - навіть "POSSIBLE" не пропускаємо
            strict_thresholds = ["POSSIBLE", "LIKELY", "VERY_LIKELY"]
            
            if safe.adult.name in strict_thresholds:
                return False, "Виявлено контент для дорослих"
            if safe.racy.name in strict_thresholds:
                return False, "Виявлено провокативний контент"
            if safe.violence.name in strict_thresholds:
                return False, "Виявлено насильницький контент"
            if safe.medical.name in ["LIKELY", "VERY_LIKELY"]:
                return False, "Виявлено медичний контент"
            
            return True, "SafeSearch пройдено"
            
        except Exception as e:
            return False, f"Помилка Vision API: {str(e)}"

    def _check_image_quality(self, image_path: str) -> tuple[bool, str]:
        """Базова перевірка якості зображення"""
        try:
            img = cv2.imread(image_path)
            if img is None:
                return False, "Неможливо прочитати зображення"
            
            # Перевірка розміру
            height, width = img.shape[:2]
            if width < 200 or height < 200:
                return False, "Зображення занадто мале"
            
            # Конвертуємо в сірий для базової перевірки
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Перевірка на повністю чорне зображення
            if np.max(gray) < 30:
                return False, "Зображення занадто темне"
            
            # Перевірка на повністю біле зображення
            if np.min(gray) > 240:
                return False, "Зображення занадто світле"
            
            # Перевірка на розмитість
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            if laplacian_var < 50:
                return False, "Зображення занадто розмите"
            
            # Покращена перевірка на темний фон
            is_dark_bg, dark_reason = self._check_dark_background(img)
            if is_dark_bg:
                return False, dark_reason
            
            return True, "Якість зображення прийнятна"
            
        except Exception as e:
            return False, f"Помилка перевірки якості: {str(e)}"

    def _check_dark_background(self, img) -> tuple[bool, str]:
        """Перевірка на темний фон з урахуванням кольорів"""
        try:
            h, w = img.shape[:2]
            
            # Аналізуємо кути зображення як можливий фон
            corners = [
                img[0:h//3, 0:w//3],  # верхній лівий
                img[0:h//3, 2*w//3:w],  # верхній правий
                img[2*h//3:h, 0:w//3],  # нижній лівий
                img[2*h//3:h, 2*w//3:w]  # нижній правий
            ]
            
            # Додатково аналізуємо краї
            edges = [
                img[0:h//10, :],  # верхній край
                img[9*h//10:h, :],  # нижній край
                img[:, 0:w//10],  # лівий край
                img[:, 9*w//10:w]  # правий край
            ]
            
            all_regions = corners + edges
            
            dark_regions = 0
            total_regions = len(all_regions)
            
            for region in all_regions:
                # Конвертуємо в HSV для кращого аналізу яскравості
                hsv_region = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
                
                # Витягуємо канал яскравості (V в HSV)
                brightness = hsv_region[:, :, 2]
                avg_brightness = np.mean(brightness)
                
                # Також перевіряємо RGB канали окремо
                b_channel = np.mean(region[:, :, 0])  # Blue
                g_channel = np.mean(region[:, :, 1])  # Green  
                r_channel = np.mean(region[:, :, 2])  # Red
                
                # Середня яскравість RGB
                rgb_brightness = (b_channel + g_channel + r_channel) / 3
                
                # Перевіряємо на темність по різним критеріям
                is_dark = (
                    avg_brightness < 80 or  # HSV яскравість
                    rgb_brightness < 70 or  # RGB яскравість
                    (max(b_channel, g_channel, r_channel) < 90)  # Найяскравіший канал
                )
                
                if is_dark:
                    dark_regions += 1
            
            # Якщо більше 60% регіонів темні - вважаємо фон темним
            if dark_regions / total_regions > 0.6:
                return True, "Виявлено темний фон"
            
            # Додаткова перевірка на загальну темність всього зображення
            hsv_full = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            overall_brightness = np.mean(hsv_full[:, :, 2])
            
            if overall_brightness < 60:
                return True, "Зображення загалом занадто темне"
            
            return False, "Фон достатньо світлий"
            
        except Exception as e:
            return True, f"Помилка перевірки фону: {str(e)}"

    async def is_background_light(self, file_id: str, bot) -> bool:
        """Визначає, чи фон зображення світлий (покращена версія)"""
        try:
            file = await bot.get_file(file_id)
            file_path = file.file_path
            photo_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"

            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as resp:
                    if resp.status != 200:
                        return False
                    content = await resp.read()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                temp_file.write(content)
                image_path = temp_file.name

            img = cv2.imread(image_path)
            
            # Використовуємо нашу покращену функцію перевірки
            is_dark, _ = self._check_dark_background(img)
            
            os.remove(image_path)
            
            return not is_dark  # Повертаємо True, якщо фон НЕ темний
            
        except Exception as e:
            print(f"Помилка перевірки фону: {e}")
            return False