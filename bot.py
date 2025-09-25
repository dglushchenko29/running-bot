import logging
import sqlite3
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# Настройка логирования чтобы видеть что происходит
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Вставьте сюда ваш токен от BotFather
import os
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8029857232:AAEi8YfRTWafF2M8jQnOQae1Xg25bdqw6Ds')

# Создаем и настраиваем базу данных SQLite
def init_db():
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    # Создаем таблицу, если ее еще нет
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            workout_type TEXT NOT NULL, -- 'run', 'bike', 'swim'
            distance REAL NOT NULL, -- Дистанция в км
            date TEXT NOT NULL -- Дата в формате YYYY-MM-DD HH:MM:SS
        )
    ''')
    conn.commit()
    conn.close()

# Вызываем функцию при старте
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

# Создаем клавиатуру с меню
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏃 Мой пробег"), KeyboardButton("🏆 Топ недели")],
        [KeyboardButton("📊 Топ месяца"), KeyboardButton("❓ Помощь")]
    ], resize_keyboard=True)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏃 Добро пожаловать в бегового бота!\n\n"
        "Выберите действие из меню ниже:",
        reply_markup=get_main_keyboard()
    )

# Функция для получения статистики пользователя
def get_user_stats(user_id, days=7):
    """Получает статистику пользователя за последние days дней"""
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Общая статистика
    cursor.execute('''
        SELECT 
            COUNT(*) as workouts_count,
            SUM(distance) as total_distance,
            AVG(distance) as avg_distance
        FROM workouts 
        WHERE user_id = ? AND date > ?
    ''', (user_id, since_date))
    
    stats = cursor.fetchone()
    
    # Статистика по типам тренировок
    cursor.execute('''
        SELECT workout_type, SUM(distance) as distance
        FROM workouts 
        WHERE user_id = ? AND date > ?
        GROUP BY workout_type
    ''', (user_id, since_date))
    
    workout_types = cursor.fetchall()
    conn.close()
    
    return stats, workout_types

# Обработчик кнопки «Мой пробег»
async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    
    # Получаем статистику за неделю
    stats, workout_types = get_user_stats(user_id, days=7)
    
    if not stats or not stats[0]:  # Если нет тренировок
        await update.message.reply_text(
            f"📊 {user.first_name}, у вас пока нет тренировок за последнюю неделю.\n\n"
            f"Отправьте фото пробежки с дистанцией и хештегом!",
            reply_markup=get_main_keyboard()
        )
        return
    
    workouts_count, total_distance, avg_distance = stats
    
    # Формируем сообщение со статистикой
    message = f"🏃 **Ваша статистика за неделю**\n\n"
    message += f"📈 **Пробежки:** {workouts_count}\n"
    message += f"📏 **Общая дистанция:** {total_distance:.1f} км\n"
    message += f"📊 **Средняя дистанция:** {avg_distance:.1f} км\n\n"
    
    # Добавляем статистику по типам тренировок
    if workout_types:
        message += "**По видам спорта:**\n"
        for workout_type, distance in workout_types:
            type_emoji = {
                'run': '🏃‍♂️',
                'bike': '🚴‍♂️', 
                'swim': '🏊‍♂️'
            }.get(workout_type, '✅')
            
            type_name = {
                'run': 'Бег',
                'bike': 'Вело',
                'swim': 'Плавание'
            }.get(workout_type, 'Тренировка')
            
            message += f"{type_emoji} {type_name}: {distance:.1f} км\n"
    
    message += f"\n💪 Так держать, {user.first_name}!"
    
    await update.message.reply_text(
        message,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

# Команда помощи
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 **Как пользоваться ботом:**

🏃 **Отслеживание тренировок:**
- Отправьте фото тренировки
- В подписи укажите дистанцию и хештег:
  • Бег: "5 км #япобегал"
  • Вело: "20 км #япокрутил"
  • Плавание: "1 км #япоплавал"

📊 **Статистика:**
- 🏃 Мой пробег - ваша статистика за неделю
- 🏆 Топ недели - рейтинг участников
- 📊 Топ месяца - рейтинг за месяц

💡 **Пример сообщения:**
"10.5 км #япобегал"
"""
    await update.message.reply_text(
        help_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

async def handle_photo_with_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    caption = message.caption # Это тот самый текст под фото

    if not caption:
        # Если подписи нет, игнорируем сообщение
        return

    # Приводим текст к нижнему регистру для удобства поиска
    caption_lower = caption.lower()

    # Определяем тип активности по тегам
    workout_type = None
    if '#япобегал' in caption_lower:
        workout_type = 'run'
    elif '#япокрутил' in caption_lower:
        workout_type = 'bike'
    elif '#япоплавал' in caption_lower:
        workout_type = 'swim'

    # Если ни одного тега не нашли, выходим
    if not workout_type:
        return

    # Ищем число (целое или дробное), обозначающее дистанцию
    distance_pattern = r'(\d+[.,]?\d*)\s*(км|km|КМ)'
    matches = re.search(distance_pattern, caption)

    if matches:
        try:
            # Заменяем запятую на точку и преобразуем в число
            distance_str = matches.group(1).replace(',', '.')
            distance_km = float(distance_str)

            # Сохраняем в базу данных
            user_name = user.first_name or user.username or "Аноним"
            save_workout(user.id, user_name, workout_type, distance_km)

            # Отправляем подтверждение пользователю
            await message.reply_text(
                f"✅ Записано! {distance_km} км ({workout_type})",
                reply_markup=get_main_keyboard()
            )
            
        except ValueError:
            # Если не получилось преобразовать в число
            await message.reply_text(
                "❌ Не могу понять дистанцию. Напишите, например, '10 км'.",
                reply_markup=get_main_keyboard()
            )
    else:
        # Если не нашли шаблон с дистанцией
        await message.reply_text(
            "❌ Не вижу дистанцию в формате '5 км' или '10.5 km'.",
            reply_markup=get_main_keyboard()
        )

def get_top_workouts(workout_type=None, days=7):
    """Функция для получения топа из базы данных за последние days дней"""
    conn = sqlite3.connect('workouts.db')
    cursor = conn.cursor()
    
    # Рассчитываем дату, с которой начинаем отсчет
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Строим SQL-запрос в зависимости от того, нужен ли конкретный тип тренировки
    if workout_type:
        cursor.execute('''
            SELECT user_name, SUM(distance) as total_distance
            FROM workouts
            WHERE date > ? AND workout_type = ?
            GROUP BY user_id
            ORDER BY total_distance DESC
            LIMIT 10
        ''', (since_date, workout_type))
    else:
        cursor.execute('''
            SELECT user_name, SUM(distance) as total_distance
            FROM workouts
            WHERE date > ?
            GROUP BY user_id
            ORDER BY total_distance DESC
            LIMIT 10
        ''', (since_date,))
    
    top_list = cursor.fetchall()
    conn.close()
    return top_list

async def top_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /top_week"""
    top_list = get_top_workouts(days=7)
    await send_top_message(update, top_list, "неделю")

async def top_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /top_month"""
    top_list = get_top_workouts(days=30)
    await send_top_message(update, top_list, "месяц")

async def send_top_message(update, top_list, period_name):
    """Вспомогательная функция для форматирования и отправки топа"""
    if not top_list:
        await update.message.reply_text(
            f"🏆 За {period_name} пока нет данных о тренировках.",
            reply_markup=get_main_keyboard()
        )
        return

    message_text = f"🏆 ТОП-10 за {period_name}:\n\n"
    for i, (user_name, total_distance) in enumerate(top_list, 1):
        message_text += f"{i}. {user_name}: {total_distance:.1f} км\n"

    await update.message.reply_text(
        message_text,
        reply_markup=get_main_keyboard()
    )

def main():
    # Создаем updater вместо application
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Добавляем обработчики команд
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("top_week", top_week))
    dispatcher.add_handler(CommandHandler("top_month", top_month))
    dispatcher.add_handler(CommandHandler("help", help_command))

    # Добавляем обработчики текстовых сообщений (кнопок)
    dispatcher.add_handler(MessageHandler(Filters.text & Filters.regex('^🏃 Мой пробег$'), my_stats))
    dispatcher.add_handler(MessageHandler(Filters.text & Filters.regex('^🏆 Топ недели$'), top_week))
    dispatcher.add_handler(MessageHandler(Filters.text & Filters.regex('^📊 Топ месяца$'), top_month))
    dispatcher.add_handler(MessageHandler(Filters.text & Filters.regex('^❓ Помощь$'), help_command))

    # Обработчик для сообщений с фото и подписью
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo_with_text))

    # Запускаем бота
    print("Бот запущен...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
