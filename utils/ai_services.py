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




import openai
import re
import random

class OpenAIService:
    def __init__(self, api_key):
        self.client = openai.AsyncOpenAI(api_key=api_key)

    def _get_category_emoji(self, category: str) -> str:
        mapping = {
            "догляд за обличчям": "🧴",
            "догляд за тілом": "🧼",
            "догляд за волоссям": "🧖‍♀️",
            "гаджети": "⚙️"
        }
        return mapping.get(category.strip().lower(), "✨")

    def _clean_telegram_text(self, text: str) -> str:
        # Видаляємо markdown форматування
        cleaned = re.sub(r'[*_`]', '', text)
        cleaned = re.sub(r'\[.+?\]\(.+?\)', '', cleaned)
        return cleaned.strip()

    def _select_hashtags(self, data: dict) -> str:
        """Вибирає 3 найкращі хештеги з наявних"""
        all_tags = [
            "#з_любовʼю_відпускаю",
            "#йой_не_моє", 
            "#нюхові_травми",
            "#відкритий_але_живий",
            "#обережно_текстура",
            "#шось_непонятне_на_дотик"
        ]
        
        # Вибираємо 3 випадкові хештеги для варіативності
        selected = random.sample(all_tags, min(3, len(all_tags)))
        return ' '.join(selected)

    def _format_dates_creatively(self, opened_at: str, expire_at: str) -> str:
        """Створює креативний опис дат відкриття та закінчення"""
        try:
            # Витягуємо роки з дат
            opened_year = None
            expire_year = None
            
            # Знаходимо рік у opened_at
            import re
            opened_match = re.search(r'20\d{2}', opened_at)
            if opened_match:
                opened_year = opened_match.group()
            
            # Знаходимо рік у expire_at
            expire_match = re.search(r'20\d{2}', expire_at)
            if expire_match:
                expire_year = expire_match.group()
            
            if opened_year and expire_year:
                years_left = int(expire_year) - 2025  # поточний рік
                if years_left > 0:
                    return f"відкритий {opened_year}, але ще тримається до {expire_year} (живе {years_left} {'рік' if years_left == 1 else 'роки'})"
                elif years_left == 0:
                    return f"відкритий {opened_year}, термін до {expire_year} (останній рік)"
                else:
                    return f"відкритий {opened_year}, термін минув у {expire_year} (але ще живий)"
            elif opened_year:
                return f"відкритий {opened_year}, термін не дихає на спину"
            else:
                # Якщо немає років, робимо креативний опис
                if "закрито" in opened_at.lower():
                    return f"закритий, до {expire_at} (спить як красуня)"
                else:
                    return f"{opened_at}, до {expire_at} (в такому стилі)"
        except:
            return f"{opened_at}, до {expire_at}"

    async def generate_post_text(self, data: dict) -> str:
        """Генерує весь пост через GPT з збереженням структури"""
        
        # Підготовка даних
        emoji = self._get_category_emoji(data['category'])
        formatted_dates = self._format_dates_creatively(
            data.get('opened_at', ''), 
            data.get('expire_at', '')
        )
        hashtags = self._select_hashtags(data)
        
        # Перевіряємо чи є ціна або обмін
        is_sale = bool(data.get('price_buy')) and bool(data.get('price_sell'))
        exchange_option = data.get('exchange_option', '').strip()
        is_exchange = bool(exchange_option and exchange_option.lower() != 'пропустити')

        system_prompt = """Ти адаптуєш дані про косметичний засіб у іронічно-розчарований стиль для продажу б/у косметики.

КРИТИЧНО ВАЖЛИВО - СТРУКТУРА ВИВОДУ:
Структура ОБОВ'ЯЗКОВА (кожен рядок крім першого з "• "):
{emoji} {назва}
• Залишок: {відсоток}% ({метафора})
• Відкрито: {креативний опис дат}
• Чому продаю: {іронічна причина}
• Про засіб: {стилізований опис користувача}
• Шкіра: {стиль типу шкіри}
• Ціна: {реальні цифри + жарт} АБО • Обмін: {стилізована причина обміну + жарт}
• Локація: {місто}, доставка: {доставка з гумором}
{3 хештеги в одному рядку через пробіли}

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

ЦІНА/ОБМІН - ВАЖЛИВО:
- Якщо ПРОДАЖ: "• Ціна: Купувала за X грн, віддаю за Y грн (відпущу в люди за символічну плату)"
- Якщо ОБМІН: "• Обмін: [стилізована причина обміну користувача з жартом]"
- НЕ пиши "ціна з жартом" - пиши РЕАЛЬНІ ЦИФРИ!

ОБМЕЖЕННЯ: Весь текст разом з хештегами ≤950 символів!

ХЕШТЕГИ: Обери 3 з цих хештегів і помісти в ОДНОМУ рядку через пробіли:
#з_любовʼю_відпускаю #йой_не_моє #нюхові_травми #відкритий_але_живий #обережно_текстура #шось_непонятне_на_дотик"""

        user_prompt = f"""Адаптуй ці дані під наш стиль:

ДАНІ:
Назва: {data['title']}
Категорія: {data['category']}
Залишок: {data.get('left_percent', 0)}%
Дати: {formatted_dates}
Причина продажу: {data.get('reason', '')}
Опис користувача: {data.get('user_description', '')}
Тип шкіри: {data.get('skin_type', '')}
Місто: {data.get('city', '')}
Доставка: {data.get('delivery', '')}
{"Ціна покупки: " + str(data.get('price_buy', '')) + " грн, продажу: " + str(data.get('price_sell', '')) + " грн" if is_sale else ""}
{"Обмін на: " + exchange_option if is_exchange else ""}

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
            result = self._clean_telegram_text(result)
            
            # Додаємо емоджі до назви, якщо його немає
            if not result.startswith(emoji):
                lines = result.split('\n')
                if lines[0] and not any(e in lines[0] for e in ['🧴', '🧼', '🧖‍♀️', '⚙️', '✨']):
                    lines[0] = f"{emoji} {lines[0]}"
                    result = '\n'.join(lines)
            
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
        
        is_sale = bool(data.get('price_buy')) and bool(data.get('price_sell'))
        exchange_option = data.get('exchange_option', '').strip()
        is_exchange = bool(exchange_option and exchange_option.lower() != 'пропустити')
        
        lines = [
            f"{emoji} {data['title']}",
            f"• Залишок: {percent}% ({condition})",
            f"• Відкрито: {formatted_dates}",
            f"• Чому продаю: {data.get('reason', 'не моє')}",
            f"• Про засіб: {data.get('user_description', 'засіб з амбіціями')}",
            f"• Шкіра: {data.get('skin_type', 'різна')}"
        ]
        
        if is_sale:
            lines.append(f"• Ціна: {data['price_buy']} → {data['price_sell']} грн")
        elif is_exchange:
            lines.append(f"• Обмін: {exchange_option}")
        
        lines.append(f"• Локація: {data.get('city', '')}, доставка: {data.get('delivery', '')}")
        lines.append(self._select_hashtags(data))
        
        result = '\n'.join(lines)
        return result[:950] if len(result) > 950 else result






    



class GoogleVisionService:
    def __init__(self, service_account_path: str):
        self.client = vision.ImageAnnotatorClient.from_service_account_file(service_account_path)

    async def validate_photo(self, file_id: str, bot) -> bool:
        """Перевірка зображення на чутливий контент через Google Vision API"""
        print("🔍 [Vision] Починаємо перевірку фото...")

        try:
            file = await bot.get_file(file_id)
            file_path = file.file_path
            photo_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"

            print(f"📥 [Vision] Завантаження фото з: {photo_url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as resp:
                    if resp.status != 200:
                        print(f"❌ [Vision] Неможливо завантажити фото. Статус: {resp.status}")
                        return False
                    content = await resp.read()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                temp_file.write(content)
                image_path = temp_file.name

            with open(image_path, "rb") as image_file:
                content = image_file.read()

            image = vision.Image(content=content)
            response = self.client.safe_search_detection(image=image)
            safe = response.safe_search_annotation

            os.remove(image_path)

            if response.error.message:
                print(f"❌ [Vision] Помилка API: {response.error.message}")
                return False

            print("🔎 [Vision] SafeSearch результати:")
            print(f"    adult: {safe.adult.name}")
            print(f"    racy: {safe.racy.name}")
            print(f"    violence: {safe.violence.name}")
            print(f"    spoof: {safe.spoof.name}")
            print(f"    medical: {safe.medical.name}")

            thresholds = ["LIKELY", "VERY_LIKELY"]
            is_inappropriate = (
                safe.adult.name in thresholds or
                safe.violence.name in thresholds or
                safe.racy.name in thresholds
            )

            if is_inappropriate:
                print("⛔️ [Vision] Фото вважається неприйнятним через SafeSearch.")
                return False

            print("✅ [Vision] Фото пройшло перевірку.")
            return True

        except Exception as e:
            print(f"❌ [Vision] Помилка при перевірці: {e}")
            return False


    async def is_background_light(self, file_id: str, bot) -> bool:
        """Визначає, чи фон зображення світлий"""
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

        image = Image.open(image_path).convert("L")
        stat = ImageStat.Stat(image)
        brightness = stat.mean[0]

        os.remove(image_path)

        return brightness > 130

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
                photo=FSInputFile(temp_output_path),  # ✅ передаємо шлях, не обʼєкт
                disable_notification=True
            )
            new_file_id = sent.photo[-1].file_id

            os.remove(temp_input_path)
            os.remove(temp_output_path)

            return new_file_id

        except Exception as e:
            print(f"❌ Помилка при додаванні ватермарки: {e}")
            return file_id
