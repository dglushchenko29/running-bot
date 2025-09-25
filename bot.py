import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования чтобы видеть что происходит
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Вставьте сюда ваш токен от BotFather
BOT_TOKEN = "8029857232:AAEi8YfRTWafF2M8jQnOQae1Xg25bdqw6Ds"

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
    # Это простой вариант, можно улучшить
    import re
    # Шаблон ищет числа, возможно с точкой, и возможные единицы измерения (km, км)
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

            # Отправляем подтверждение пользователю (можно убрать, если не нужно)
            await message.reply_text(f"✅ Записано! {distance_km} км ({workout_type})")
            
        except ValueError:
            # Если не получилось преобразовать в число
            await message.reply_text("❌ Не могу понять дистанцию. Напишите, например, '10 км'.")
    else:
        # Если не нашли шаблон с дистанцией
        await message.reply_text("❌ Не вижу дистанцию в формате '5 км' или '10.5 km'.")
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
        await update.message.reply_text(f"🏆 За {period_name} пока нет данных о тренировках.")
        return

    message_text = f"🏆 ТОП-10 за {period_name}:\n\n"
    for i, (user_name, total_distance) in enumerate(top_list, 1):
        message_text += f"{i}. {user_name}: {total_distance:.1f} км\n"

    await update.message.reply_text(message_text)
def main():
    # Создаем приложение и передаем ему токен
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики
    # Обработчик для сообщений с фото и подписью
    application.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r".*"), handle_photo_with_text))
    
    # Обработчики команд
    application.add_handler(CommandHandler("top_week", top_week))
    application.add_handler(CommandHandler("top_month", top_month))

    # Запускаем бота на опрос серверов Telegram
    print("Бот запущен...")
    application.run_polling()

# Точка входа в программу
if __name__ == '__main__':
    main()
