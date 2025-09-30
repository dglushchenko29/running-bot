import logging
import sqlite3
import re
import os
from datetime import datetime, timedelta
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8029857232:AAEi8YfRTWafF2M8jQnOQae1Xg25bdqw6Ds')

# База данных
def init_db():
    conn = sqlite3.connect('running_bot.db')
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
    conn = sqlite3.connect('running_bot.db')
    cursor = conn.cursor()
    registered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, telegram_name, c95_name, c95_profile_url, registered_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, telegram_name, c95_name, c95_url, registered_at))
    
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('running_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def save_workout(user_id, workout_type, distance):
    conn = sqlite3.connect('running_bot.db')
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO workouts (user_id, workout_type, distance, date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, workout_type, distance, current_time))
    
    conn.commit()
    conn.close()

# Клавиатура для чата - ОДНА кнопка
def get_chat_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏃 Добавить пробежку")]
    ], resize_keyboard=True, one_time_keyboard=False)

# Клавиатура для ЛС - полное меню
def get_private_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Моя статистика"), KeyboardButton("🏆 Топ недели")],
        [KeyboardButton("📈 Топ месяца"), KeyboardButton("🔗 Регистрация")]
    ], resize_keyboard=True)

# Команда старта
def start_bot(update, context):
    user = update.message.from_user
    chat_type = update.message.chat.type
    
    if chat_type == 'private':
        # В ЛС - показываем полное меню
        user_data = get_user(user.id)
        if user_data:
            message = f"🏃 С возвращением, {user_data[2]}!\nВыберите действие:"
        else:
            message = "🏃‍♂️ Добро пожаловать! Для начала зарегистрируйтесь."
        
        update.message.reply_text(message, reply_markup=get_private_keyboard())
    else:
        # В чате - показываем одну кнопку
        update.message.reply_text(
            "🏃 Нажмите кнопку ниже чтобы добавить пробежку:",
            reply_markup=get_chat_keyboard()
        )

# Обработчик кнопки "🏃 Добавить пробежку"
def add_run_button(update, context):
    user = update.message.from_user
    
    # Проверяем регистрацию
    user_data = get_user(user.id)
    if not user_data:
        update.message.reply_text(
            "❌ Сначала зарегистрируйтесь в ЛС у бота:\n\n"
            "1. Напишите боту в личные сообщения\n" 
            "2. Используйте команду /start\n"
            "3. Пройдите регистрацию",
            reply_markup=get_chat_keyboard()
        )
        return
    
    # Просим ввести дистанцию
    update.message.reply_text(
        f"📝 Введите дистанцию пробежки:\n\n"
        f"Примеры:\n"
        f"• 5 км\n" 
        f"• 10.5 км\n"
        f"• 7,2 км\n\n"
        f"Бот автоматически добавит #япобегал",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("Отмена")]
        ], resize_keyboard=True)
    )
    
    context.user_data['waiting_for_distance'] = True

# Обработчик ввода дистанции
def handle_distance_input(update, context):
    text = update.message.text
    user = update.message.from_user
    
    if text.lower() == 'отмена':
        context.user_data.pop('waiting_for_distance', None)
        update.message.reply_text("❌ Отменено", reply_markup=get_chat_keyboard())
        return
    
    if context.user_data.get('waiting_for_distance'):
        # Ищем дистанцию в сообщении
        matches = re.search(r'(\d+[.,]?\d*)\s*(км|km)?', text, re.IGNORECASE)
        if matches:
            try:
                distance_str = matches.group(1).replace(',', '.')
                distance_km = float(distance_str)
                
                # Сохраняем тренировку
                save_workout(user.id, 'run', distance_km)
                
                # Очищаем состояние
                context.user_data.pop('waiting_for_distance', None)
                
                # Пытаемся отправить подтверждение в ЛС
                try:
                    user_data = get_user(user.id)
                    c95_name = user_data[2] or user.first_name
                    
                    user.send_message(
                        f"✅ Пробежка записана!\n\n"
                        f"🏃‍♂️ Дистанция: {distance_km} км\n"
                        f"👤 От имени: {c95_name}\n"
                        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                    )
                except:
                    pass
                
                # В чате - простое подтверждение
                update.message.reply_text(
                    f"✅ {distance_km} км записано!",
                    reply_markup=get_chat_keyboard()
                )
                
            except ValueError:
                update.message.reply_text(
                    "❌ Не понимаю дистанцию. Введите например: 5 км",
                    reply_markup=get_chat_keyboard()
                )
        else:
            update.message.reply_text(
                "❌ Не вижу дистанцию. Введите например: 5 км",
                reply_markup=get_chat_keyboard()
            )

# Регистрация в ЛС
def start_registration(update, context):
    user = update.message.from_user
    
    message = "🔗 *Регистрация*\n\n"
    message += "1. Найдите свой профиль на s95.ru\n"
    message += "2. Скопируйте ссылку вида: https://s95.ru/athletes/XXXXX\n"
    message += "3. Отправьте мне эту ссылку\n\n"
    message += "После этого введите ваше имя как на сайте."
    
    update.message.reply_text(message, parse_mode='Markdown')
    context.user_data['registration_step'] = 'waiting_url'

