#!/usr/bin/env python3
import logging
import re
from datetime import datetime, timedelta
from config import Config
from database import Database
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, JobQueue
from PIL import Image, ImageEnhance, ImageFilter
import easyocr
import numpy as np
from io import BytesIO

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RunningBot:
    def __init__(self):
        self.db = Database()
        self.application = Application.builder().token(Config.BOT_TOKEN).build()
        self.reader = easyocr.Reader(['ru', 'en'])
        self.setup_handlers()
        self.setup_jobs()
    
    def setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("my_stats", self.my_stats))
        self.application.add_handler(CommandHandler("group_stats", self.group_stats))
        self.application.add_handler(CommandHandler("test_weekly_top", self.test_weekly_top))
        self.application.add_handler(CommandHandler("get_chat_id", self.get_chat_id))
        self.application.add_handler(CommandHandler("debug_db", self.debug_db))
        
        self.application.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.GROUPS & filters.Regex(r'#япобегал'),
            self.handle_group_run_message
        ))
        
        self.application.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            self.handle_private_message
        ))
        
        self.application.add_handler(MessageHandler(filters.PHOTO, self.process_image))
    
    def setup_jobs(self):
        """Настройка автоматических заданий"""
        job_queue = self.application.job_queue
        job_queue.run_once(self.send_test_weekly_top, when=timedelta(seconds=60))
    
    async def get_chat_id(self, update: Update, context: CallbackContext):
        """Получить ID чата"""
        chat = update.effective_chat
        await update.message.reply_text(f"ID этого чата: `{chat.id}`", parse_mode='Markdown')
    
    async def debug_db(self, update: Update, context: CallbackContext):
        """Детальная отладочная информация"""
        try:
            debug_info = self.db.debug_info()
            
            message_lines = [
                "🐛 ДЕТАЛЬНАЯ ОТЛАДКА БАЗЫ ДАННЫХ:",
                f"📋 Таблицы: {', '.join(debug_info.get('tables', []))}",
                f"👥 Пользователей: {debug_info.get('users_count', 0)}",
                f"🏃 Всего пробежек: {debug_info.get('runs_count', 0)}",
                "",
                "📊 ПОСЛЕДНИЕ 5 ПРОБЕЖЕК:"
            ]
            
            for run in debug_info.get('recent_runs', []):
                message_lines.append(
                    f"ID:{run[0]} User:{run[1]} Dist:{run[2]} Date:{run[3]}"
                )
            
            # Проверяем конкретно пользователей
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT user_id, first_name FROM users")
            users = cursor.fetchall()
            
            message_lines.extend(["", "👥 ВСЕ ПОЛЬЗОВАТЕЛИ:"])
            for user in users:
                message_lines.append(f"ID:{user[0]} Name:{user[1]}")
            
            await update.message.reply_text("\n".join(message_lines))
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка отладки: {e}")
    
    def extract_distance_from_text(self, message):
        """Извлекает дистанцию из текстового сообщения"""
        clean_message = re.sub(r'#япобегал', '', message, flags=re.IGNORECASE)
        clean_message = re.sub(r'\s+', ' ', clean_message).strip()
        
        patterns = [
            r'(\d+[.,]?\d*)\s*км',
            r'(\d+[.,]?\d*)\s*km',
        ]

        for pattern in patterns:
            match = re.search(pattern, clean_message, re.IGNORECASE)
            if match:
                try:
                    distance_str = match.group(1).replace(',', '.')
                    distance = float(distance_str)
                    if 0.1 <= distance <= 100:
                        return distance
                except ValueError:
                    continue

        return None

    def preprocess_image(self, img):
        """Улучшение качества изображения - ПОЛНАЯ ВЕРСИЯ"""
        img = img.convert('L')
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(3.0)
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(3.0)
        return img

    def parse_time_to_seconds(self, time_str):
        """Парсит время в секунды"""
        if not time_str:
            return None
            
        time_str = time_str.replace('.', ':').replace(';', ':')
        parts = time_str.split(':')
        
        if len(parts) == 3:
            try:
                hours, minutes, seconds = map(int, parts)
                if hours < 24 and minutes < 60 and seconds < 60:
                    return hours * 3600 + minutes * 60 + seconds
            except ValueError:
                return None
                
        elif len(parts) == 2:
            try:
                minutes, seconds = map(int, parts)
                if minutes < 60 and seconds < 60:
                    return minutes * 60 + seconds
            except ValueError:
                return None
                
        return None

    def seconds_to_time_format(self, seconds):
        """Конвертирует секунды в формат ЧЧ:ММ:СС или ММ:СС"""
        if not seconds:
            return None
            
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    def seconds_to_pace_format(self, seconds):
        """Конвертирует секунды в формат темпа ММ:СС"""
        if not seconds:
            return None
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes}:{seconds:02d}"

    def extract_running_data(self, extracted_text):
        """Умное извлечение данных о пробежке с расчетом недостающих значений - ПОЛНАЯ ВЕРСИЯ"""
        logger.info(f"🔍 Распознанный текст: {extracted_text}")
        
        extracted_text = re.sub(r'[<>&]', ' ', extracted_text)
        extracted_text = re.sub(r'\s+', ' ', extracted_text).strip()
        
        distance = None
        time_str = None
        pace_str = None
        time_seconds = None
        pace_seconds = None
        
        # 1. ПОИСК ДИСТАНЦИИ
        distance_patterns = [
            r'(\d+[.,]\d+)\s*km',
            r'(\d+[.,]\d+)\s*км',
            r'(\d+[.,]\d+)km',
            r'(\d+[.,]\d+)км',
            r'расстояние[^\d]*(\d+[.,]\d+)',
            r'дистанция[^\d]*(\d+[.,]\d+)',
        ]
        
        for pattern in distance_patterns:
            match = re.search(pattern, extracted_text, re.IGNORECASE)
            if match:
                try:
                    dist = float(match.group(1).replace(',', '.'))
                    if 0.5 <= dist <= 42.2:
                        distance = dist
                        logger.info(f"✅ Найдена дистанция: {distance} км")
                        break
                except ValueError:
                    continue
        
        # Резервный поиск дистанции
        if not distance:
            number_pattern = r'\b(1[0-5][.,]\d{1,2})\b'
            matches = re.findall(number_pattern, extracted_text)
            for match in matches:
                try:
                    dist = float(match.replace(',', '.'))
                    if 5.0 <= dist <= 20.0:
                        context = extracted_text.lower()
                        if not any(word in context for word in ['пульс', 'калори', 'уд/м', 'kcal']):
                            distance = dist
                            logger.info(f"✅ Найдена дистанция (резерв): {distance} км")
                            break
                except ValueError:
                    continue
        
        # 2. ПОИСК ВРЕМЕНИ
        time_patterns = [
            r'(\d+:\d+:\d+)',
            r'(\d+:\d+)',
            r'общее\s+время[^\d]*(\d+:\d+:\d+)',
            r'время[^\d]*(\d+:\d+:\d+)',
            r'общее\s+время[^\d]*(\d+:\d+)',
            r'время[^\d]*(\d+:\d+)',
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, extracted_text, re.IGNORECASE)
            if match:
                candidate = match.group(1)
                seconds = self.parse_time_to_seconds(candidate)
                if seconds and seconds >= 60:
                    time_str = candidate
                    time_seconds = seconds
                    logger.info(f"✅ Найдено время: {time_str} ({time_seconds} сек)")
                    break
        
        if not time_str:
            all_time_matches = re.findall(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', extracted_text)
            for match in all_time_matches:
                seconds = self.parse_time_to_seconds(match)
                if seconds and seconds >= 180:
                    time_str = match
                    time_seconds = seconds
                    logger.info(f"✅ Найдено время (общий поиск): {time_str}")
                    break
        
        # 3. ПОИСК ТЕМПА
        pace_patterns = [
            (r'(\d{3})"\s*/\s*km', True),
            (r'(\d{3})"\s*/\s*км', True),
            (r'(\d+:\d+)\s*/\s*km', False),
            (r'(\d+:\d+)\s*/\s*км', False),
            (r"(\d+)'(\d+)''?", True),
            (r'средн\.?\s*темп[^\d]*(\d+:\d+)', False),
            (r'средний\s*темп[^\d]*(\d+:\d+)', False),
        ]
        
        for pattern, needs_conversion in pace_patterns:
            match = re.search(pattern, extracted_text, re.IGNORECASE)
            if match:
                if needs_conversion:
                    if pattern.startswith(r'(\d{3})"'):
                        num = match.group(1)
                        if len(num) == 3:
                            minutes = int(num[0])
                            seconds = int(num[1:])
                            if seconds < 60:
                                pace_seconds = minutes * 60 + seconds
                                pace_str = f"{minutes}:{seconds:02d}"
                                logger.info(f"✅ Найден темп (3 цифры): {pace_str}")
                                break
                    elif pattern.startswith(r"(\d+)'(\d+)''?"):
                        minutes, seconds = match.groups()
                        pace_seconds = int(minutes) * 60 + int(seconds)
                        pace_str = f"{minutes}:{seconds}"
                        logger.info(f"✅ Найден темп (минуты'секунды): {pace_str}")
                        break
                else:
                    pace_candidate = match.group(1)
                    pace_seconds_candidate = self.parse_time_to_seconds(pace_candidate)
                    if pace_seconds_candidate and 120 <= pace_seconds_candidate <= 1200:
                        pace_seconds = pace_seconds_candidate
                        pace_str = pace_candidate
                        logger.info(f"✅ Найден темп: {pace_str}")
                        break
        
        # 4. УМНЫЙ РАСЧЕТ НЕДОСТАЮЩИХ ДАННЫХ
        calculated_time = None
        calculated_pace = None
        
        if distance:
            if time_seconds and not pace_seconds:
                pace_seconds = time_seconds / distance
                if 120 <= pace_seconds <= 1200:
                    calculated_pace = self.seconds_to_pace_format(pace_seconds)
                    pace_str = calculated_pace
                    logger.info(f"🧮 ВЫЧИСЛЕН темп: {pace_str} из времени {time_str} и дистанции {distance}км")
            
            elif pace_seconds and not time_seconds:
                time_seconds = pace_seconds * distance
                if 60 <= time_seconds <= 36000:
                    calculated_time = self.seconds_to_time_format(time_seconds)
                    time_str = calculated_time
                    logger.info(f"🧮 ВЫЧИСЛЕНО время: {time_str} из темпа {pace_str} и дистанции {distance}км")
            
            elif not time_seconds and not pace_seconds:
                estimated_pace_seconds = 360
                time_seconds = estimated_pace_seconds * distance
                if 60 <= time_seconds <= 36000:
                    calculated_time = self.seconds_to_time_format(time_seconds)
                    time_str = calculated_time
                    pace_str = "6:00"
                    logger.info(f"🧮 ВЫЧИСЛЕНО примерное время: {time_str} (темп 6:00/км)")
        
        if calculated_time and time_str:
            time_str = f"{time_str} (вычислено)"
        
        if calculated_pace and pace_str:
            pace_str = f"{pace_str} (вычислено)"
        
        logger.info(f"📊 ИТОГОВЫЕ ДАННЫЕ: дистанция={distance}, время={time_str}, темп={pace_str}")
        
        return distance, time_str, pace_str, time_seconds, pace_seconds

    async def process_image(self, update: Update, context: CallbackContext):
        """Обработка изображений - ПОЛНАЯ ВЕРСИЯ"""
        try:
            user = update.effective_user
            logger.info(f"📸 Обработка изображения от пользователя: {user.first_name} (ID: {user.id})")
            
            photo = update.message.photo[-1]
            file_obj = await photo.get_file()
            image_data = await file_obj.download_as_bytearray()
            img = Image.open(BytesIO(image_data))
            
            img = self.preprocess_image(img)
            img_array = np.array(img)
            
            results = self.reader.readtext(img_array, detail=0)
            extracted_text = ' '.join(results)
            
            distance, time_info, pace, time_seconds, pace_seconds = self.extract_running_data(extracted_text)
            
            if distance:
                # ГАРАНТИРОВАННОЕ СОХРАНЕНИЕ ПОЛЬЗОВАТЕЛЯ
                user_saved = self.db.add_user(user.id, user.first_name, user.last_name, user.username)
                if not user_saved:
                    logger.error(f"❌ Не удалось сохранить пользователя {user.id}")
                
                # ГАРАНТИРОВАННОЕ СОХРАНЕНИЕ ПРОБЕЖКИ
                run_id = self.db.add_run(
                    user_id=user.id, 
                    distance=distance,
                    run_time=time_info,
                    pace=pace,
                    run_time_seconds=time_seconds,
                    pace_seconds=pace_seconds
                )
                
                if run_id:
                    message_lines = [
                        "✅ Пробежка записана из изображения!",
                        "",
                        f"🏃 Бегун: {user.first_name}",
                        f"📏 Дистанция: {distance} км",
                    ]
                    
                    if time_info:
                        message_lines.append(f"⏱️ Время: {time_info}")
                    if pace:
                        message_lines.append(f"🏃‍♂️ Темп: {pace}/км")
                    
                    message_lines.extend(["", "Так держать! 💪"])
                    
                    await update.message.reply_text("\n".join(message_lines))
                    
                    logger.info(f"✅ УСПЕХ: Пробежка сохранена для {user.first_name} - {distance} км")
                    
                else:
                    await update.message.reply_text(
                        "❌ Ошибка сохранения пробежки в базу данных\n"
                        "Попробуйте еще раз или напишите текстом: 5 км #япобегал"
                    )
                    logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось сохранить пробежку для {user.id}")
                
            else:
                await update.message.reply_text(
                    "❌ Не удалось распознать пробежку на изображении\n\n"
                    "Попробуйте:\n"
                    "• Более четкое изображение\n"
                    "• Или напишите текстом: 5 км #япобегал"
                )
                logger.warning(f"⚠️ Не распознана пробежка на изображении от {user.first_name}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке изображения: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке изображения\n"
                "Попробуйте отправить текстом: 5 км #япобегал"
            )

    async def handle_group_run_message(self, update: Update, context: CallbackContext):
        """Обработчик сообщений в группах - ГАРАНТИРОВАННОЕ СОХРАНЕНИЕ"""
        try:
            user = update.effective_user
            message_text = update.message.text
            
            logger.info(f"💬 Обработка сообщения от {user.first_name} (ID: {user.id}): {message_text}")
            
            # ГАРАНТИРОВАННОЕ СОХРАНЕНИЕ ПОЛЬЗОВАТЕЛЯ
            user_saved = self.db.add_user(user.id, user.first_name, user.last_name, user.username)
            if not user_saved:
                logger.error(f"❌ Не удалось сохранить пользователя {user.id}")
            
            # Извлекаем дистанцию
            distance = self.extract_distance_from_text(message_text)
            
            if distance:
                # ГАРАНТИРОВАННОЕ СОХРАНЕНИЕ ПРОБЕЖКИ
                run_id = self.db.add_run(user.id, distance)
                
                if run_id:
                    # Отправляем подтверждение в ЛС
                    try:
                        await context.bot.send_message(
                            chat_id=user.id,
                            text=(
                                f"✅ Пробежка записана!\n\n"
                                f"🏃 Бегун: {user.first_name}\n"
                                f"📏 Дистанция: {distance} км\n\n"
                                f"Так держать! 💪"
                            )
                        )
                        logger.info(f"✅ УСПЕХ: Пробежка сохранена для {user.first_name} - {distance} км")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось отправить ЛС пользователю {user.id}: {e}")
                else:
                    logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось сохранить пробежку для {user.id}")
                    
            else:
                logger.warning(f"⚠️ Не найдена дистанция в сообщении от {user.first_name}")
                try:
                    await context.bot.send_message(
                        chat_id=user.id,
                        text=(
                            f"❌ Не могу определить дистанцию\n\n"
                            f"Попробуй формат: 5 км #япобегал\n"
                            f"Или: 5.2 км #япобегал"
                        )
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось отправить сообщение об ошибке: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке пробежки: {e}")

    def get_weekly_top(self, days_back=3):
        """Получает топ бегунов за последние N дней"""
        try:
            top_runners_data, start_date, end_date = self.db.get_weekly_top(days_back)
            
            top_runners = []
            for row in top_runners_data:
                first_name, last_name, username, runs_count, total_distance, avg_distance = row
                name = first_name
                if last_name:
                    name += f" {last_name}"
                if username:
                    name += f" (@{username})"
                
                top_runners.append({
                    'name': name,
                    'runs_count': runs_count,
                    'total_distance': round(total_distance, 1),
                    'avg_distance': round(avg_distance, 1) if avg_distance else 0
                })
            
            logger.info(f"📊 Сформирован топ из {len(top_runners)} бегунов")
            return top_runners, start_date, end_date
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении топа: {e}")
            return [], None, None

    def format_weekly_top_message(self, top_runners, start_date, end_date):
        """Форматирует сообщение с топом бегунов"""
        if not top_runners:
            return "🏃 За этот период пока нет пробежек"
        
        message_lines = [
            "🏆 <b>ТОП БЕГУНОВ</b> 🏆",
            f"📅 Период: {start_date.strftime('%d.%m')} - {end_date.strftime('%d.%m.%Y')}",
            ""
        ]
        
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        for i, runner in enumerate(top_runners):
            if i < len(medals):
                medal = medals[i]
            else:
                medal = f"{i+1}."
            
            message_lines.append(
                f"{medal} <b>{runner['name']}</b>\n"
                f"   🏃 Пробежек: {runner['runs_count']}\n"
                f"   📏 Дистанция: {runner['total_distance']} км\n"
                f"   📐 В среднем: {runner['avg_distance']} км/забег"
            )
            
            if i < len(top_runners) - 1:
                message_lines.append("")
        
        message_lines.extend([
            "",
            "💪 Так держать! Бегайте больше!",
            "",
            "<i>Статистика обновляется автоматически</i>"
        ])
        
        return "\n".join(message_lines)

    async def send_test_weekly_top(self, context: CallbackContext):
        """Отправляет тестовый топ за неделю"""
        try:
            chat_id = Config.get_group_chat_id()
            top_runners, start_date, end_date = self.get_weekly_top(days_back=7)
            message = self.format_weekly_top_message(top_runners, start_date, end_date)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='HTML'
            )
            
            logger.info(f"✅ Тестовый топ отправлен в чат {chat_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке тестового топа: {e}")

    async def test_weekly_top(self, update: Update, context: CallbackContext):
        """Ручная команда для тестирования топа"""
        if update.effective_chat.type != "private":
            return
            
        try:
            chat_id = Config.get_group_chat_id()
            top_runners, start_date, end_date = self.get_weekly_top(days_back=7)
            message = self.format_weekly_top_message(top_runners, start_date, end_date)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='HTML'
            )
            
            await update.message.reply_text("✅ Тестовый топ отправлен в групповой чат!")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при отправке топа: {e}")

    async def start(self, update: Update, context: CallbackContext):
        """Обработчик команды /start"""
        user = update.effective_user
        self.db.add_user(user.id, user.first_name, user.last_name, user.username)
        
        if update.effective_chat.type == "private":
            await update.message.reply_text(
                f"🏃 Привет, {user.first_name}!\n\n"
                f"Я помогу тебе отслеживать твои пробежки!\n\n"
                f"Чтобы записать пробежку, напиши в групповом чате:\n"
                f"5 км #япобегал\n\n"
                f"Или пришли скриншот из бегового приложения.\n\n"
                f"Команды:\n"
                f"/my_stats - моя статистика\n"
                f"/group_stats - статистика группы\n"
                f"/test_weekly_top - тест топа бегунов\n"
                f"/get_chat_id - получить ID чата\n"
                f"/debug_db - отладочная информация"
            )

    async def handle_private_message(self, update: Update, context: CallbackContext):
        """Обработчик личных сообщений"""
        user = update.effective_user
        await update.message.reply_text(
            "Чтобы записать пробежку, напиши в групповом чате:\n"
            "5 км #япобегал\n\n"
            "Или используй команды:\n"
            "/my_stats - моя статистика\n"
            "/group_stats - статистика группы\n"
            "/test_weekly_top - тест топа бегунов\n"
            "/get_chat_id - получить ID чата\n"
            "/debug_db - отладочная информация"
        )

    async def my_stats(self, update: Update, context: CallbackContext):
        """Статистика пользователя"""
        if update.effective_chat.type != "private":
            return
            
        user = update.effective_user
        stats = self.db.get_user_stats(user.id)
        
        if stats['total_runs'] > 0:
            count = stats['total_runs']
            distance = stats['total_distance']
            avg_distance = distance / count
            
            text = (
                f"📊 Статистика {user.first_name}\n\n"
                f"🏃 Пробежек: {count}\n"
                f"📏 Общая дистанция: {distance:.1f} км\n"
                f"📐 Средняя дистанция: {avg_distance:.1f} км"
            )
            await update.message.reply_text(text)
        else:
            await update.message.reply_text(
                "📊 У вас пока нет пробежек\n\n"
                "Напиши в групповом чате: 5 км #япобегал"
            )

    async def group_stats(self, update: Update, context: CallbackContext):
        """Общая статистика"""
        if update.effective_chat.type != "private":
            return
            
        stats = self.db.get_all_stats()
        
        text = (
            f"📊 Общая статистика\n\n"
            f"👥 Бегунов: {stats['active_users']}\n"
            f"🏃 Пробежек: {stats['total_runs']}\n"
            f"📏 Дистанция: {stats['total_distance']:.1f} км"
        )
        
        await update.message.reply_text(text)

    def run(self):
        """Запуск бота"""
        logger.info("🚀 Запускаем бегового бота...")
        try:
            Config.validate()
            self.application.run_polling()
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске бота: {e}")
            raise

if __name__ == "__main__":
    bot = RunningBot()
    bot.run()