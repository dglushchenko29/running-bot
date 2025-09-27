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
    
    # Пользователи (синхронизация с С95)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            telegram_name TEXT,
            c95_name TEXT,
            c95_profile_url TEXT,
            registered_at TEXT
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
    
    conn.commit()
    conn.close()

init_db()

# Регистрация пользователя
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

# Получение данных пользователя
def get_user(user_id):
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

# Сохранение тренировки
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

# Команда для регистрации
def start_registration(update, context):
    user = update.message.from_user
    
    # Проверяем, есть ли уже ссылка в сообщении
    if context.args:
        c95_url = context.args[0]
        if 's95.ru/athletes/' in c95_url:
            # Парсим имя из URL или запрашиваем
            update.message.reply_text(
                f"🔗 Найден профиль С95: {c95_url}\n"
                f"📝 Введите ваше имя и фамилию как на сайте С95:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]])
            )
            context.user_data['pending_registration'] = {'url': c95_url}
            return
    
    # Если нет ссылки - просим прислать
    update.message.reply_text(
        "🏃‍♂️ *Регистрация в беговом боте С95*\n\n"
        "1. Найдите свой профиль на s95.ru\n"
        "2. Скопируйте ссылку вида: https://s95.ru/athletes/12345\n"
        "3. Отправьте мне эту ссылку\n\n"
        "Или используйте команду:\n"
        "/register https://s95.ru/athletes/ваш_номер",
        parse_mode='Markdown'
    )

# Обработчик ссылок С95
def handle_c95_link(update, context):
    text = update.message.text
    user = update.message.from_user
    
    if 's95.ru/athletes/' in text:
        # Это ссылка на профиль С95
        c95_url = text.strip()
        
        # Просим ввести имя
        update.message.reply_text(
            f"🔗 Найден профиль С95!\n"
            f"📝 Теперь введите ваше имя и фамилию как на сайте:"
        )
        context.user_data['pending_registration'] = {'url': c95_url}
        
        # Пытаемся удалить сообщение со ссылкой для приватности
        try:
            update.message.delete()
        except:
            pass

# Завершение регистрации
def complete_registration(update, context):
    text = update.message.text
    user = update.message.from_user
    
    if 'pending_registration' in context.user_data:
        c95_url = context.user_data['pending_registration']['url']
        c95_name = text.strip()
        
        # Регистрируем пользователя
        register_user(user.id, user.first_name, c95_name, c95_url)
        
        # Очищаем контекст
        del context.user_data['pending_registration']
        
        # Приветствуем
        update.message.reply_text(
            f"✅ *Регистрация завершена!*\n\n"
            f"👤 *Имя:* {c95_name}\n"
            f"🔗 *Профиль:* [ссылка]({c95_url})\n\n"
            f"Теперь отправляйте тренировки в формате:\n"
            f"*10 км #япобегал*\n\n"
            f"Команды:\n"
            f"/stats - ваша статистика\n"
            f"/top_week - топ недели\n"
            f"/top_month - топ месяца",
            parse_mode='Markdown'
        )

# Обработчик тренировок
def handle_workout_message(update, context):
    text = update.message.text
    user = update.message.from_user
    
    if not text:
        return
    
    # Если идет процесс регистрации
    if 'pending_registration' in context.user_data:
        complete_registration(update, context)
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
        # Проверяем не ссылку ли на С95 отправили
        if 's95.ru/athletes/' in text:
            handle_c95_link(update, context)
        return
    
    # Ищем дистанцию
    matches = re.search(r'(\d+[.,]?\d*)\s*(км|km)', text, re.IGNORECASE)
    if matches:
        try:
            distance_str = matches.group(1).replace(',', '.')
            distance_km = float(distance_str)
            
            # Сохраняем тренировку
            save_workout(user.id, workout_type, distance_km)
            
            # Пытаемся отправить в ЛС
            try:
                user_data = get_user(user.id)
                if user_data:
                    c95_name = user_data[2] or user.first_name
                    c95_url = user_data[3]
                else:
                    c95_name = user.first_name
                    c95_url = None
                
                message = f"✅ *Тренировка записана!*\n\n🏃‍♂️ *Дистанция:* {distance_km} км\n👤 *От имени:* {c95_name}"
                
                if c95_url:
                    message += f"\n🔗 *Профиль:* [С95]({c95_url})"
                
                user.send_message(message, parse_mode='Markdown')
            except:
                # Fallback - маленький ответ в чате
                update.message.reply_text("✅", reply_to_message_id=update.message.message_id)
            
        except ValueError:
            pass

# Топ с гиперссылками
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

# Команда топа недели
def top_week(update, context):
    top_list = get_top_workouts(7)
    send_top_message(update, top_list, "неделю")

# Команда топа месяца
def top_month(update, context):
    top_list = get_top_workouts(30)
    send_top_message(update, top_list, "месяц")

def send_top_message(update, top_list, period_name):
    if not top_list:
        update.message.reply_text(f"🏆 За {period_name} пока нет данных.")
        return
        
    message = f"🏆 *ТОП за {period_name}:*\n\n"
    
    for i, (user_id, c95_name, c95_url, total_distance) in enumerate(top_list, 1):
        if c95_url and c95_name:
            # С гиперссылкой
            message += f"{i}. [{c95_name}]({c95_url}): {total_distance:.1f} км\n"
        else:
            # Без ссылки
            user_data = get_user(user_id)
            name = c95_name or (user_data[1] if user_data else f"Участник {user_id}")
            message += f"{i}. {name}: {total_distance:.1f} км\n"
    
    update.message.reply_text(message, parse_mode='Markdown')

# Статистика пользователя
def user_stats(update, context):
    user = update.message.from_user
    user_data = get_user(user.id)
    
    if not user_data:
        update.message.reply_text("📋 Сначала зарегистрируйтесь: /register")
        return
    
    conn = sqlite3.connect('workouts.db')
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
    
    c95_name, c95_url = user_data[2], user_data[3]
    
    message = f"📊 *Ваша статистика*\n\n"
    message += f"👤 *Имя:* {c95_name}\n"
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
        message += f"\n📭 Пока нет записанных тренировок.\nОтправьте: *5 км #япобегал*"
    
    update.message.reply_text(message, parse_mode='Markdown')

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Команды
    dispatcher.add_handler(CommandHandler("start", start_registration))
    dispatcher.add_handler(CommandHandler("register", start_registration))
    dispatcher.add_handler(CommandHandler("stats", user_stats))
    dispatcher.add_handler(CommandHandler("top_week", top_week))
    dispatcher.add_handler(CommandHandler("top_month", top_month))

    # Обработчик тренировок и сообщений
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_workout_message))

    print("Бот запущен... (С95 версия)")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
