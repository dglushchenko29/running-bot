import logging
import sqlite3
import re
import os
from datetime import datetime, timedelta
from telegram import ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен бота
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8029857232:AAEi8YfRTWafF2M8jQnOQae1Xg25bdqw6Ds')

# База данных
def init_db():
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            workout_type TEXT NOT NULL,
            distance REAL NOT NULL,
            date TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_workout(user_id, user_name, workout_type, distance):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO workouts (user_id, user_name, workout_type, distance, date)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, user_name, workout_type, distance, current_time))
    conn.commit()
    conn.close()

# Меню
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏃 Мой пробег"), KeyboardButton("🏆 Топ недели")],
        [KeyboardButton("📊 Топ месяца"), KeyboardButton("❓ Помощь")]
    ], resize_keyboard=True)

# Команда /start
def start(update, context):
    update.message.reply_text(
        "🏃 Добро пожаловать в бегового бота!\n\n"
        "Используйте кнопки ниже для управления:",
        reply_markup=get_main_keyboard()
    )

# Статистика пользователя
def get_user_stats(user_id, days=7):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        SELECT 
            COUNT(*) as workouts_count,
            SUM(distance) as total_distance,
            AVG(distance) as avg_distance
        FROM workouts 
        WHERE user_id = ? AND date > ?
    ''', (user_id, since_date))
    
    stats = cursor.fetchone()
    
    cursor.execute('''
        SELECT workout_type, SUM(distance) as distance
        FROM workouts 
        WHERE user_id = ? AND date > ?
        GROUP BY workout_type
    ''', (user_id, since_date))
    
    workout_types = cursor.fetchall()
    conn.close()
    
    return stats, workout_types

# Обработчик кнопки "Мой пробег"
def my_stats(update, context):
    user = update.message.from_user
    user_id = user.id
    
    stats_week, workout_types_week = get_user_stats(user_id, days=7)
    stats_month, workout_types_month = get_user_stats(user_id, days=30)
    
    if not stats_week or not stats_week[0]:
        update.message.reply_text(
            f"📊 {user.first_name}, у вас пока нет тренировок.\n\n"
            f"Отправьте фото пробежки с дистанцией и хештегом #япобегал!",
            reply_markup=get_main_keyboard()
        )
        return
    
    workouts_week, total_week, avg_week = stats_week
    workouts_month, total_month, avg_month = stats_month
    
    message = f"🏃 **Статистика {user.first_name}**\n\n"
    message += f"📅 **За текущую неделю:**\n"
    message += f"   • Пробежки: {workouts_week}\n"
    message += f"   • Дистанция: {total_week:.1f} км\n"
    message += f"   • В среднем: {avg_week:.1f} км/пробег\n\n"
    
    message += f"📅 **За текущий месяц:**\n"
    message += f"   • Пробежки: {workouts_month}\n"
    message += f"   • Дистанция: {total_month:.1f} км\n"
    message += f"   • В среднем: {avg_month:.1f} км/пробег\n"
    
    update.message.reply_text(message, reply_markup=get_main_keyboard())

# Обработчик кнопки "Помощь"
def help_command(update, context):
    help_text = """🤖 **Как пользоваться ботом:**

📸 **Чтобы записать тренировку:**
Отправьте фото с подписью:
• 5 км #япобегал - для бега
• 20 км #япокрутил - для вело
• 1 км #япоплавал - для плавания

⚡ **Бот учитывает ТОЛЬКО сообщения с хештегами!**
Сообщения без #япобегал/#япокрутил/#япоплавал игнорируются.

📊 **Кнопки:**
• 🏃 Мой пробег - ваша статистика
• 🏆 Топ недели - рейтинг за неделю
• 📊 Топ месяца - рейтинг за месяц"""
    
    update.message.reply_text(help_text, reply_markup=get_main_keyboard())

# Обработчик сообщений с фото - ТОЛЬКО с хештегами
def handle_photo_with_text(update, context):
    message = update.message
    user = update.message.from_user
    caption = message.caption

    if not caption:
        return  # Игнорируем фото без подписи

    caption_lower = caption.lower()
    
    # Проверяем наличие хештегов
    workout_type = None
    if '#япобегал' in caption_lower:
        workout_type = 'run'
    elif '#япокрутил' in caption_lower:
        workout_type = 'bike'
    elif '#япоплавал' in caption_lower:
        workout_type = 'swim'
    
    if not workout_type:
        return  # Игнорируем сообщения без правильных хештегов

    # Ищем дистанцию
    matches = re.search(r'(\d+[.,]?\d*)\s*(км|km|КМ)', caption, re.IGNORECASE)
    if matches:
        try:
            distance_str = matches.group(1).replace(',', '.')
            distance_km = float(distance_str)
            
            user_name = user.first_name or user.username or "Аноним"
            save_workout(user.id, user_name, workout_type, distance_km)
            
            update.message.reply_text(
                f"✅ Записано! {distance_km} км",
                reply_markup=get_main_keyboard()
            )
        except ValueError:
            # Игнорируем ошибки - не наша проблема
            return
    else:
        # Игнорируем если нет дистанции
        return

# Функции для топа
def get_top_workouts(days=7):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        SELECT user_name, SUM(distance) as total_distance 
        FROM workouts 
        WHERE date > ? 
        GROUP BY user_id 
        ORDER BY total_distance DESC 
        LIMIT 10
    ''', (since_date,))
    top_list = cursor.fetchall()
    conn.close()
    return top_list

def top_week(update, context):
    top_list = get_top_workouts(7)
    send_top_message(update, top_list, "неделю")

def top_month(update, context):
    top_list = get_top_workouts(30)
    send_top_message(update, top_list, "месяц")

def send_top_message(update, top_list, period_name):
    if not top_list:
        update.message.reply_text(
            f"🏆 За {period_name} пока нет данных о тренировках.",
            reply_markup=get_main_keyboard()
        )
        return
        
    message_text = f"🏆 ТОП-10 за {period_name}:\n\n"
    for i, (user_name, total_distance) in enumerate(top_list, 1):
        message_text += f"{i}. {user_name}: {total_distance:.1f} км\n"
        
    update.message.reply_text(message_text, reply_markup=get_main_keyboard())

# Главная функция
def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Обработчики команд
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("top_week", top_week))
    dispatcher.add_handler(CommandHandler("top_month", top_month))
    dispatcher.add_handler(CommandHandler("help", help_command))

    # Обработчики кнопок - ПРОСТЫЕ фильтры
    dispatcher.add_handler(MessageHandler(Filters.text("🏃 Мой пробег"), my_stats))
    dispatcher.add_handler(MessageHandler(Filters.text("🏆 Топ недели"), top_week))
    dispatcher.add_handler(MessageHandler(Filters.text("📊 Топ месяца"), top_month))
    dispatcher.add_handler(MessageHandler(Filters.text("❓ Помощь"), help_command))

    # Обработчик фото
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo_with_text))

    print("Бот запущен...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
