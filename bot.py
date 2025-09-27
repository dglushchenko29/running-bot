import logging
import sqlite3
import re
import os
from datetime import datetime, timedelta
from telegram.ext import Updater, MessageHandler, Filters

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

# Полностью невидимый обработчик тренировок
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
            
            # НИКАКИХ ОТВЕТОВ - абсолютная тишина
            # Просто записываем в базу и молчим
            
        except ValueError:
            pass  # Молчим даже об ошибках

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Только обработчик тренировок - никаких команд
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_workout_message))

    print("Бот запущен... (невидимый режим)")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
