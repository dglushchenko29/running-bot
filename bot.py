import logging
import sqlite3
import re
import os
from datetime import datetime, timedelta
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

def get_user_stats(user_id, days=7):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT COUNT(*), SUM(distance), AVG(distance) FROM workouts WHERE user_id = ? AND date > ?', (user_id, since_date))
    stats = cursor.fetchone()
    conn.close()
    return stats

# Отправка приватного сообщения (только в ЛС)
def send_private_message(user, text):
    try:
        user.send_message(text)
        return True
    except:
        return False

# Обработчик тренировок - ставит реакцию и пишет в ЛС
def handle_workout_message(update, context):
    text = update.message.text
    user = update.message.from_user
    
    if not text:
        return
    
    text_lower = text.lower()
    
    # Проверяем хештеги
    workout_type = None
    emoji = "🔥"
    if '#япобегал' in text_lower:
        workout_type = 'run'
        emoji = "🏃‍♂️"
    elif '#япокрутил' in text_lower:
        workout_type = 'bike'
        emoji = "🚴‍♂️"
    elif '#япоплавал' in text_lower:
        workout_type = 'swim'
        emoji = "🏊‍♂️"
    else:
        return
    
    # Ищем дистанцию
    matches = re.search(r'(\d+[.,]?\d*)\s*(км|km)', text, re.IGNORECASE)
    if matches:
        try:
            distance_str = matches.group(1).replace(',', '.')
            distance_km = float(distance_str)
            
            user_name = user.first_name or user.username or "Аноним"
            save_workout(user.id, user_name, workout_type, distance_km)
            
            # Ставим реакцию (всем видно в чате)
            try:
                update.message.reply_text(emoji)
            except:
                pass
            
            # Приватное сообщение в ЛС
            private_msg = f"✅ Записано {distance_km} км!\n\nКоманды:\n/stats - моя статистика\n/top_week - топ недели\n/top_month - топ месяца"
            send_private_message(user, private_msg)
            
        except ValueError:
            pass

# Команда /stats - полностью приватная
def stats_command(update, context):
    user = update.message.from_user
    
    # Пытаемся удалить команду из чата
    try:
        update.message.delete()
    except:
        pass
    
    stats_week = get_user_stats(user.id, 7)
    stats_month = get_user_stats(user.id, 30)
    
    if not stats_week or not stats_week[0]:
        send_private_message(user, "📊 Пока нет тренировок.")
        return
    
    wk_workouts, wk_total, wk_avg = stats_week
    mn_workouts, mn_total, mn_avg = stats_month
    
    message = f"🏃 Ваша статистика:\n\n"
    message += f"📅 Неделя: {wk_workouts} пробежек, {wk_total:.1f} км\n"
    message += f"📅 Месяц: {mn_workouts} пробежек, {mn_total:.1f} км\n\n"
    message += "💡 Отправьте: 5 км #япобегал"
    
    send_private_message(user, message)

# Команда /top_week - публичный топ
def top_week_command(update, context):
    user = update.message.from_user
    
    # Пытаемся удалить команду из чата
    try:
        update.message.delete()
    except:
        pass
    
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT user_name, SUM(distance) FROM workouts WHERE date > ? GROUP BY user_id ORDER BY SUM(distance) DESC LIMIT 10', (since_date,))
    top_list = cursor.fetchall()
    conn.close()
    
    if not top_list:
        send_private_message(user, "🏆 За неделю пока нет данных.")
        return
        
    message = "🏆 ТОП за неделю:\n"
    for i, (user_name, distance) in enumerate(top_list, 1):
        message += f"{i}. {user_name}: {distance:.1f} км\n"
    
    # Топ отправляем в чат (публично)
    try:
        update.message.reply_text(message)
    except:
        send_private_message(user, message)

# Команда /top_month - публичный топ
def top_month_command(update, context):
    user = update.message.from_user
    
    # Пытаемся удалить команду из чата
    try:
        update.message.delete()
    except:
        pass
    
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT user_name, SUM(distance) FROM workouts WHERE date > ? GROUP BY user_id ORDER BY SUM(distance) DESC LIMIT 10', (since_date,))
    top_list = cursor.fetchall()
    conn.close()
    
    if not top_list:
        send_private_message(user, "🏆 За месяц пока нет данных.")
        return
        
    message = "🏆 ТОП за месяц:\n"
    for i, (user_name, distance) in enumerate(top_list, 1):
        message += f"{i}. {user_name}: {distance:.1f} км\n"
    
    # Топ отправляем в чат (публично)
    try:
        update.message.reply_text(message)
    except:
        send_private_message(user, message)

# Команда /start - приватная справка
def start_command(update, context):
    user = update.message.from_user
    
    # Пытаемся удалить команду из чата
    try:
        update.message.delete()
    except:
        pass
    
    message = "🏃 Беговой бот\n\n"
    message += "📝 Чтобы записать тренировку, отправьте в чат:\n"
    message += "5 км #япобегал - для бега\n"
    message += "20 км #япокрутил - для вело\n"
    message += "1 км #япоплавал - для плавания\n\n"
    message += "📊 Команды (приватные):\n"
    message += "/stats - ваша статистика\n"
    message += "/top_week - топ недели (публичный)\n"
    message += "/top_month - топ месяца (публичный)\n\n"
    message += "🔥 Бот поставит реакцию на ваше сообщение!"
    
    send_private_message(user, message)

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Команды (приватные)
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("stats", stats_command))
    dispatcher.add_handler(CommandHandler("top_week", top_week_command))
    dispatcher.add_handler(CommandHandler("top_month", top_month_command))
    dispatcher.add_handler(CommandHandler("help", start_command))

    # Обработчик тренировок
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_workout_message))

    print("Бот запущен...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
