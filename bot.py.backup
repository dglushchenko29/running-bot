import logging
import sqlite3
import re
import os
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
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

# Команды
def start(update, context):
    update.message.reply_text("🏃 Добро пожаловать! Выберите действие:", reply_markup=get_main_keyboard())

def get_user_stats(user_id, days=7):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT COUNT(*), SUM(distance), AVG(distance) FROM workouts WHERE user_id = ? AND date > ?', (user_id, since_date))
    stats = cursor.fetchone()
    conn.close()
    return stats

def my_stats(update, context):
    user = update.message.from_user
    stats = get_user_stats(user.id)
    
    if not stats or not stats[0]:
        update.message.reply_text(f"📊 {user.first_name}, пока нет тренировок за неделю.", reply_markup=get_main_keyboard())
        return
    
    workouts_count, total_distance, avg_distance = stats
    message = f"🏃 Статистика {user.first_name} за неделю:\n\n"
    message += f"📈 Пробежки: {workouts_count}\n"
    message += f"📏 Дистанция: {total_distance:.1f} км\n"
    message += f"📊 В среднем: {avg_distance:.1f} км\n"
    message += f"\n💪 Так держать!"
    
    update.message.reply_text(message, reply_markup=get_main_keyboard())

def help_command(update, context):
    help_text = "🤖 Отправьте фото тренировки с подписью: '5 км #япобегал'"
    update.message.reply_text(help_text, reply_markup=get_main_keyboard())

def handle_photo_with_text(update, context):
    message = update.message
    user = update.message.from_user
    caption = message.caption

    if not caption:
        return

    caption_lower = caption.lower()
    workout_type = None
    
    if '#япобегал' in caption_lower:
        workout_type = 'run'
    elif '#япокрутил' in caption_lower:
        workout_type = 'bike'
    elif '#япоплавал' in caption_lower:
        workout_type = 'swim'

    if not workout_type:
        return

    matches = re.search(r'(\d+[.,]?\d*)\s*(км|km)', caption)
    if matches:
        try:
            distance_str = matches.group(1).replace(',', '.')
            distance_km = float(distance_str)
            user_name = user.first_name or user.username or "Аноним"
            save_workout(user.id, user_name, workout_type, distance_km)
            update.message.reply_text(f"✅ Записано! {distance_km} км", reply_markup=get_main_keyboard())
        except ValueError:
            update.message.reply_text("❌ Не понимаю дистанцию", reply_markup=get_main_keyboard())

def get_top_workouts(days=7):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT user_name, SUM(distance) FROM workouts WHERE date > ? GROUP BY user_id ORDER BY SUM(distance) DESC LIMIT 10', (since_date,))
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
        update.message.reply_text(f"🏆 За {period_name} пока нет данных.", reply_markup=get_main_keyboard())
        return
    message_text = f"🏆 ТОП-10 за {period_name}:\n\n"
    for i, (user_name, total_distance) in enumerate(top_list, 1):
        message_text += f"{i}. {user_name}: {total_distance:.1f} км\n"
    update.message.reply_text(message_text, reply_markup=get_main_keyboard())

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("top_week", top_week))
    dispatcher.add_handler(CommandHandler("top_month", top_month))
    dispatcher.add_handler(CommandHandler("help", help_command))

    dispatcher.add_handler(MessageHandler(Filters.text & Filters.regex('^🏃 Мой пробег$'), my_stats))
    dispatcher.add_handler(MessageHandler(Filters.text & Filters.regex('^🏆 Топ недели$'), top_week))
    dispatcher.add_handler(MessageHandler(Filters.text & Filters.regex('^📊 Топ месяца$'), top_month))
    dispatcher.add_handler(MessageHandler(Filters.text & Filters.regex('^❓ Помощь$'), help_command))

    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo_with_text))

    print("Бот запущен...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
