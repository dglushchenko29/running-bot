#!/usr/bin/env python3
import logging
import re
from datetime import datetime
from config import Config
from database import Database
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
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
        # Инициализируем EasyOCR один раз при запуске
        self.reader = easyocr.Reader(['ru', 'en'])
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        # Обработчики команд
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("my_stats", self.my_stats))
        self.application.add_handler(CommandHandler("group_stats", self.group_stats))
        
        # Обработчик ВСЕХ сообщений в группах (обычных и отредактированных)
        self.application.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.GROUPS & filters.Regex(r'#япобегал'),
            self.handle_group_run_message
        ))
        
        # Обработчик любых сообщений в личных чатах
        self.application.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            self.handle_private_message
        ))
        
        # Обработчик для изображений
        self.application.add_handler(MessageHandler(filters.PHOTO, self.process_image))
    
    def extract_distance(self, message):
        """
        Извлекает дистанцию из сообщения с хэштегом #япобегал
        Поддерживает форматы: '5 км', '5км', '5.2 км', '5.2км' и т.д.
        """
        # Убираем хэштег и лишние пробелы
        clean_message = re.sub(r'#япобегал', '', message, flags=re.IGNORECASE)
        clean_message = re.sub(r'\s+', ' ', clean_message).strip()
        
        # Паттерны для поиска дистанции
        patterns = [
            r'(\d+[.,]?\d*)\s*км',        # 5 км, 5.2 км, 5,2 км
            r'(\d+[.,]?\d*)\s*km',        # 5 km, 5.2 km
            r'(\d+[.,]?\d*)\s*километр',  # 5 километр
            r'(\d+[.,]?\d*)\s*kilometer', # 5 kilometer
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

        # Если не нашли по паттернам, ищем просто числа
        numbers = re.findall(r'\d+[.,]?\d*', clean_message)
        for num_str in numbers:
            try:
                distance = float(num_str.replace(',', '.'))
                if 0.1 <= distance <= 100:
                    return distance
            except ValueError:
                continue

        return None

    def preprocess_image(self, img):
        """Улучшение качества изображения для лучшего распознавания"""
        # Конвертируем в grayscale
        img = img.convert('L')
        
        # Увеличиваем контраст
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        
        # Увеличиваем резкость
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)
        
        # Немного увеличиваем яркость
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.1)
        
        return img

    def extract_running_data(self, extracted_text):
        """
        Основная функция извлечения данных о пробежке из распознанного текста
        """
        logger.info(f"Распознанный текст: {extracted_text}")
        
        # Очистка и нормализация текста
        extracted_text = extracted_text.replace('|', '/').replace('*', ':')
        extracted_text = extracted_text.replace('"', "'")
        extracted_text = re.sub(r'\s+', ' ', extracted_text).strip()
        
        # Все найденные кандидаты на дистанцию, время и темп
        distance_candidates = []
        time_candidates = []
        pace_candidates = []
        
        # ПАТТЕРНЫ ДЛЯ ДИСТАНЦИИ (приоритет по порядку)
        distance_patterns = [
            # Форматы с единицами измерения (высший приоритет)
            (r'(\d+[.,]\d+)\s*[kкKК][mмMМ]', 1.0),  # 15,04 км, 2.86 km
            (r'(\d+)\s*[kкKК][mмMМ]', 0.9),         # 15 км, 5 km
            (r'расстояние[^\d]*(\d+[.,]\d+)', 0.95), # расстояние 15,04
            (r'дистанция[^\d]*(\d+[.,]\d+)', 0.95),  # дистанция 15,04
            
            # Числа с плавающей точкой в контексте (средний приоритет)
            (r'\b(\d+[.,]\d+)\b', 0.7),             # любые числа с запятой/точкой
            
            # Целые числа (низкий приоритет)
            (r'\b(\d{2,3})\b', 0.3),                # 2-3 значные числа
        ]
        
        # ПАТТЕРНЫ ДЛЯ ВРЕМЕНИ
        time_patterns = [
            r'(\d+:\d+:\d+)',                       # 1:43:08, 0:24:13
            r'(\d+:\d+)',                           # 29:21, 24:13
            r'время[^\d]*(\d+:\d+(?::\d+)?)',       # время 1:43:08
        ]
        
        # ПАТТЕРНЫ ДЛЯ ТЕМПА
        pace_patterns = [
            (r"(\d+)'(\d+)''?", 1.0),               # 06'51", 8'21
            (r'(\d+:\d+)\s*/\s*[kкKК][mмMМ]', 0.9), # 6:51 /км
            (r'темп[^\d]*(\d+:\d+)', 0.8),          # темп 6:51
        ]
        
        # Поиск дистанции с приоритетами
        for pattern, priority in distance_patterns:
            matches = re.finditer(pattern, extracted_text, re.IGNORECASE)
            for match in matches:
                try:
                    distance_str = match.group(1).replace(',', '.')
                    distance = float(distance_str)
                    
                    # Фильтруем разумные значения
                    if 0.1 <= distance <= 100:
                        # Проверяем контекст - избегаем чисел из названий мест
                        context = extracted_text[max(0, match.start()-20):match.end()+20]
                        context_lower = context.lower()
                        
                        # Игнорируем числа из географических названий
                        geographic_indicators = ['район', 'деревня', 'улица', 'проспект', 
                                               'область', 'город', 'р-н', 'регион']
                        if not any(indicator in context_lower for indicator in geographic_indicators):
                            distance_candidates.append({
                                'value': distance,
                                'priority': priority,
                                'context': context,
                                'match': match.group()
                            })
                except ValueError:
                    continue
        
        # Поиск времени
        for pattern in time_patterns:
            matches = re.finditer(pattern, extracted_text)
            for match in matches:
                time_str = match.group(1)
                # Проверяем валидность формата времени
                time_parts = time_str.split(':')
                if len(time_parts) >= 2 and all(part.isdigit() for part in time_parts[:2]):
                    time_candidates.append(time_str)
        
        # Поиск темпа
        for pattern, priority in pace_patterns:
            matches = re.finditer(pattern, extracted_text)
            for match in matches:
                if len(match.groups()) == 2:
                    # Формат типа 06'51"
                    minutes, seconds = match.groups()
                    pace_str = f"{minutes}:{seconds}"
                else:
                    pace_str = match.group(1)
                pace_candidates.append(pace_str)
        
        # ВЫБОР НАИЛУЧШИХ КАНДИДАТОВ
        
        # Выбор дистанции - берем с наивысшим приоритетом
        final_distance = None
        if distance_candidates:
            # Сортируем по приоритету и значению (предпочитаем бОльшие числа с десятичной частью)
            distance_candidates.sort(key=lambda x: (
                x['priority'], 
                x['value'] if '.' in str(x['value']) else x['value'] - 0.1
            ), reverse=True)
            
            final_distance = distance_candidates[0]['value']
            logger.info(f"Выбрана дистанция: {final_distance} км из кандидатов: {[c['value'] for c in distance_candidates]}")
        
        # Выбор времени - берем самое длинное (скорее всего полное время)
        final_time = None
        if time_candidates:
            time_candidates.sort(key=lambda x: len(x), reverse=True)
            final_time = time_candidates[0]
        
        # Выбор темпа
        final_pace = pace_candidates[0] if pace_candidates else None
        
        # РАСШИРЕННЫЙ ПОИСК ДЛЯ СЛОЖНЫХ ФОРМАТОВ
        
        # Если не нашли дистанцию, ищем комбинированные паттерны
        if not final_distance:
            combined_patterns = [
                # Паттерн для Samsung Health: "1:43:08 15,04 км 06'51""
                r'(\d+:\d+:\d+)\s+(\d+[.,]\d+)\s*[kкKК]?[mмMМ]?\s+(\d+\'\d+)',
                # Паттерн для часов: "2.86 km 0:24:13 8'21"
                r'(\d+[.,]\d+)\s*[kкKК]?[mмMМ]?\s+(\d+:\d+:\d+)\s+(\d+\'\d+)',
                # Более общие паттерны
                r'(\d+[.,]\d+)\s*[kкKК]?[mмMМ]?\s+(\d+:\d+(?::\d+)?)\s+(\d+[:]\d+)',
            ]
            
            for pattern in combined_patterns:
                match = re.search(pattern, extracted_text, re.IGNORECASE)
                if match:
                    logger.info(f"Найден комбинированный паттерн: {match.groups()}")
                    try:
                        # Вторая группа обычно дистанция
                        distance_str = match.group(2).replace(',', '.')
                        candidate_distance = float(distance_str)
                        if 0.1 <= candidate_distance <= 100:
                            final_distance = candidate_distance
                            if not final_time:
                                final_time = match.group(1)
                            if not final_pace and len(match.groups()) > 2:
                                final_pace = match.group(3).replace("'", ":")
                            break
                    except (ValueError, IndexError):
                        continue
        
        # ВЫЧИСЛЕНИЕ ТЕМПА ИЗ ВРЕМЕНИ И ДИСТАНЦИИ
        calculated_pace = None
        if final_distance and final_time and not final_pace:
            try:
                # Парсим время
                time_parts = final_time.split(':')
                if len(time_parts) == 3:  # ЧЧ:ММ:СС
                    hours, minutes, seconds = map(int, time_parts)
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                elif len(time_parts) == 2:  # ММ:СС
                    minutes, seconds = map(int, time_parts)
                    total_seconds = minutes * 60 + seconds
                else:
                    total_seconds = 0
                
                if total_seconds > 0 and final_distance > 0:
                    # Вычисляем темп в минутах на км
                    pace_seconds_per_km = total_seconds / final_distance
                    pace_minutes = int(pace_seconds_per_km // 60)
                    pace_seconds = int(pace_seconds_per_km % 60)
                    calculated_pace = f"{pace_minutes}:{pace_seconds:02d}"
                    logger.info(f"Вычислен темп: {calculated_pace} из времени {final_time} и дистанции {final_distance}км")
            except Exception as e:
                logger.error(f"Ошибка вычисления темпа: {e}")
        
        # Используем вычисленный темп, если не нашли распознанный
        final_pace = final_pace or calculated_pace
        
        # Форматирование темпа
        if final_pace and "'" in final_pace:
            final_pace = final_pace.replace("'", ":").replace('"', '')
        
        return final_distance, final_time, final_pace

    async def process_image(self, update: Update, context: CallbackContext):
        """Распознавание текста на изображении с помощью EasyOCR"""
        try:
            # Получаем изображение
            photo = update.message.photo[-1]
            file_obj = await photo.get_file()
            image_data = await file_obj.download_as_bytearray()
            img = Image.open(BytesIO(image_data))
            
            # Улучшаем качество изображения
            img = self.preprocess_image(img)
            
            # Конвертируем в numpy array для EasyOCR
            img_array = np.array(img)
            
            # Распознаем текст с помощью EasyOCR
            results = self.reader.readtext(img_array, detail=0)
            extracted_text = ' '.join(results)
            
            # Извлекаем данные о пробежке
            distance, time_info, pace = self.extract_running_data(extracted_text)
            
            if distance:
                # Сохраняем данные в базу
                current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                user = update.effective_user
                self.db.add_user(user.id, user.first_name, user.last_name, user.username)
                run_id = self.db.add_run(user.id, distance)
                
                # Формируем сообщение
                message_text = (
                    f"✅ <b>Пробежка записана из изображения!</b>\n\n"
                    f"🏃 Бегун: {user.first_name}\n"
                    f"📏 Дистанция: {distance} км\n"
                )
                
                if time_info:
                    message_text += f"⏱️ Время: {time_info}\n"
                if pace:
                    # Форматируем темп для отображения
                    if ":" in pace:
                        pace_parts = pace.split(":")
                        if len(pace_parts) == 2:
                            pace_display = f"{pace_parts[0]}:{pace_parts[1]}/км"
                        else:
                            pace_display = f"{pace}/км"
                    else:
                        pace_display = f"{pace}/км"
                    message_text += f"🏃‍♂️ Темп: {pace_display}\n"
                
                message_text += f"\nТак держать! 💪"
                
                await update.message.reply_text(
                    message_text,
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode='HTML'
                )
                
                logger.info(f"Пробежка записана из изображения: {user.first_name} - {distance} км")
                
            else:
                logger.warning(f"Не удалось распознать дистанцию. Текст: {extracted_text}")
                
                # Анализ для отладки
                numbers = re.findall(r'\d+[.,]?\d*', extracted_text)
                logger.info(f"Найденные числа: {numbers}")
                
                await update.message.reply_text(
                    f"❌ <b>Не удалось распознать пробежку на изображении</b>\n\n"
                    f"Распознанный текст:\n<code>{extracted_text[:500]}...</code>\n\n"
                    f"Попробуй:\n"
                    f"• Более четкое изображение\n"
                    f"• Или напиши текстом: <code>5 км #япобегал</code>",
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode='HTML'
                )
                
        except Exception as e:
            logger.error(f"Ошибка при обработке изображения: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке изображения",
                reply_markup=ReplyKeyboardRemove()
            )

    async def start(self, update: Update, context: CallbackContext):
        """Обработчик команды /start"""
        user = update.effective_user
        chat = update.effective_chat
        
        # Добавляем пользователя в БД
        self.db.add_user(user.id, user.first_name, user.last_name, user.username)
        
        if chat.type == "private":
            await update.message.reply_text(
                f"🏃 Привет, {user.first_name}!\n\n"
                f"Я помогу тебе отслеживать твои пробежки! 🏃‍♂️\n\n"
                f"Чтобы записать пробежку, напиши в групповом чате:\n"
                f"<code>5 км #япобегал</code>\n\n"
                f"Также можешь присылать фото отчёта с приложениями (Strava, Garmin).\n\n"
                f"Доступные команды:\n"
                f"/my_stats - моя статистика\n"
                f"/group_stats - статистика группы",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='HTML'
            )
        else:
            # Групповой чат - удаляем сообщение /start
            try:
                await update.message.delete()
            except:
                pass

    async def handle_private_message(self, update: Update, context: CallbackContext):
        """Обработчик текстовых сообщений в личных чатах"""
        user = update.effective_user
        await update.message.reply_text(
            "Чтобы записать пробежку, напиши в групповом чате:\n"
            "<code>5 км #япобегал</code>\n\n"
            "Или используй команды:\n"
            "/my_stats - моя статистика\n"
            "/group_stats - статистика группы",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='HTML'
        )

    async def handle_group_run_message(self, update: Update, context: CallbackContext):
        """Обработчик пробежек в группах (обычных и отредактированных)"""
        if update.edited_message:
            message = update.edited_message.text
            user = update.edited_message.from_user
            message_id = update.edited_message.message_id
            logger.info(f"Обрабатываем ОТРЕДАКТИРОВАННОЕ сообщение {message_id} от {user.first_name}")
            is_edited = True
        else:
            message = update.message.text
            user = update.effective_user
            message_id = update.message.message_id
            logger.info(f"Обрабатываем ОБЫЧНОЕ сообщение {message_id} от {user.first_name}")
            is_edited = False

        try:
            self.db.add_user(user.id, user.first_name, user.last_name, user.username)
            distance = self.extract_distance(message)

            if distance:
                current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if is_edited:
                    run_id = self.db.update_run(user.id, distance, message_id)
                    action_text = "обновлена"
                else:
                    run_id = self.db.add_run(user.id, distance, message_id)
                    action_text = "записана"

                # Отправляем подтверждение в ЛС
                try:
                    await context.bot.send_message(
                        chat_id=user.id,
                        text=(
                            f"✅ <b>Пробежка {action_text}!</b>\n\n"
                            f"🏃 Бегун: {user.first_name}\n"
                            f"📏 Дистанция: {distance} км\n"
                            f"📅 Дата: {current_date.split()[0]}\n\n"
                            f"Так держать! 💪"
                        ),
                        reply_markup=ReplyKeyboardRemove(),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение в ЛС пользователю {user.id}: {e}")
                
                logger.info(f"Пробежка {action_text}: {user.first_name} - {distance} км")
                
            else:
                logger.warning(f"Не удалось извлечь дистанцию из сообщения: {message}")
                try:
                    await context.bot.send_message(
                        chat_id=user.id,
                        text=(
                            f"❌ <b>Не могу определить дистанцию</b>\n\n"
                            f"В сообщении: <code>{message}</code>\n\n"
                            f"Попробуй формат: <code>5 км #япобегал</code>\n"
                            f"Или: <code>5.2 км #япобегал</code>"
                        ),
                        reply_markup=ReplyKeyboardRemove(),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение об ошибке в ЛС пользователю {user.id}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке пробежки: {e}")

    async def my_stats(self, update: Update, context: CallbackContext):
        """Персональная статистика пользователя"""
        if update.effective_chat.type != "private":
            return
            
        user = update.effective_user
        stats = self.db.get_user_stats(user.id)
        
        if stats and stats['total_runs'] > 0:
            count = stats['total_runs']
            distance = stats['total_distance']
            avg_distance = distance / count if count > 0 else 0
            
            text = (
                f"📊 <b>Статистика {user.first_name}</b>\n\n"
                f"🏃 Пробежек: <b>{count}</b>\n"
                f"📏 Общая дистанция: <b>{distance:.1f} км</b>\n"
                f"📐 Средняя дистанция: <b>{avg_distance:.1f} км</b>"
            )
            await update.message.reply_text(
                text, 
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "📊 У вас пока нет пробежек\n\n"
                "Напиши в групповом чате: <code>5 км #япобегал</code>",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='HTML'
            )

    async def group_stats(self, update: Update, context: CallbackContext):
        """Общая статистика всех пробежек"""
        if update.effective_chat.type != "private":
            return
            
        try:
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT COUNT(*), SUM(distance) FROM runs')
            result = cursor.fetchone()

            if result and result[0] and result[1] is not None:
                count, distance = result
                
                cursor.execute('SELECT COUNT(DISTINCT user_id) FROM runs')
                active_users = cursor.fetchone()[0]
                
                text = (
                    f"📊 <b>Общая статистика всех пробежек</b>\n\n"
                    f"👥 Активных бегунов: <b>{active_users}</b>\n"
                    f"🏃 Всего пробежек: <b>{count}</b>\n"
                    f"📏 Общая дистанция: <b>{distance:.1f} км</b>"
                )
                await update.message.reply_text(
                    text, 
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    "📊 Пока нет пробежек в системе\n\n"
                    "Стань первым! Напиши в группе: <code>5 км #япобегал</code>",
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode='HTML'
                )
                
        except Exception as e:
            logger.error(f"Ошибка при получении групповой статистики: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при получении статистики",
                reply_markup=ReplyKeyboardRemove()
            )

    def run(self):
        """Запуск бота"""
        logger.info("🚀 Запускаем бегового бота...")
        try:
            self.application.run_polling()
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
            raise

if __name__ == "__main__":
    bot = RunningBot()
    bot.run()