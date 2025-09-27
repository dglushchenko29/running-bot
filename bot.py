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
    update.message.reply_text(
        "🏃 Беговой бот активирован!\n\n"
        "Отправьте тренировку в формате: 5 км #япобегал\n"
        "Используйте кнопки для статистики:",
        reply_markup=get_main_keyboard()
    )

def get_user_stats(user_id, days=7):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT COUNT(*), SUM(distance), AVG(distance) FROM workouts WHERE user_id = ? AND date > ?', (user_id, since_date))
    stats = cursor.fetchone()
    conn.close()
    return stats

# Команда /week
def week_stats(update, context):
    user = update.message.from_user
    stats = get_user_stats(user.id, 7)
    
    if not stats or not stats[0]:
        update.message.reply_text("📊 За неделю нет тренировок.")
        return
    
    workouts, total, avg = stats
    update.message.reply_text(f"📅 За неделю: {workouts} пробежек, {total:.1f} км, в среднем {avg:.1f} км")

# Команда /stats
def all_stats(update, context):
    user = update.message.from_user
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    cursor.execute('SELECT distance, date FROM workouts WHERE user_id = ? ORDER BY date DESC LIMIT 10', (user.id,))
    workouts = cursor.fetchall()
    conn.close()
    
    if not workouts:
        update.message.reply_text("📊 Пока нет записанных тренировок.")
        return
    
    message = "📋 Последние тренировки:\n"
    for distance, date in workouts:
        message += f"• {distance:.1f} км ({date[:10]})\n"
    
    update.message.reply_text(message)

# Кнопка "Мой пробег"
def my_stats(update, context):
    user = update.message.from_user
    stats_week = get_user_stats(user.id, 7)
    stats_month = get_user_stats(user.id, 30)
    
    if not stats_week or not stats_week[0]:
        update.message.reply_text("📊 Пока нет тренировок.", reply_markup=get_main_keyboard())
        return
    
    wk_workouts, wk_total, wk_avg = stats_week
    mn_workouts, mn_total, mn_avg = stats_month
    
    message = f"🏃 Статистика {user.first_name}:\n\n"
    message += f"📅 Неделя: {wk_workouts} пробежек, {wk_total:.1f} км\n"
    message += f"📅 Месяц: {mn_workouts} пробежек, {mn_total:.1f} км\n"
    
    update.message.reply_text(message, reply_markup=get_main_keyboard())

def help_command(update, context):
    help_text = "🤖 Отправьте: 5 км #япобегал\nИспользуйте кнопки для статистики!"
    update.message.reply_text(help_text, reply_markup=get_main_keyboard())

# Обработчик сообщений с тренировками
def handle_workout_message(update, context):
    text = update.message.text
    user = update.message.from_user
    
    if not text:
        return
    
    text_lower = text.lower()
    
    # Проверяем хештеги
    workout_type = None
    if '#япобегал' in text_lower:
        workout_type = 'run'
    elif '#япокрутил' in text_lower:
        workout_type = 'bike'
    elif '#япоплавал' in text_lower:
        workout_type = 'swim'
    else:
        return  # Игнорируем если нет хештега
    
    # Ищем дистанцию
    matches = re.search(r'(\d+[.,]?\d*)\s*(км|km)', text, re.IGNORECASE)
    if matches:
        try:
            distance_str = matches.group(1).replace(',', '.')
            distance_km = float(distance_str)
            
            user_name = user.first_name or user.username or "Аноним"
            save_workout(user.id, user_name, workout_type, distance_km)
            
            update.message.reply_text(f"✅ Записано! {distance_km} км", reply_markup=get_main_keyboard())
        except ValueError:
            pass

# Топы
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
        
    message = f"🏆 ТОП за {period_name}:\n"
    for i, (user_name, distance) in enumerate(top_list, 1):
        message += f"{i}. {user_name}: {distance:.1f} км\n"
    update.message.reply_text(message, reply_markup=get_main_keyboard())

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Команды
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("week", week_stats))
    dispatcher.add_handler(CommandHandler("stats", all_stats))
    dispatcher.add_handler(CommandHandler("top_week", top_week))
    dispatcher.add_handler(CommandHandler("top_month", top_month))
    dispatcher.add_handler(CommandHandler("help", help_command))

    # Кнопки
    dispatcher.add_handler(MessageHandler(Filters.text("🏃 Мой пробег"), my_stats))
    dispatcher.add_handler(MessageHandler(Filters.text("🏆 Топ недели"), top_week))
    dispatcher.add_handler(MessageHandler(Filters.text("📊 Топ месяца"), top_month))
    dispatcher.add_handler(MessageHandler(Filters.text("❓ Помощь"), help_command))

    # Обработчик текстовых сообщений с тренировками
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_workout_message))

    print("Бот запущен...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
