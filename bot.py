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
    
    # Пользователи
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            telegram_name TEXT,
            c95_name TEXT,
            c95_profile_url TEXT,
            club_id INTEGER,
            registered_at TEXT
        )
    ''')
    
    # Клубы
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clubs (
            club_id INTEGER PRIMARY KEY,
            club_name TEXT,
            club_url TEXT
        )
    ''')
    
    # Тренировки
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
    
    # Заполняем клубы
    clubs_data = [
        (1, "Беговая братия", "https://s95.ru/clubs/1"),
        (2, "Марафонцы", "https://s95.ru/clubs/2"),
        (3, "Спринтеры", "https://s95.ru/clubs/3"),
        (4, "Ультрамарафонцы", "https://s95.ru/clubs/4"),
        (5, "Любители", "https://s95.ru/clubs/5")
    ]
    
    cursor.executemany('''
        INSERT OR IGNORE INTO clubs (club_id, club_name, club_url)
        VALUES (?, ?, ?)
    ''', clubs_data)
    
    conn.commit()
    conn.close()

init_db()

def register_user(user_id, telegram_name, c95_name, c95_url, club_id):
    conn = sqlite3.connect('running_bot.db')
    cursor = conn.cursor()
    registered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, telegram_name, c95_name, c95_profile_url, club_id, registered_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, telegram_name, c95_name, c95_url, club_id, registered_at))
    
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('running_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.*, c.club_name 
        FROM users u 
        LEFT JOIN clubs c ON u.club_id = c.club_id 
        WHERE u.user_id = ?
    ''', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_clubs():
    conn = sqlite3.connect('running_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT club_id, club_name FROM clubs ORDER BY club_name')
    clubs = cursor.fetchall()
    conn.close()
    return clubs

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

# Главное меню
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Моя статистика"), KeyboardButton("🏆 Топ недели")],
        [KeyboardButton("📈 Топ месяца"), KeyboardButton("🔗 Зарегистрироваться")]
    ], resize_keyboard=True)

# Команда старта
def start_bot(update, context):
    user = update.message.from_user
    user_data = get_user(user.id)
    
    if user_data:
        # Уже зарегистрирован
        message = f"🏃 С возвращением, {user_data[2]}!\n\n"
        message += f"👤 Клуб: {user_data[5] or 'Не указан'}\n"
        message += "Выберите действие:"
    else:
        # Новый пользователь
        message = "🏃‍♂️ Добро пожаловать в бегового бота С95!\n\n"
        message += "📊 Я помогу отслеживать ваши тренировки и соревноваться с другими бегунами.\n\n"
        message += "Чтобы начать, нажмите '🔗 Зарегистрироваться'"
    
    update.message.reply_text(message, reply_markup=get_main_keyboard())

# Начало регистрации
def start_registration(update, context):
    message = "🔗 *Регистрация в беговом боте*\n\n"
    message += "1. Найдите свой профиль на s95.ru\n"
    message += "2. Скопируйте ссылку вида: https://s95.ru/athletes/XXXXX\n"
    message += "3. Отправьте мне эту ссылку\n\n"
    message += "После этого выберите свой клуб из списка."
    
    update.message.reply_text(message, parse_mode='Markdown')
    context.user_data['registration_step'] = 'waiting_url'

# Обработчик сообщений
def handle_message(update, context):
    text = update.message.text
    user = update.message.from_user
    
    if not text:
        return
    
    # Проверяем текущий шаг регистрации
    registration_step = context.user_data.get('registration_step')
    
    if registration_step == 'waiting_url':
        # Ждем ссылку на С95
        if 's95.ru/athletes/' in text:
            c95_url = text.strip()
            context.user_data['c95_url'] = c95_url
            context.user_data['registration_step'] = 'waiting_name'
            
            update.message.reply_text("✅ Ссылка принята!\n\n📝 Теперь введите ваше имя и фамилию как на сайте С95:")
        else:
            update.message.reply_text("❌ Это не похоже на ссылку С95. Нужна ссылка вида: https://s95.ru/athletes/XXXXX")
    
    elif registration_step == 'waiting_name':
        # Ждем имя
        c95_name = text.strip()
        context.user_data['c95_name'] = c95_name
        context.user_data['registration_step'] = 'waiting_club'
        
        # Показываем клубы для выбора
        clubs = get_clubs()
        keyboard = []
        for club_id, club_name in clubs:
            keyboard.append([InlineKeyboardButton(club_name, callback_data=f"club_{club_id}")])
        
        update.message.reply_text(
            "✅ Имя сохранено!\n\n🏢 Теперь выберите ваш клуб:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    else:
        # Обычное сообщение - проверяем на тренировку
        handle_workout_message(update, context)

# Обработчик выбора клуба
def handle_club_selection(update, context):
    query = update.callback_query
    user = query.from_user
    
    if query.data.startswith('club_'):
        club_id = int(query.data.split('_')[1])
        
        # Завершаем регистрацию
        c95_url = context.user_data.get('c95_url')
        c95_name = context.user_data.get('c95_name')
        
        if c95_url and c95_name:
            register_user(user.id, user.first_name, c95_name, c95_url, club_id)
            
            # Очищаем контекст
            context.user_data.clear()
            
            # Получаем название клуба
            clubs = get_clubs()
            club_name = next((name for cid, name in clubs if cid == club_id), "Неизвестный клуб")
            
            message = f"✅ *Регистрация завершена!*\n\n"
            message += f"👤 *Имя:* {c95_name}\n"
            message += f"🏢 *Клуб:* {club_name}\n"
            message += f"🔗 *Профиль:* {c95_url}\n\n"
            message += "Теперь отправляйте тренировки в формате:\n"
            message += "*10 км #япобегал*"
            
            query.edit_message_text(message, parse_mode='Markdown')
            query.message.reply_text("🎉 Теперь вы можете использовать все функции бота!", reply_markup=get_main_keyboard())
    
    query.answer()

# Обработчик тренировок
def handle_workout_message(update, context):
    text = update.message.text
    user = update.message.from_user
    
    text_lower = text.lower()
    
    workout_type = None
    if '#япобегал' in text_lower:
        workout_type = 'run'
    elif '#япокрутил' in text_lower:
        workout_type = 'bike'
    elif '#япоплавал' in text_lower:
        workout_type = 'swim'
    else:
        return
    
    matches = re.search(r'(\d+[.,]?\d*)\s*(км|km)', text, re.IGNORECASE)
    if matches:
        try:
            distance_str = matches.group(1).replace(',', '.')
            distance_km = float(distance_str)
            
            save_workout(user.id, workout_type, distance_km)
            
            # Пытаемся отправить в ЛС
            try:
                user_data = get_user(user.id)
                if user_data:
                    c95_name = user_data[2] or user.first_name
                else:
                    c95_name = user.first_name
                
                user.send_message(f"✅ Тренировка записана!\n\n🏃‍♂️ Дистанция: {distance_km} км\n👤 От имени: {c95_name}")
            except:
                update.message.reply_text("✅", reply_to_message_id=update.message.message_id)
            
        except ValueError:
            pass

# Кнопка "Моя статистика"
def show_my_stats(update, context):
    user = update.message.from_user
    user_data = get_user(user.id)
    
    if not user_data:
        update.message.reply_text("❌ Сначала зарегистрируйтесь!", reply_markup=get_main_keyboard())
        return
    
    conn = sqlite3.connect('running_bot.db')
    cursor = conn.cursor()
    
    # Статистика за неделю
    since_date_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT COUNT(*), SUM(distance) FROM workouts WHERE user_id = ? AND date > ?', (user.id, since_date_week))
    week_stats = cursor.fetchone()
    
    # Статистика за месяц
    since_date_month = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('SELECT COUNT(*), SUM(distance) FROM workouts WHERE user_id = ? AND date > ?', (user.id, since_date_month))
    month_stats = cursor.fetchone()
    
    conn.close()
    
    c95_name, c95_url, club_name = user_data[2], user_data[3], user_data[5]
    
    message = f"📊 *Статистика {c95_name}*\n\n"
    message += f"🏢 *Клуб:* {club_name or 'Не указан'}\n"
    
    if week_stats and week_stats[0]:
        message += f"\n📅 *За неделю:*\n"
        message += f"• Пробежек: {week_stats[0]}\n"
        message += f"• Дистанция: {week_stats[1]:.1f} км\n"
    
    if month_stats and month_stats[0]:
        message += f"\n📅 *За месяц:*\n"
        message += f"• Пробежек: {month_stats[0]}\n"
        message += f"• Дистанция: {month_stats[1]:.1f} км\n"
    
    if not week_stats[0] and not month_stats[0]:
        message += f"\n📭 Пока нет записанных тренировок.\nОтправьте: *5 км #япобегал*"
    
    update.message.reply_text(message, parse_mode='Markdown', reply_markup=get_main_keyboard())

# Функции для топа
def get_top_workouts(days=7):
    conn = sqlite3.connect('running_bot.db')
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        SELECT u.c95_name, u.c95_profile_url, c.club_name, SUM(w.distance) as total_distance
        FROM workouts w
        JOIN users u ON w.user_id = u.user_id
        LEFT JOIN clubs c ON u.club_id = c.club_id
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
        update.message.reply_text(f"🏆 За {period_name} пока нет данных.", reply_markup=get_main_keyboard())
        return
        
    message = f"🏆 *ТОП за {period_name}:*\n\n"
    
    for i, (c95_name, c95_url, club_name, total_distance) in enumerate(top_list, 1):
        if c95_url:
            message += f"{i}. [{c95_name}]({c95_url}): {total_distance:.1f} км\n"
            if club_name:
                message += f"   🏢 {club_name}\n"
        else:
            message += f"{i}. {c95_name}: {total_distance:.1f} км\n"
            if club_name:
                message += f"   🏢 {club_name}\n"
        message += "\n"
    
    update.message.reply_text(message, parse_mode='Markdown', reply_markup=get_main_keyboard())

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Команды
    dispatcher.add_handler(CommandHandler("start", start_bot))
    
    # Обработчики кнопок
    dispatcher.add_handler(MessageHandler(Filters.text("📊 Моя статистика"), show_my_stats))
    dispatcher.add_handler(MessageHandler(Filters.text("🏆 Топ недели"), show_top_week))
    dispatcher.add_handler(MessageHandler(Filters.text("📈 Топ месяца"), show_top_month))
    dispatcher.add_handler(MessageHandler(Filters.text("🔗 Зарегистрироваться"), start_registration))
    
    # Обработчики callback
    dispatcher.add_handler(CallbackQueryHandler(handle_club_selection, pattern='^club_'))
    
    # Обработчик сообщений
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    print("Бот запущен... (улучшенная версия с кнопками)")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