# Обработчик сообщений
def handle_message(update, context):
    text = update.message.text
    user = update.message.from_user
    chat_type = update.message.chat.type
    
    if not text:
        return
    
    # Проверяем текущий шаг регистрации (только в ЛС)
    if chat_type == 'private':
        registration_step = context.user_data.get('registration_step')
        
        if registration_step == 'waiting_url':
            if 's95.ru/athletes/' in text:
                c95_url = text.strip()
                context.user_data['c95_url'] = c95_url
                context.user_data['registration_step'] = 'waiting_name'
                
                update.message.reply_text("✅ Ссылка принята!\n\n📝 Теперь введите ваше имя и фамилию как на сайте С95:")
            else:
                update.message.reply_text("❌ Это не похоже на ссылку С95. Нужна ссылка вида: https://s95.ru/athletes/XXXXX")
        
        elif registration_step == 'waiting_name':
            c95_name = text.strip()
            c95_url = context.user_data.get('c95_url')
            
            if c95_url:
                register_user(user.id, user.first_name, c95_name, c95_url)
                
                # Очищаем контекст
                context.user_data.clear()
                
                message = f"✅ *Регистрация завершена!*\n\n"
                message += f"👤 *Имя:* {c95_name}\n"
                message += f"🔗 *Профиль:* {c95_url}\n\n"
                message += "Теперь вы можете добавлять пробежки через кнопку в чате!"
                
                update.message.reply_text(message, parse_mode='Markdown', reply_markup=get_private_keyboard())
        
        else:
            # Обычное сообщение в ЛС
            if text == "📊 Моя статистика":
                show_my_stats(update, context)
            elif text == "🏆 Топ недели":
                show_top_week(update, context)
            elif text == "📈 Топ месяца":
                show_top_month(update, context)
            elif text == "🔗 Регистрация":
                start_registration(update, context)
    
    else:
        # Сообщение в чате
        if text == "🏃 Добавить пробежку":
            add_run_button(update, context)
        else:
            handle_distance_input(update, context)

# Статистика пользователя
def show_my_stats(update, context):
    user = update.message.from_user
    user_data = get_user(user.id)
    
    if not user_data:
        update.message.reply_text("❌ Сначала зарегистрируйтесь!", reply_markup=get_private_keyboard())
        return
    
    conn = sqlite3.connect('running_bot.db')
    cursor = conn.cursor()
    
    since_date_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT COUNT(*), SUM(distance) FROM workouts WHERE user_id = ? AND date > ?', (user.id, since_date_week))
    week_stats = cursor.fetchone()
    
    since_date_month = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT COUNT(*), SUM(distance) FROM workouts WHERE user_id = ? AND date > ?', (user.id, since_date_month))
    month_stats = cursor.fetchone()
    
    conn.close()
    
    c95_name, c95_url = user_data[2], user_data[3]
    
    message = f"📊 *Статистика {c95_name}*\n\n"
    if c95_url:
        message += f"🔗 *Профиль:* [С95]({c95_url})\n"
    
    if week_stats and week_stats[0]:
        message += f"\n📅 *За неделю:*\n"
        message += f"• Пробежек: {week_stats[0]}\n"
        message += f"• Дистанция: {week_stats[1]:.1f} км\n"
    
    if month_stats and month_stats[0]:
        message += f"\n📅 *За месяц:*\n"
        message += f"• Пробежек: {month_stats[0]}\n"
        message += f"• Дистанция: {month_stats[1]:.1f} км\n"
    
    if not week_stats[0] and not month_stats[0]:
        message += f"\n📭 Пока нет записанных пробежек.\nИспользуйте кнопку в чате!"
    
    update.message.reply_text(message, parse_mode='Markdown', reply_markup=get_private_keyboard())

# Функции для топа
def get_top_workouts(days=7):
    conn = sqlite3.connect('running_bot.db')
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        SELECT u.c95_name, u.c95_profile_url, SUM(w.distance) as total_distance
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

def show_top_week(update, context):
    top_list = get_top_workouts(7)
    send_top_message(update, top_list, "неделю")

def show_top_month(update, context):
    top_list = get_top_workouts(30)
    send_top_message(update, top_list, "месяц")

def send_top_message(update, top_list, period_name):
    if not top_list:
        update.message.reply_text(f"🏆 За {period_name} пока нет данных.", reply_markup=get_private_keyboard())
        return
        
    message = f"🏆 *ТОП за {period_name}:*\n\n"
    
    for i, (c95_name, c95_url, total_distance) in enumerate(top_list, 1):
        if c95_url:
            message += f"{i}. [{c95_name}]({c95_url}): {total_distance:.1f} км\n"
        else:
            message += f"{i}. {c95_name}: {total_distance:.1f} км\n"
    
    update.message.reply_text(message, parse_mode='Markdown', reply_markup=get_private_keyboard())

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Команды
    dispatcher.add_handler(CommandHandler("start", start_bot))
    
    # Обработчик всех сообщений
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    print("Бот запущен... (умные кнопки)")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
