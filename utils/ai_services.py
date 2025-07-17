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
            "нехай живе у когось іншого",
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
{emoji} *{назва}*
• Залишок: {відсоток}% ({метафора})
• Відкрито: {креативний опис дат}
• Чому продаю: {іронічна причина}
• Про засіб: {стилізований опис користувача}
• Шкіра: {стиль типу шкіри}
{рядок з ціною або обміном - ВСТАВИТИ БЕЗ ЗМІН}
• Локація: {місто}, доставка: {доставка з гумором}

{хештеги в окремому рядку}

ФОРМАТУВАННЯ:
- Назва ОБОВ'ЯЗКОВО в зірочках: *назва продукту*
- Хештеги завжди в окремому рядку в кінці
- Зберігай всі зірочки навколо назви

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
                    # Перевіряємо чи назва вже в зірочках
                    if '*' in lines[0]:
                        lines[0] = f"{emoji} {lines[0]}"
                    else:
                        lines[0] = f"{emoji} *{lines[0]}*"
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
            f"{emoji} *{data['title']}*",  # Назва в зірочках
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
        """Жорстка перевірка зображення на відповідність правилам"""
        print("🔍 [Vision] Починаємо жорстку перевірку фото...")

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

            # 1. Перевірка яскравості та контрасту
            brightness_ok, brightness_reason = self._check_brightness_and_contrast(image_path)
            if not brightness_ok:
                os.remove(image_path)
                return False, brightness_reason

            # 2. Перевірка фону
            background_ok, background_reason = self._check_background_quality(image_path)
            if not background_ok:
                os.remove(image_path)
                return False, background_reason

            # 3. Перевірка через Google Vision API
            vision_ok, vision_reason = await self._check_with_vision_api(content)
            if not vision_ok:
                os.remove(image_path)
                return False, vision_reason

            # 4. Перевірка на частини тіла/обличчя
            body_ok, body_reason = await self._check_body_parts(content)
            if not body_ok:
                os.remove(image_path)
                return False, body_reason

            # 5. Перевірка кольорової гами
            color_ok, color_reason = self._check_color_distribution(image_path)
            if not color_ok:
                os.remove(image_path)
                return False, color_reason

            os.remove(image_path)
            print("✅ [Vision] Фото пройшло всі перевірки.")
            return True, "Фото відповідає вимогам"

        except Exception as e:
            print(f"❌ [Vision] Помилка при перевірці: {e}")
            return False, f"Технічна помилка: {str(e)}"

    def _check_brightness_and_contrast(self, image_path: str) -> tuple[bool, str]:
        """Перевірка яскравості та контрасту"""
        try:
            # Використовуємо OpenCV для більш точної перевірки
            img = cv2.imread(image_path)
            if img is None:
                return False, "Неможливо прочитати зображення"
            
            # Конвертуємо в сірий для аналізу
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Перевірка середньої яскравості
            mean_brightness = np.mean(gray)
            if mean_brightness < 80:  # Занадто темно
                return False, "Зображення занадто темне"
            if mean_brightness > 240:  # Занадто світло
                return False, "Зображення занадто світле"
            
            # Перевірка контрасту
            contrast = np.std(gray)
            if contrast < 30:  # Низький контраст
                return False, "Зображення має низький контраст"
            
            # Перевірка на переекспонування
            overexposed_pixels = np.sum(gray > 250)
            total_pixels = gray.size
            if overexposed_pixels / total_pixels > 0.1:  # Більше 10% переекспонованих пікселів
                return False, "Зображення переекспоноване"
            
            # Перевірка на недоекспонування
            underexposed_pixels = np.sum(gray < 10)
            if underexposed_pixels / total_pixels > 0.1:  # Більше 10% недоекспонованих пікселів
                return False, "Зображення недоекспоноване"
            
            return True, "Яскравість і контраст в нормі"
            
        except Exception as e:
            return False, f"Помилка перевірки яскравості: {str(e)}"

    def _check_background_quality(self, image_path: str) -> tuple[bool, str]:
        """Перевірка якості фону"""
        try:
            img = cv2.imread(image_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Виявлення країв для оцінки складності фону
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            if edge_density > 0.15:  # Занадто багато деталей у фоні
                return False, "Фон занадто складний або захаращений"
            
            # Перевірка однорідності фону
            # Розділяємо зображення на блоки та перевіряємо однорідність
            h, w = gray.shape
            block_size = 50
            uniformity_scores = []
            
            for i in range(0, h - block_size, block_size):
                for j in range(0, w - block_size, block_size):
                    block = gray[i:i+block_size, j:j+block_size]
                    std = np.std(block)
                    uniformity_scores.append(std)
            
            mean_uniformity = np.mean(uniformity_scores)
            if mean_uniformity > 50:  # Фон не однорідний
                return False, "Фон не однорідний"
            
            return True, "Фон відповідає вимогам"
            
        except Exception as e:
            return False, f"Помилка перевірки фону: {str(e)}"

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

    async def _check_body_parts(self, content: bytes) -> tuple[bool, str]:
        """Перевірка на частини тіла через Face Detection та Object Detection"""
        try:
            image = vision.Image(content=content)
            
            # Перевірка на обличчя
            face_response = self.client.face_detection(image=image)
            faces = face_response.face_annotations
            
            if len(faces) > 0:
                return False, "Виявлено обличчя на зображенні"
            
            # Перевірка на об'єкти (включаючи частини тіла)
            object_response = self.client.object_localization(image=image)
            objects = object_response.localized_object_annotations
            
            # Список заборонених об'єктів
            forbidden_objects = [
                "Person", "Human body", "Human face", "Human head", 
                "Human hand", "Human foot", "Human leg", "Human arm",
                "Man", "Woman", "Child", "Baby", "Human eye", "Human hair",
                "Clothing", "Dress", "Shirt", "Pants", "Shoe", "Hat"
            ]
            
            for obj in objects:
                if obj.name in forbidden_objects and obj.score > 0.3:
                    return False, f"Виявлено заборонений об'єкт: {obj.name}"
            
            return True, "Частини тіла не виявлено"
            
        except Exception as e:
            return False, f"Помилка перевірки частин тіла: {str(e)}"

    def _check_color_distribution(self, image_path: str) -> tuple[bool, str]:
        """Перевірка розподілу кольорів"""
        try:
            img = cv2.imread(image_path)
            
            # Перевірка на переважно темні кольори
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            v_channel = hsv[:, :, 2]  # Value channel
            
            # Якщо більше 60% пікселів темні
            dark_pixels = np.sum(v_channel < 60)
            total_pixels = v_channel.size
            
            if dark_pixels / total_pixels > 0.6:
                return False, "Зображення занадто темне (переважають темні кольори)"
            
            # Перевірка на монохромність
            b, g, r = cv2.split(img)
            
            # Якщо стандартне відхилення між каналами мале, то зображення монохромне
            channel_std = np.std([np.mean(b), np.mean(g), np.mean(r)])
            if channel_std < 10:
                return False, "Зображення занадто монохромне"
            
            return True, "Розподіл кольорів прийнятний"
            
        except Exception as e:
            return False, f"Помилка перевірки кольорів: {str(e)}"

    async def is_background_light(self, file_id: str, bot) -> bool:
        """Визначає, чи фон зображення світлий (оновлена версія)"""
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

            # Використовуємо OpenCV для більш точної оцінки
            img = cv2.imread(image_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Аналіз центральної частини як можливого фону
            h, w = gray.shape
            center_region = gray[h//4:3*h//4, w//4:3*w//4]
            brightness = np.mean(center_region)

            os.remove(image_path)
            
            return brightness > 140  # Підвищили поріг для більш світлого фону
            
        except Exception as e:
            print(f"Помилка перевірки фону: {e}")
            return False

    # Решта методів залишаються без змін
    def add_watermark(self, image_path: str, output_path: str, config) -> None:
        """Додає ватермарку на зображення"""
        base = Image.open(image_path).convert("RGBA")
        watermark = Image.open(config.WATERMARK_PATH).convert("RGBA")

        scale_ratio = min(base.size[0] / (4 * watermark.size[0]), 1.0)
        new_size = (int(watermark.size[0] * scale_ratio), int(watermark.size[1] * scale_ratio))
        watermark = watermark.resize(new_size, Image.LANCZOS)

        alpha = watermark.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(config.WATERMARK_OPACITY)
        watermark.putalpha(alpha)

        margin = 10
        if config.WATERMARK_POSITION == "bottom_right":
            position = (base.size[0] - watermark.size[0] - margin, base.size[1] - watermark.size[1] - margin)
        elif config.WATERMARK_POSITION == "bottom_left":
            position = (margin, base.size[1] - watermark.size[1] - margin)
        elif config.WATERMARK_POSITION == "top_right":
            position = (base.size[0] - watermark.size[0] - margin, margin)
        else:
            position = (margin, margin)

        base.paste(watermark, position, watermark)
        base.convert("RGB").save(output_path, "JPEG")

    async def add_watermark_from_file_id(self, file_id: str, bot) -> str:
        """Скачує фото по file_id, додає ватермарк, повертає новий file_id"""
        try:
            config = bot.config
            file = await bot.get_file(file_id)
            photo_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"

            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as resp:
                    if resp.status != 200:
                        return file_id
                    content = await resp.read()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_input:
                temp_input.write(content)
                temp_input_path = temp_input.name

            temp_output_path = temp_input_path.replace(".jpg", "_wm.jpg")

            self.add_watermark(temp_input_path, temp_output_path, config)

            sent = await bot.send_photo(
                chat_id=bot.config.WATERMARK_TEMP_CHAT_ID or bot.config.CHANNEL_ID,
                photo=FSInputFile(temp_output_path),
                disable_notification=True
            )
            new_file_id = sent.photo[-1].file_id

            os.remove(temp_input_path)
            os.remove(temp_output_path)

            return new_file_id

        except Exception as e:
            print(f"❌ Помилка при додаванні ватермарки: {e}")
            return file_id