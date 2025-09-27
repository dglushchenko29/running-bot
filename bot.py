import logging
import sqlite3
import re
import os
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

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

# Приватный ответ (только для отправителя в ЛС)
def reply_private(update, text):
    try:
        # Пытаемся отправить в личные сообщения
        update.message.from_user.send_message(text)
    except Exception as e:
        # Если не удалось, отвечаем в чате но удаляем исходное сообщение
        try:
            # Удаляем сообщение пользователя чтобы скрыть команду
            update.message.delete()
        except:
            pass
        # Отвечаем временным сообщением которое само удалится
        msg = update.message.reply_text(text)
        # В реальном боте здесь был бы таймер на удаление сообщения

# Команды
def start(update, context):
    reply_private(update,
        "🏃 Беговой бот\n\n"
        "Команды:\n"
        "/week - статистика за неделю\n" 
        "/stats - последние тренировки\n"
        "/top_week - топ за неделю (публичный)\n"
        "/top_month - топ за месяц (публичный)\n\n"
        "Чтобы записать тренировку, отправьте:\n"
        "5 км #япобегал - для бега\n"
        "20 км #япокрутил - для вело\n"
        "1 км #япоплавал - для плавания\n\n"
        "Бот работает автоматически!"
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
        reply_private(update, "📊 За неделю нет тренировок.")
        return
    
    workouts, total, avg = stats
    reply_private(update, f"📅 Неделя: {workouts} пробежек, {total:.1f} км, в среднем {avg:.1f} км")

# Команда /stats
def all_stats(update, context):
    user = update.message.from_user
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    cursor.execute('SELECT distance, date FROM workouts WHERE user_id = ? ORDER BY date DESC LIMIT 10', (user.id,))
    workouts = cursor.fetchall()
    conn.close()
    
    if not workouts:
        reply_private(update, "📊 Пока нет записанных тренировок.")
        return
    
    message = "📋 Последние тренировки:\n"
    for distance, date in workouts:
        message += f"• {distance:.1f} км ({date[:10]})\n"
    
    reply_private(update, message)

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
            
            # Приватный ответ о записи
            reply_private(update, f"✅ Записано! {distance_km} км")
        except ValueError:
            pass

# Топы (публичные - видны всем)
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
        reply_private(update, f"🏆 За {period_name} пока нет данных.")
        return
        
    message = f"🏆 ТОП за {period_name}:\n"
    for i, (user_name, distance) in enumerate(top_list, 1):
        message += f"{i}. {user_name}: {distance:.1f} км\n"
    
    # Топы публичные - видны всем в чате
    try:
        update.message.reply_text(message)
    except:
        reply_private(update, message)

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Команды
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("week", week_stats))
    dispatcher.add_handler(CommandHandler("stats", all_stats))
    dispatcher.add_handler(CommandHandler("top_week", top_week))
    dispatcher.add_handler(CommandHandler("top_month", top_month))
    dispatcher.add_handler(CommandHandler("help", start))  # help = start

    # Обработчик текстовых сообщений с тренировками
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_workout_message))

    print("Бот запущен...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
