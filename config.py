import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    
    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("❌ BOT_TOKEN не найден в переменных окружения!")
        if not cls.ADMIN_IDS:
            raise ValueError("❌ ADMIN_IDS не найден в переменных окружения!")
        print("✅ Конфигурация загружена успешно")
    
    @classmethod
    def get_group_chat_id(cls):
        """Получить ID группового чата с проверкой"""
        if not cls.GROUP_CHAT_ID:
            raise ValueError("❌ GROUP_CHAT_ID не настроен в .env файле!")
        try:
            return int(cls.GROUP_CHAT_ID)
        except ValueError:
            raise ValueError("❌ GROUP_CHAT_ID должен быть числом!")