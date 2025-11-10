#!/usr/bin/env python3
import logging
import re
from datetime import datetime
from config import Config
from database import Database
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RunningBot:
    def __init__(self):
        self.db = Database()
        self.application = Application.builder().token(Config.BOT_TOKEN).build()
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

    async def start(self, update: Update, context: CallbackContext):
        """Обработчик команды /start"""
        user = update.effective_user
        chat = update.effective_chat
        
        # Добавляем пользователя в БД
        self.db.add_user(user.id, user.first_name, user.last_name, user.username)
        
        if chat.type == "private":
            # ЛИЧНЫЕ СООБЩЕНИЯ - БЕЗ КНОПОК
            await update.message.reply_text(
                f"🏃 Привет, {user.first_name}!\n\n"
                f"Я помогу тебе отслеживать твои пробежки! 🏃‍♂️\n\n"
                f"Чтобы записать пробежку, напиши в групповом чате:\n"
                f"<code>5 км #япобегал</code>\n\n"
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
        
        # Просто отправляем подсказку БЕЗ КНОПОК
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
        # Определяем тип сообщения (обычное или отредактированное)
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
            # Сохраняем пользователя в БД
            self.db.add_user(user.id, user.first_name, user.last_name, user.username)

            # Ищем дистанцию
            distance = self.extract_distance(message)

            if distance:
                # Сохраняем тренировку в БД
                current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if is_edited:
                    # Для отредактированных сообщений - обновляем пробежку по message_id
                    run_id = self.db.update_run(user.id, distance, message_id)
                    action_text = "обновлена"
                else:
                    # Для обычных сообщений - создаем новую запись с message_id
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
                
                logger.info(f"Пробежка {action_text}: {user.first_name} - {distance} км (message_id: {message_id})")
                
            else:
                logger.warning(f"Не удалось извлечь дистанцию из сообщения: {message}")
                
                # Пытаемся отправить ошибку в ЛС
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