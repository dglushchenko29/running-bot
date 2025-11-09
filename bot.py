#!/usr/bin/env python3
import logging
import sqlite3
import os
from config import Config
from database import Database
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RunningBot:
    async def stats(self, update: Update, context: CallbackContext):
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Только для админов")
            return
        
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        users_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM runs')
        runs_count = cursor.fetchone()[0]
    
        text = f"""📊 Статистика БД:

👥 Пользователей: {users_count}
🏃 Пробежек: {runs_count}"""
    
        await update.message.reply_text(text)
    
    def extract_distance(self, message):
        """
        Извлекает дистанцию из сообщения с хэштегом #япобегал
        Поддерживает форматы: '5 км', '5км', '5.2 км', '5.2км' и т.д.
        """
        import re

        # Убираем хэштег и лишние пробелы
        clean_message = re.sub(r'#япобегал', '', message, flags=re.IGNORECASE)
        clean_message = re.sub(r'\s+', ' ', clean_message).strip()
        
        # Паттерны для поиск дистанции
        patterns = [
            r'(\d+[.,]?\d*)\s*км', # 5 км, 5.2 км, 5,2 км
            r'(\d+[.,]?\d*)\s*km,', # 5 km, 5.2 km
            r'(\d+[.,]?\d*)\s*километр', # 5 километр
            r'(\d+[.,]?\d*)\s*kilometer', # 5 kilometer
        ]

        for pattern in patterns:
            match = re.search(pattern, clean_message, re.IGNORECASE)
            if match:
                try:
                    # Заменяем запятую на точку и преобразуем в float
                    distance_str = match.group(1).replace(',', '.')
                    distance = float(distance_str)

                    # Проверяем реальностичность дистанции
                    if 0.1 <= distance <= 100:
                        return distance
                except ValueError:
                    continue

        # Если не нашли по паттернам, ищем просто числа в сообщении
        numbers = re.findall(r'\d+[.,]?\d*', clean_message)
        for num_str in numbers:
            try:
                distance = float(num_str.replace(',', '.'))
                if 0.1 <= distance <= 100:
                    return distance
            except ValueError:
                continue

        return None

    def __init__(self):
        self.db = Database()
        self.application = Application.builder().token(Config.BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        # Обработчики команд (работают в группах и личных сообщениях)
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("admin", self.admin_panel))
        self.application.add_handler(CommandHandler("stats", self.stats))
        self.application.add_handler(CommandHandler("my_stats", self.my_stats))
        self.application.add_handler(CommandHandler("group_stats", self.group_stats))
        self.application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, self.handle_run_message))
        
        # Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    def is_admin(self, user_id):
        admin_ids = [612481183]  # Твой ID
        return user_id in admin_ids
    
    async def start(self, update: Update, context: CallbackContext):
        user = update.effective_user
        chat = update.effective_chat
        self.db.add_user(user.id, user.first_name, user.last_name, user.username)
        
        # Определяем тип чата
        if chat.type == "private":
            # Личные сообщения
            if self.is_admin(user.id):
                await self.admin_panel(update, context)
            else:
                keyboard = [
                    [KeyboardButton("📊 Моя статистика")],
                    [KeyboardButton("📊 Статистика группы")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text(
                    f"🏃 Привет, {user.first_name}!\n"
                    f"Просто напиши в группе: 'n км #япобегал'",
                    reply_markup=reply_markup
                )
        else:
            # Групповой чат
            await update.message.reply_text(
                f"🏃 Беговой бот активирован в группе!\n\n"
                f"Просто напиши: '5 км #япобегал'\n"  
                f"Или команды:\n"
                f"/my_stats - моя статистика\n"
                f"/group_stats - статистика группы"
            )
    
    async def admin_panel(self, update: Update, context: CallbackContext):
        keyboard = [
            [KeyboardButton("📊 Статистика БД"), KeyboardButton("📋 Все пробежки")],
            [KeyboardButton("👥 Пользователи"), KeyboardButton("🏆 Топ недели")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("👨‍💻 Админ-панель", reply_markup=reply_markup)
    
    async def handle_message(self, update: Update, context: CallbackContext):
        # Работает только в личных сообщениях
        if update.effective_chat.type != "private":
            return
            
        text = update.message.text
        user = update.effective_user
        
        logger.info(f"Кнопка: {text} от {user.first_name}")
        
        if text == "📊 Моя статистика":
            await self.my_stats(update, context)
        elif text == "📊 Статистика группы":
            await self.group_stats(update,context)

        elif self.is_admin(user.id):
            if text == "📊 Статистика БД":
                await self.stats(update, context)
            elif text == "📋 Все пробежки":
                await self.show_all_runs(update, context)
            elif text == "👥 Пользователи":
                await self.show_users(update, context)
            elif text == "🏆 Топ недели":
                await self.show_weekly_top(update, context)
            elif text == "Топ месяца":
                await self.show_monthly_top(update, context)
    
    async def my_stats(self, update: Update, context: CallbackContext):
        user = update.effective_user
        stats = self.db.get_user_stats(user.id)
        
        if stats and stats['total_runs'] > 0:
            count = stats['total_runs']
            distance = stats['total_distance']
            average = stats['average_distance']
            text = f"""📊 Статистика {user.first_name}:

🏃 Пробежек: {count}
📏 Дистанция: {distance:.1f} км"""
            await update.message.reply_text(text)
        else:
            await update.message.reply_text("📊 У вас пока нет пробежек")
    
    async def group_stats(self, update: Update, context: CallbackContext):
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT COUNT(*), SUM(distance) from runs')
        result = cursor.fetchone()

        if result and result[0]:
            count, distance = result
            text = f"""Общая статистика всех пробежек:

    Всего пробежек: {count}
    Общая дистанция: {distance:.1f} км"""
            await update.message.reply_text(text)
        else:
            await update.message.reply_text("Пока нет пробежек в системе")
    
    async def show_all_runs(self, update: Update, context: CallbackContext):
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT r.run_id, u.first_name, r.distance, r.duration, r.date 
            FROM runs r JOIN users u ON r.user_id = u.user_id 
            ORDER BY r.date DESC LIMIT 10
        ''')
        runs = cursor.fetchall()
        
        if runs:
            text = "📋 Последние пробежки:\n\n"
            for run in runs:
                text += f"#{run[0]} {run[1]}: {run[2]}км/{run[3]}мин ({run[4]})\n"
            await update.message.reply_text(text)
        else:
            await update.message.reply_text("📭 Нет пробежек")
    
    async def show_users(self, update: Update, context: CallbackContext):
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT user_id, first_name FROM users')
        users = cursor.fetchall()
        
        if users:
            text = "👥 Пользователи:\n\n"
            for user in users:
                text += f"• {user[1]} (ID: {user[0]})\n"
            await update.message.reply_text(text)
        else:
            await update.message.reply_text("👥 Нет пользователей")
    
    async def show_weekly_top(self, update: Update, context: CallbackContext):
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT u.first_name, SUM(r.distance), COUNT(r.run_id)
            FROM runs r JOIN users u ON r.user_id = u.user_id 
            WHERE r.date >= date('now', '-7 days')
            GROUP BY u.user_id ORDER BY SUM(r.distance) DESC LIMIT 5
        ''')
        top = cursor.fetchall()
        
        if top:
            text = "🏆 Топ за неделю:\n\n"
            for i, user in enumerate(top, 1):
                text += f"{i}. {user[0]} - {user[1]:.1f} км ({user[2]} пробежек)\n"
            await update.message.reply_text(text)
        else:
            await update.message.reply_text("🏆 Нет пробежек за неделю")

    def run(self):
        logger.info("🚀 Запускаем бота...")
        self.application.run_polling()
    
    async def handle_run_message(self, update: Update, context: CallbackContext):
        message = update.message.text
        user = update.effective_user
        chat = update.effective_chat

        # Проверяем наличие хэштега и километража
        if "#япобегал" in message.lower():
            try:
                # Сохарянем пользователя в БД
                self.db.add_user(user.id, user.first_name, user.last_name, user.username)

                # Ищем дистанцию улучшенным способом
                distance = self.extract_distance(message)

                if distance:
                    # Сохраняем тренировку в БД
                    import datetime
                    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
                    run_id = self.db.add_run(user.id, distance)

                    # Отправляем подтверждение в лс
                    await context.bot.send_message(
                        chat_id=user.id,
                        text=f"✅ {user.first_name}, ваша пробежка на {distance} км записана! Так держать! 💪"
                        )
                else:
                    logger.warning(f"Не удалось извлечь дистанцию: {message}")
            except Exception as e:
                logger.error(f"Ошибка: {e}")

if __name__ == "__main__":
    bot = RunningBot()
    bot.run()
