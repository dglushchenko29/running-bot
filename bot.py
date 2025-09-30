import os
import logging
import re
from datetime import datetime
from typing import Optional

from telegram import (
    Update, 
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ContextTypes, 
    filters,
    ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import Database

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class RunningBot:
    def __init__(self, token: str, db: Database):
        self.token = token
        self.db = db
        self.application = Application.builder().token(token).build()
        self.scheduler = AsyncIOScheduler()
        
        self._setup_handlers()
        self._setup_scheduler()
    
    def _setup_handlers(self):
        # Команды для бота
        self.application.add_handler(CommandHandler("start", self._start))
        self.application.add_handler(CommandHandler("stats", self._stats))
        self.application.add_handler(CommandHandler("top_week", self._top_week))
        self.application.add_handler(CommandHandler("top_month", self._top_month))
        self.application.add_handler(CommandHandler("help", self._help))
        
        # Обработчик сообщений в группах (для парсинга #япобегал)
        self.application.add_handler(MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT, 
            self._handle_group_message
        ))
        
        # Обработчик сообщений в ЛС
        self.application.add_handler(MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT, 
            self._handle_private_message
        ))
        
        # Обработчик когда бот добавляется в группу
        self.application.add_handler(MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            self._handle_bot_added_to_group
        ))
    
    def _setup_scheduler(self):
        """Настройка планировщика для автоматических рассылок"""
        # Каждый понедельник в 10:00
        self.scheduler.add_job(
            self._send_weekly_stats,
            CronTrigger(day_of_week=0, hour=10, minute=0),  # 0 = понедельник
            id='weekly_stats'
        )
        
        # Первое число каждого месяца в 10:00
        self.scheduler.add_job(
            self._send_monthly_stats,
            CronTrigger(day=1, hour=10, minute=0),
            id='monthly_stats'
        )
    
    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        chat = update.effective_chat
        
        self.db.add_user(user.id, user.first_name, user.last_name, user.username)
        
        if chat.type == "private":
            await update.message.reply_text(
                f"🏃 Привет, {user.first_name}!\n\n"
                "Я бот для учета пробежек! Вот что я умею:\n\n"
                "В ЛИЧНЫХ СООБЩЕНИЯХ:\n"
                "/stats - твоя статистика\n"
                "/stats @username - статистика другого бегуна\n"
                "/top_week - топ за неделю\n"
                "/top_month - топ за месяц\n\n"
                "В ГРУППОВОМ ЧАТЕ:\n"
                "Просто отправь сообщение с хештегом:\n"
                "#япобегал 5.2км\n"
                "и я автоматически запишу твою пробежку!\n\n"
                "Каждый понедельник в 10:00 я публикую топ за неделю, "
                "а 1-го числа каждого месяца - топ за месяц!"
            )
        else:
            await update.message.reply_text(
                "✅ Бот активирован! Теперь я буду автоматически записывать пробежки "
                "из сообщений с хештегом #япобегал\n\n"
                "Пример: #япобегал 5.2км\n\n"
                "Для личной статистики напишите мне в ЛС!"
            )
            # Сохраняем чат для рассылки
            self.db.add_chat(chat.id, chat.title)
    
    async def _stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику"""
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type != "private":
            await update.message.reply_text(
                "📊 Для просмотра статистики напишите мне в личные сообщения!"
            )
            return
        
        target_user = user
        if context.args:
            # Если указан username, ищем этого пользователя
            username = context.args[0].replace('@', '')
            # Здесь нужно будет доработать поиск по username
            # Показываем статистику текущего пользователя
            pass
        
        stats = self.db.get_user_stats(target_user.id)
        
        if stats['total_runs'] == 0:
            await update.message.reply_text(
                "📊 У тебя пока нет пробежек.\n\n"
                "Добавь первую пробежку отправив в группе сообщение:\n"
                "#япобегал 5.2км"
            )
        else:
            await update.message.reply_text(
                f"📊 Статистика {target_user.first_name}:\n\n"
                f"🏃 Всего пробежек: {stats['total_runs']}\n"
                f"📏 Общая дистанция: {stats['total_distance']:.1f} км\n"
                f"📈 Средняя дистанция: {stats['average_distance']:.1f} км"
            )
    
    async def _top_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Топ за неделю"""
        chat = update.effective_chat
        
        if chat.type != "private":
            await update.message.reply_text(
                "📈 Для просмотра топа напишите мне в личные сообщения!"
            )
            return
        
        stats = self.db.get_week_stats()
        await self._send_top_list(update, stats, "неделю")
    
    async def _top_month(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Топ за месяц"""
        chat = update.effective_chat
        
        if chat.type != "private":
            await update.message.reply_text(
                "📈 Для просмотра топа напишите мне в личные сообщения!"
            )
            return
        
        stats = self.db.get_month_stats()
        await self._send_top_list(update, stats, "месяц")
    
    async def _send_top_list(self, update: Update, stats: list, period: str):
        """Отправка списка топа"""
        if not stats:
            await update.message.reply_text(f"📭 За этот {period} пока нет пробежек")
            return
        
        text = f"🏆 ТОП бегунов за {period}:\n\n"
        
        for i, runner in enumerate(stats[:10], 1):  # Топ-10
            username = f"@{runner['username']}" if runner['username'] else runner['first_name']
            text += f"{i}. {username} - {runner['total_distance']:.1f} км ({runner['runs_count']} пробежек)\n"
        
        await update.message.reply_text(text)
    
    async def _help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        await update.message.reply_text(
            "🏃 Помощь по беговому боту:\n\n"
            "В ГРУППЕ:\n"
            "• Отправь сообщение: #япобегал 5.2км\n"
            "• Я автоматически запишу пробежку\n\n"
            "В ЛИЧНЫХ СООБЩЕНИЯХ:\n"
            "/stats - твоя статистика\n"
            "/top_week - топ за неделю\n"
            "/top_month - топ за месяц\n"
            "/help - эта справка\n\n"
            "Автоматически:\n"
            "• Каждый понедельник в 10:00 - топ за неделю\n"
            "• 1-го числа каждого месяца в 10:00 - топ за месяц"
        )
    
    async def _handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик сообщений в группах - парсинг #япобегал"""
        message = update.message
        text = message.text
        
        if not text or '#япобегал' not in text.lower():
            return
        
        # Парсим дистанцию из сообщения
        distance = self._parse_distance_from_text(text)
        
        if distance:
            user = message.from_user
            self.db.add_user(user.id, user.first_name, user.last_name, user.username)
            self.db.add_run(user.id, distance)
            
            logger.info(f"Записана пробежка: {user.first_name} - {distance} км")
            
            # Отправляем подтверждение в ЛС пользователю
            try:
                stats = self.db.get_user_stats(user.id)
                await context.bot.send_message(
                    chat_id=user.id,
                    text=f"✅ Пробежка записана!\n"
                         f"Дистанция: {distance} км\n"
                         f"Всего пробежек: {stats['total_runs']}\n"
                         f"Общая дистанция: {stats['total_distance']:.1f} км"
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить подтверждение пользователю {user.id}: {e}")
    
    async def _handle_private_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик сообщений в ЛС"""
        message = update.message
        text = message.text
        
        # Если сообщение содержит #япобегал, парсим его
        if text and '#япобегал' in text.lower():
            distance = self._parse_distance_from_text(text)
            if distance:
                user = message.from_user
                self.db.add_user(user.id, user.first_name, user.last_name, user.username)
                self.db.add_run(user.id, distance)
                
                stats = self.db.get_user_stats(user.id)
                await message.reply_text(
                    f"✅ Пробежка записана!\n"
                    f"Дистанция: {distance} км\n"
                    f"Всего пробежек: {stats['total_runs']}\n"
                    f"Общая дистанция: {stats['total_distance']:.1f} км"
                )
            else:
                await message.reply_text(
                    "❌ Не удалось распознать дистанцию.\n"
                    "Правильный формат: #япобегал 5.2км\n"
                    "Или просто: #япобегал 10 км"
                )
    
    async def _handle_bot_added_to_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик добавления бота в группу"""
        chat = update.effective_chat
        new_members = update.message.new_chat_members
        
        # Проверяем, добавили ли самого бота
        bot_id = context.bot.id
        if any(member.id == bot_id for member in new_members):
            self.db.add_chat(chat.id, chat.title)
            
            await update.message.reply_text(
                "✅ Бот для учета пробежек активирован!\n\n"
                "Как использовать:\n"
                "1. Отправьте сообщение: #япобегал 5.2км\n"
                "2. Бот автоматически запишет пробежку\n"
                "3. Для статистики напишите боту в ЛС\n\n"
                "Каждый понедельник в 10:00 бот публикует топ за неделю!"
            )
    
    async def _send_weekly_stats(self):
        """Автоматическая отправка топа за неделю"""
        stats = self.db.get_week_stats()
        if not stats:
            return
        
        text = "🏆 ТОП бегунов за неделю:\n\n"
        
        for i, runner in enumerate(stats[:10], 1):
            username = f"@{runner['username']}" if runner['username'] else runner['first_name']
            text += f"{i}. {username} - {runner['total_distance']:.1f} км ({runner['runs_count']} пробежек)\n"
        
        # Отправляем во все зарегистрированные чаты
        for chat_id in self.db.get_chats():
            try:
                await self.application.bot.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logger.error(f"Не удалось отправить weekly stats в чат {chat_id}: {e}")
    
    async def _send_monthly_stats(self):
        """Автоматическая отправка топа за месяц"""
        stats = self.db.get_month_stats()
        if not stats:
            return
        
        text = "🏆 ТОП бегунов за месяц:\n\n"
        
        for i, runner in enumerate(stats[:10], 1):
            username = f"@{runner['username']}" if runner['username'] else runner['first_name']
            text += f"{i}. {username} - {runner['total_distance']:.1f} км ({runner['runs_count']} пробежек)\n"
        
        # Отправляем во все зарегистрированные чаты
        for chat_id in self.db.get_chats():
            try:
                await self.application.bot.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logger.error(f"Не удалось отправить monthly stats в чат {chat_id}: {e}")
    
    def _parse_distance_from_text(self, text: str) -> Optional[float]:
        """Парсит дистанцию из текста сообщения"""
        try:
            # Ищем числа в тексте после хештега
            text = text.lower().replace('#япобегал', '').strip()
            
            # Удаляем все не-цифры и не-точки, кроме пробелов
            clean_text = re.sub(r'[^\d\s.,]', '', text)
            
            # Ищем первое число
            match = re.search(r'(\d+[.,]?\d*)', clean_text)
            if match:
                number_str = match.group(1).replace(',', '.')
                distance = float(number_str)
                return distance if distance > 0 else None
        except (ValueError, AttributeError):
            pass
        
        return None
    
    def run(self):
        """Запуск бота"""
        self.scheduler.start()
        logger.info("Бот запущен...")
        logger.info("Планировщик запущен: понедельник 10:00 (неделя), 1 число 10:00 (месяц)")
        self.application.run_polling()
