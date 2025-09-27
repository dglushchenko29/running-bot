import os
import telebot
from telebot import types
import sqlite3
from datetime import datetime, timedelta
import re
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация бота
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

bot = telebot.TeleBot(BOT_TOKEN)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('running.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            distance REAL NOT NULL,
            date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

# Функция для добавления пробега
def add_run(user_id, username, distance, date=None):
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    conn = sqlite3.connect('running.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO runs (user_id, username, distance, date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, distance, date))
    
    conn.commit()
    conn.close()
    logger.info(f"Added run: user_id={user_id}, distance={distance}km, date={date}")

# Функция для получения пробега за неделю
def get_weekly_distance(user_id):
    conn = sqlite3.connect('running.db')
    cursor = conn.cursor()
    
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    cursor.execute('''
        SELECT SUM(distance) FROM runs 
        WHERE user_id = ? AND date >= ?
    ''', (user_id, week_ago))
    
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result[0] is not None else 0

# Функция для получения последних пробегов
def get_recent_runs(user_id, limit=5):
    conn = sqlite3.connect('running.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT distance, date FROM runs 
        WHERE user_id = ? 
        ORDER BY date DESC 
        LIMIT ?
    ''', (user_id, limit))
    
    runs = cursor.fetchall()
    conn.close()
    
    return runs

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    welcome_text = f"""
Привет, {username}! 🏃‍♂️

Я бот для учета пробегов. Просто отправляй мне свои пробеги в формате:
• 5 км
• 10.5 км
• 7,2 км

Команды:
/start - начать работу
/week - пробег за неделю
/stats - последние пробеги
    """
    
    bot.reply_to(message, welcome_text)
    logger.info(f"User {user_id} started the bot")

# Обработчик команды /week
@bot.message_handler(commands=['week'])
def show_weekly(message):
    user_id = message.from_user.id
    weekly_distance = get_weekly_distance(user_id)
    
    if weekly_distance > 0:
        text = f"🏃‍♂️ Ваш пробег за неделю: {weekly_distance:.1f} км"
    else:
        text = "📊 Пока нет пробегов за неделю. Начните бегать!"
    
    bot.reply_to(message, text)
    logger.info(f"Weekly stats for user {user_id}: {weekly_distance}km")

# Обработчик команды /stats
@bot.message_handler(commands=['stats'])
def show_stats(message):
    user_id = message.from_user.id
    recent_runs = get_recent_runs(user_id)
    
    if recent_runs:
        text = "📈 Ваши последние пробеги:\n\n"
        for i, (distance, date) in enumerate(recent_runs, 1):
            text += f"{i}. {distance} км - {date}\n"
    else:
        text = "📊 У вас пока нет записанных пробегов."
    
    bot.reply_to(message, text)
    logger.info(f"Stats shown for user {user_id}")

# Главный обработчик текстовых сообщений
@bot.message_handler(content_types=['text'])
def handle_text_messages(message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name
        text = message.text.strip()
        
        logger.info(f"Received message from {user_id} ({username}): {text}")
        
        # Пытаемся найти километраж в сообщении
        km_match = re.search(r'(\d+[,.]?\d*)\s*км', text, re.IGNORECASE)
        if km_match:
            km_str = km_match.group(1).replace(',', '.')
            km = float(km_str)
            
            # Сохраняем пробег в базу данных
            add_run(user_id, username, km)
            
            # Получаем недельный пробег для отчета
            weekly_distance = get_weekly_distance(user_id)
            
            response = f"""
✅ Пробег {km} км сохранен! 🏃‍♂️

📊 Ваш пробег за неделю: {weekly_distance:.1f} км
            """
            
            bot.reply_to(message, response)
            logger.info(f"Run saved: user_id={user_id}, distance={km}km")
            
        else:
            # Если это не пробег, предлагаем помощь
            help_text = """
🤔 Я не нашел пробег в вашем сообщении.

Отправьте пробег в формате:
• 5 км
• 10.5 км  
• 7,2 км

Или используйте команды:
/week - пробег за неделю
/stats - последние пробеги
            """
            bot.reply_to(message, help_text)
            
    except ValueError:
        bot.reply_to(message, "❌ Неправильный формат числа. Используйте например: 5 км или 10.5 км")
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при обработке сообщения")

# Запуск бота
if __name__ == "__main__":
    logger.info("Initializing database...")
    init_db()
    logger.info("Bot starting...")
    
    # Проверяем, используем ли мы вебхук или polling
    webhook_url = os.getenv('WEBHOOK_URL')
    
    if webhook_url:
        logger.info(f"Using webhook: {webhook_url}")
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        logger.info("Webhook set successfully")
    else:
        logger.info("Using polling...")
        bot.polling(none_stop=True, interval=2, timeout=60)
        logger.info("Polling started")
