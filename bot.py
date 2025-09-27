import logging
import sqlite3
import re
import os
from datetime import datetime, timedelta
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler

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
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            telegram_name TEXT,
            c95_name TEXT,
            c95_profile_url TEXT,
            registered_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            workout_type TEXT NOT NULL,
            distance REAL NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

def register_user(user_id, telegram_name, c95_name, c95_url):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    registered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, telegram_name, c95_name, c95_profile_url, registered_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, telegram_name, c95_name, c95_url, registered_at))
    
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def save_workout(user_id, workout_type, distance):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO workouts (user_id, workout_type, distance, date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, workout_type, distance, current_time))
    
    conn.commit()
    conn.close()

# Упрощенная команда старта (без сложного форматирования)
def start_registration(update, context):
    user = update.message.from_user
    
    # Простое сообщение без Markdown
    message = """
🏃‍♂️ Регистрация в беговом боте С95

Чтобы начать, отправьте мне ссылку на ваш профиль на s95.ru

Пример ссылки:
https://s95.ru/athletes/12345

После этого введите ваше имя как на сайте.

Или используйте команду:
/register https://s95.ru/athletes/ваш_номер
"""
    
    update.message.reply_text(message)

def handle_c95_link(update, context):
    text = update.message.text
    user = update.message.from_user
    
    if 's95.ru/athletes/' in text:
        c95_url = text.strip()
        
        update.message.reply_text(
            f"🔗 Найден профиль С95!\n"
            f"📝 Теперь введите ваше имя и фамилию как на сайте:"
        )
        context.user_data['pending_registration'] = {'url': c95_url}
        
        try:
            update.message.delete()
        except:
            pass

def complete_registration(update, context):
    text = update.message.text
    user = update.message.from_user
    
    if 'pending_registration' in context.user_data:
        c95_url = context.user_data['pending_registration']['url']
        c95_name = text.strip()
        
        register_user(user.id, user.first_name, c95_name, c95_url)
        del context.user_data['pending_registration']
        
        message = f"✅ Регистрация завершена!\n\n"
        message += f"👤 Имя: {c95_name}\n"
        message += f"🔗 Профиль: {c95_url}\n\n"
        message += f"Теперь отправляйте тренировки в формате:\n"
        message += f"10 км #япобегал\n\n"
        message += f"Команды:\n"
        message += f"/stats - ваша статистика\n"
        message += f"/top_week - топ недели\n"
        message += f"/top_month - топ месяца"
        
        update.message.reply_text(message)

def handle_workout_message(update, context):
    text = update.message.text
    user = update.message.from_user
    
    if not text:
        return
    
    if 'pending_registration' in context.user_data:
        complete_registration(update, context)
        return
    
    text_lower = text.lower()
    
    workout_type = None
    if '#япобегал' in text_lower:
        workout_type = 'run'
    elif '#япокрутил' in text_lower:
        workout_type = 'bike'
    elif '#япоплавал' in text_lower:
        workout_type = 'swim'
    else:
        if 's95.ru/athletes/' in text:
            handle_c95_link(update, context)
        return
    
    matches = re.search(r'(\d+[.,]?\d*)\s*(км|km)', text, re.IGNORECASE)
    if matches:
        try:
            distance_str = matches.group(1).replace(',', '.')
            distance_km = float(distance_str)
            
            save_workout(user.id, workout_type, distance_km)
            
            try:
                user_data = get_user(user.id)
                if user_data:
                    c95_name = user_data[2] or user.first_name
                    c95_url = user_data[3]
                else:
                    c95_name = user.first_name
                    c95_url = None
                
                message = f"✅ Тренировка записана!\n\n🏃‍♂️ Дистанция: {distance_km} км\n👤 От имени: {c95_name}"
                
                if c95_url:
                    message += f"\n🔗 Профиль: {c95_url}"
                
                user.send_message(message)
            except:
                update.message.reply_text("✅", reply_to_message_id=update.message.message_id)
            
        except ValueError:
            pass

def get_top_workouts(days=7):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        SELECT u.user_id, u.c95_name, u.c95_profile_url, SUM(w.distance) as total_distance
        FROM workouts w
        JOIN users u ON w.user_id = u.user_id
        WHERE w.date > ?
        GROUP BY u.user_id
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
        update.message.reply_text(f"🏆 За {period_name} пока нет данных.")
        return
        
    message = f"🏆 ТОП за {period_name}:\n\n"
    
    for i, (user_id, c95_name, c95_url, total_distance) in enumerate(top_list, 1):
        if c95_url and c95_name:
            message += f"{i}. {c95_name}: {total_distance:.1f} км\n"
            message += f"   🔗 {c95_url}\n\n"
        else:
            user_data = get_user(user_id)
            name = c95_name or (user_data[1] if user_data else f"Участник {user_id}")
            message += f"{i}. {name}: {total_distance:.1f} км\n\n"
    
    update.message.reply_text(message)

def user_stats(update, context):
    user = update.message.from_user
    user_data = get_user(user.id)
    
    if not user_data:
        update.message.reply_text("📋 Сначала зарегистрируйтесь: /register")
        return
    
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    
    since_date_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT COUNT(*), SUM(distance) FROM workouts WHERE user_id = ? AND date > ?', (user.id, since_date_week))
    week_stats = cursor.fetchone()
    
    since_date_month = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT COUNT(*), SUM(distance) FROM workouts WHERE user_id = ? AND date > ?', (user.id, since_date_month))
    month_stats = cursor.fetchone()
    
    conn.close()
    
    c95_name, c95_url = user_data[2], user_data[3]
    
    message = f"📊 Ваша статистика\n\n"
    message += f"👤 Имя: {c95_name}\n"
    if c95_url:
        message += f"🔗 Профиль: {c95_url}\n"
    
    if week_stats and week_stats[0]:
        message += f"\n📅 За неделю:\n"
        message += f"• Пробежек: {week_stats[0]}\n"
        message += f"• Дистанция: {week_stats[1]:.1f} км\n"
    
    if month_stats and month_stats[0]:
        message += f"\n📅 За месяц:\n"
        message += f"• Пробежек: {month_stats[0]}\n"
        message += f"• Дистанция: {month_stats[1]:.1f} км\n"
    
    if not week_stats[0] and not month_stats[0]:
        message += f"\n📭 Пока нет записанных тренировок.\nОтправьте: 5 км #япобегал"
    
    update.message.reply_text(message)

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start_registration))
    dispatcher.add_handler(CommandHandler("register", start_registration))
    dispatcher.add_handler(CommandHandler("stats", user_stats))
    dispatcher.add_handler(CommandHandler("top_week", top_week))
    dispatcher.add_handler(CommandHandler("top_month", top_month))

    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_workout_message))

    print("Бот запущен... (исправленная версия)")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
