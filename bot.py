import os
import logging
import re
from datetime import datetime
from typing import Optional

from telegram import (
    Update, 
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    MenuButtonCommands
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
        self.application.add_handler(CommandHandler("add_runner", self._add_runner))
        
        # Обработчик callback кнопок
        self.application.add_handler(CallbackQueryHandler(self._button_handler))
        
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
    
    async def _setup_menu_buttons(self, application):
        """Настройка кнопок меню бота"""
        commands = [
            BotCommand("start", "Регистрация и начало работы"),
            BotCommand("stats", "Моя статистика"),
            BotCommand("top_week", "Топ за неделю"),
            BotCommand("top_month", "Топ за месяц"),
            BotCommand("help", "Помощь"),
            BotCommand("add_runner", "Добавить пробежку")
        ]
        
        await application.bot.set_my_commands(commands)
        await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    
    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        chat = update.effective_chat
        
        self.db.add_user(user.id, user.first_name, user.last_name, user.username)
        
        if chat.type == "private":
            # Создаем клавиатуру для ЛС
            keyboard = [
                ["📊 Моя статистика", "🏆 Топ недели"],
                ["📈 Топ месяца", "❓ Помощь"],
                ["➕ Добавить пробежку"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                f"🏃 Привет, {user.first_name}!\n\n"
                "Я бот для учета пробежек в нашем чате! Вот что я умею:\n\n"
                "📱 В ЛИЧНЫХ СООБЩЕНИЯХ:\n"
                "• Смотри свою статистику\n"
                "• Смотри топы за неделю/месяц\n"
                "• Добавляй пробежки\n\n"
                "💬 В ГРУППОВОМ ЧАТЕ:\n"
                "• Нажми кнопку 'Добавить пробежку' в меню\n"
                "• Или отправь сообщение: #япобегал 5.2км\n"
                "• Я автоматически запишу твою пробежку!\n\n"
                "📅 Автоматически:\n"
                "• Каждый понедельник в 10:00 - топ за неделю\n"
                "• 1-го числа каждого месяца - топ за месяц",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "✅ Бот активирован! Теперь я буду автоматически записывать пробежки "
                "из сообщений с хештегом #япобегал\n\n"
                "Как добавить пробежку:\n"
                "1. Нажмите кнопку 'Добавить пробежку' в меню бота\n"
                "2. Или отправьте сообщение: #япобегал 5.2км\n\n"
                "Для личной статистики напишите мне в ЛС!"
            )
            # Сохраняем чат для рассылки
            self.db.add_chat(chat.id, chat.title)
    
    async def _add_runner(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды add_runner - для кнопки в меню группы"""
        chat = update.effective_chat
        
        if chat.type == "private":
            await update.message.reply_text(
                "Чтобы добавить пробежку, просто отправь мне сообщение в формате:\n\n"
                "#япобегал 5.2км\n\n"
                "Или используй кнопки ниже 👇"
            )
        else:
            await update.message.reply_text(
                "🏃 Чтобы добавить пробежку:\n\n"
                "Просто отправьте в чат сообщение:\n"
                "#япобегал 5.2км\n\n"
                "Или напишите боту в личные сообщения для более подробной статистики!"
            )
    
    async def _button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        
        if data == "my_stats":
            await self._show_user_stats(query, user)
        elif data == "top_week":
            await self._show_top_week(query)
        elif data == "top_month":
            await self._show_top_month(query)
        elif data == "add_run":
            await self._show_add_run_help(query)
    
    async def _show_user_stats(self, query, user):
        """Показать статистику пользователя"""
        stats = self.db.get_user_stats(user.id)
        
        if stats['total_runs'] == 0:
            await query.edit_message_text(
                "📊 У тебя пока нет пробежек.\n\n"
                "Добавь первую пробежку отправив в группе сообщение:\n"
                "#япобегал 5.2км\n\n"
                "Или напиши мне в ЛС то же сообщение!"
            )
        else:
            await query.edit_message_text(
                f"📊 Твоя статистика:\n\n"
                f"🏃 Всего пробежек: {stats['total_runs']}\n"
                f"📏 Общая дистанция: {stats['total_distance']:.1f} км\n"
                f"📈 Средняя дистанция: {stats['average_distance']:.1f} км\n\n"
                "Продолжай в том же духе! 💪"
            )
    
    async def _show_top_week(self, query):
        """Показать топ за неделю"""
        stats = self.db.get_week_stats()
        await self._send_top_to_query(query, stats, "неделю")
    
    async def _show_top_month(self, query):
        """Показать топ за месяц"""
        stats = self.db.get_month_stats()
        await self._send_top_to_query(query, stats, "месяц")
    
    async def _send_top_to_query(self, query, stats, period):
        """Отправить топ в callback query"""
        if not stats:
            await query.edit_message_text(f"📭 За эту {period} пока нет пробежек")
            return
        
        text = f"🏆 ТОП бегунов за {period}:\n\n"
        
        for i, runner in enumerate(stats[:10], 1):
            username = f"@{runner['username']}" if runner['username'] else runner['first_name']
            text += f"{i}. {username} - {runner['total_distance']:.1f} км ({runner['runs_count']} пробежек)\n"
        
        await query.edit_message_text(text)
    
    async def _show_add_run_help(self, query):
        """Показать помощь по добавлению пробежки"""
        await query.edit_message_text(
            "➕ Добавить пробежку:\n\n"
            "В ГРУППЕ:\n"
            "Отправь сообщение:\n"
            "#япобегал 5.2км\n\n"
            "В ЛИЧНЫХ СООБЩЕНИЯХ:\n"
            "Отправь мне сообщение:\n"
            "#япобегал 5.2км\n\n"
            "Формат:\n"
            "• #япобегал 5 км\n"
            "• #япобегал 10.5км\n"
            "• #япобегал 7.2 км"
        )
    
    async def _stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику"""
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type != "private":
            await update.message.reply_text(
                "📊 Для просмотра статистики напишите мне в личные сообщения!"
            )
            return
        
        stats = self.db.get_user_stats(user.id)
        
        if stats['total_runs'] == 0:
            await update.message.reply_text(
                "📊 У тебя пока нет пробежек.\n\n"
                "Добавь первую пробежку отправив в группе сообщение:\n"
                "#япобегал 5.2км\n\n"
                "Или напиши мне в ЛС то же сообщение!"
            )
        else:
            await update.message.reply_text(
                f"📊 Твоя статистика:\n\n"
                f"🏃 Всего пробежек: {stats['total_runs']}\n"
                f"📏 Общая дистанция: {stats['total_distance']:.1f} км\n"
                f"📈 Средняя дистанция: {stats['average_distance']:.1f} км\n\n"
                "Продолжай в том же духе! 💪"
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
        
        for i, runner in enumerate(stats[:10], 1):
            username = f"@{runner['username']}" if runner['username'] else runner['first_name']
            text += f"{i}. {username} - {runner['total_distance']:.1f} км ({runner['runs_count']} пробежек)\n"
        
        await update.message.reply_text(text)
    
    async def _help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        await update.message.reply_text(
            "🏃 Помощь по беговому боту:\n\n"
            "В ГРУППЕ:\n"
            "• Нажми 'Добавить пробежку' в меню бота\n"
            "• Или отправь: #япобегал 5.2км\n\n"
            "В ЛИЧНЫХ СООБЩЕНИЯХ:\n"
            "• Используй кнопки меню\n"
            "• Или команды:\n"
            "/stats - твоя статистика\n"
            "/top_week - топ за неделю\n"
            "/top_month - топ за месяц\n"
            "/help - эта справка\n\n"
            "📅 Автоматически:\n"
            "• Понедельник 10:00 - топ за неделю\n"
            "• 1 число месяца 10:00 - топ за месяц"
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
                         f"Общая дистанция: {stats['total_distance']:.1f} км\n\n"
                         f"Так держать! 💪"
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить подтверждение пользователю {user.id}: {e}")
    
    async def _handle_private_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик сообщений в ЛС"""
        message = update.message
        text = message.text
        user = message.from_user
        
        # Обработка текстовых кнопок
        if text == "📊 Моя статистика":
            await self._stats(update, context)
        elif text == "🏆 Топ недели":
            await self._top_week(update, context)
        elif text == "📈 Топ месяца":
            await self._top_month(update, context)
        elif text == "❓ Помощь":
            await self._help(update, context)
        elif text == "➕ Добавить пробежку":
            await message.reply_text(
                "Чтобы добавить пробежку, отправь мне сообщение в формате:\n\n"
                "#япобегал 5.2км\n\n"
                "Или просто напиши в групповом чате то же сообщение!"
            )
        # Если сообщение содержит #япобегал, парсим его
        elif text and '#япобегал' in text.lower():
            distance = self._parse_distance_from_text(text)
            if distance:
                self.db.add_user(user.id, user.first_name, user.last_name, user.username)
                self.db.add_run(user.id, distance)
                
                stats = self.db.get_user_stats(user.id)
                await message.reply_text(
                    f"✅ Пробежка записана!\n"
                    f"Дистанция: {distance} км\n"
                    f"Всего пробежек: {stats['total_runs']}\n"
                    f"Общая дистанция: {stats['total_distance']:.1f} км\n\n"
                    f"Так держать! 💪"
                )
            else:
                await message.reply_text(
                    "❌ Не удалось распознать дистанцию.\n"
                    "Правильный формат: #япобегал 5.2км\n"
                    "Или просто: #япобегал 10 км"
                )
        elif text and not text.startswith('/'):
            # Если обычное сообщение без команды
            await message.reply_text(
                "Привет! Используй кнопки ниже для навигации 👇\n\n"
                "Или отправь мне сообщение с пробежкой:\n"
                "#япобегал 5.2км"
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
                "1. Нажмите 'Добавить пробежку' в меню бота\n"
                "2. Или отправьте сообщение: #япобегал 5.2км\n"
                "3. Бот автоматически запишет пробежку\n"
                "4. Для статистики напишите боту в ЛС\n\n"
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
        # Настраиваем меню при запуске
        self.application.post_init = self._setup_menu_buttons
        
        self.scheduler.start()
        logger.info("Бот запущен...")
        logger.info("Планировщик запущен: понедельник 10:00 (неделя), 1 число 10:00 (месяц)")
        self.application.run_polling()
