import os
from database import Database
from bot import RunningBot

def main():
    # Инициализация базы данных
    db = Database()
    
    # Получение токена бота
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set")
    
    # Создание и запуск бота
    bot = RunningBot(BOT_TOKEN, db)
    bot.run()

if __name__ == "__main__":
    main()
