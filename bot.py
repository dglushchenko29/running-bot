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

# ТВОЙ USER_ID
ADMIN_IDS = [862970986]

# Состояния для добавления пробежки админом
ADMIN_ADD_RUN = range(2)

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
        self.application.add_handler(CommandHandler("admin", self._admin))
        
        # Админ команды
        self.application.add_handler(CommandHandler("add_run", self._add_run_start))
        
        # ConversationHandler для админского добавления пробежек
        admin_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("add_run", self._add_run_start)],
            states={
                ADMIN_ADD_RUN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._add_run_finish)
                ],
            },
            fallbacks=[CommandHandler("cancel", self._add_run_cancel)],
        )
        self.application.add_handler(admin_conv_handler)
        
        # Обработчик callback кнопок
        self.application.add_handler(CallbackQueryHandler(self._button_handler))
        
        # Обработчик ВСЕХ сообщений в группах (текст, фото с подписью, и т.д.)
        self.application.add_handler(MessageHandler(
            filters.ChatType.GROUPS & (filters.TEXT | filters.CAPTION | filters.PHOTO),
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
        """Настройка кнопок меню бота - ТОЛЬКО для ЛС"""
        # Команды только для ЛС (пустой список для групп)
        private_commands = [
            BotCommand("start", "Регистрация и начало работы"),
            BotCommand("stats", "Моя статистика"),
            BotCommand("top_week", "Топ за неделю"),
            BotCommand("top_month", "Топ за месяц"),
            BotCommand("help", "Помощь")
        ]
        
        await application.bot.set_my_commands(private_commands)
        await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    
    def _is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором"""
        return user_id in ADMIN_IDS
    
    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start - ТОЛЬКО для ЛС"""
        user = update.effective_user
        chat = update.effective_chat
        
        # Работаем только в личных сообщениях
        if chat.type != "private":
            # В группе просто игнорируем команду /start
            return
        
        # ВАЖНО: Регистрируем пользователя, но не перезаписываем если уже есть
        self.db.add_user(user.id, user.first_name, user.last_name, user.username)
        
        # Для админа показываем админ-панель
        if self._is_admin(user.id):
            keyboard = [
                ["📊 Моя статистика", "🏆 Топ недели"],
                ["📈 Топ месяца", "❓ Помощь"],
                ["⚙️ Админ-панель"]
            ]
        else:
            keyboard = [
                ["📊 Моя статистика", "🏆 Топ недели"],
                ["📈 Топ месяца", "❓ Помощь"]
            ]
            
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"🏃 Привет, {user.first_name}!\n\n"
            "Я бот для учета пробежек в нашем чате! Вот что я умею:\n\n"
            "📱 В ЛИЧНЫХ СООБЩЕНИЯХ:\n"
            "• Смотри свою статистику\n"
            "• Смотри топы за неделю/месяц\n\n"
            "💬 В ГРУППОВОМ ЧАТЕ:\n"
            "• Просто отправь сообщение с #япобегал и дистанцией\n"
            "• Или фото с подписью: #япобегал 5.2км\n"
            "• Я автоматически запишу твою пробежку!\n\n"
            "📅 Автоматически:\n"
            "• Каждый понедельник в 10:00 - топ за неделю\n"
            "• 1-го числа каждого месяца - топ за месяц",
            reply_markup=reply_markup
        )
    
    async def _admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Админ-панель"""
        user = update.effective_user
        
        if not self._is_admin(user.id):
            await update.message.reply_text("❌ Эта команда только для администраторов")
            return
        
        # Используем Inline-кнопки для админ-панели
        keyboard = [
            [
                InlineKeyboardButton("📊 Статистика БД", callback_data="admin_db_stats"),
            ],
            [
                InlineKeyboardButton("👥 Все пользователи", callback_data="admin_all_users"),
                InlineKeyboardButton("🏃 Все пробежки", callback_data="admin_all_runs")
            ],
            [
                InlineKeyboardButton("➕ Добавить пробежку", callback_data="admin_add_run"),
                InlineKeyboardButton("🧹 Очистить БД", callback_data="admin_clear_db")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚙️ Админ-панель:\nВыберите действие:",
            reply_markup=reply_markup
        )
    
    async def _show_db_stats(self, query):
        """Показать статистику БД"""
        try:
            # Получаем базовую статистику
            users_result = self.db._execute_query('SELECT COUNT(*) as count FROM users')
            runs_result = self.db._execute_query('SELECT COUNT(*) as count FROM runs')
            distance_result = self.db._execute_query('SELECT COALESCE(SUM(distance), 0) as total FROM runs')
            
            users_count = users_result[0][0] if users_result else 0
            runs_count = runs_result[0][0] if runs_result else 0
            total_distance = float(distance_result[0][0]) if distance_result else 0
            
            # Статистика за неделю
            week_runs_result = self.db._execute_query('SELECT COUNT(*) as count FROM runs WHERE run_date >= CURRENT_TIMESTAMP - INTERVAL \'7 days\'')
            week_distance_result = self.db._execute_query('SELECT COALESCE(SUM(distance), 0) as total FROM runs WHERE run_date >= CURRENT_TIMESTAMP - INTERVAL \'7 days\'')
            
            week_runs_count = week_runs_result[0][0] if week_runs_result else 0
            week_total_distance = float(week_distance_result[0][0]) if week_distance_result else 0
            
            # Статистика за месяц
            month_runs_result = self.db._execute_query('SELECT COUNT(*) as count FROM runs WHERE run_date >= CURRENT_TIMESTAMP - INTERVAL \'30 days\'')
            month_distance_result = self.db._execute_query('SELECT COALESCE(SUM(distance), 0) as total FROM runs WHERE run_date >= CURRENT_TIMESTAMP - INTERVAL \'30 days\'')
            
            month_runs_count = month_runs_result[0][0] if month_runs_result else 0
            month_total_distance = float(month_distance_result[0][0]) if month_distance_result else 0
            
            stats_text = (
                f"📊 Статистика базы данных:\n\n"
                f"👥 Пользователей: {users_count}\n"
                f"🏃 Всего пробежек: {runs_count}\n"
                f"📏 Общая дистанция: {total_distance:.1f} км\n\n"
                f"📈 За НЕДЕЛЮ:\n"
                f"• Пробежек: {week_runs_count}\n"
                f"• Дистанция: {week_total_distance:.1f} км\n\n"
                f"📅 За МЕСЯЦ:\n"
                f"• Пробежек: {month_runs_count}\n"
                f"• Дистанция: {month_total_distance:.1f} км\n\n"
                f"🤖 Автоматические рассылки:\n"
                f"• Понедельник 10:00 - топ за неделю\n"
                f"• 1 число месяца 10:00 - топ за месяц"
            )
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(stats_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка показа статистики: {e}")
            await query.edit_message_text("❌ Ошибка загрузки статистики")
    
    async def _show_all_users(self, query):
        """Показать всех пользователей"""
        try:
            users_result = self.db._execute_query('SELECT user_id, first_name, username FROM users ORDER BY first_name ASC')
            
            if not users_result:
                text = "👥 Пользователей пока нет"
            else:
                text = f"👥 Все пользователи ({len(users_result)}):\n\n"
                for i, row in enumerate(users_result, 1):
                    if self.db.use_postgres:
                        user_id = row['user_id']
                        first_name = row['first_name']
                        username = row['username']
                    else:
                        user_id = row[0]
                        first_name = row[1]
                        username = row[2]
                    
                    name_display = f"@{username}" if username else first_name
                    text += f"{i}. {name_display} (ID: {user_id})\n"
                    
                    if len(text) > 3500:
                        text += f"\n... и еще {len(users_result) - i} пользователей"
                        break
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка показа пользователей: {e}")
            await query.edit_message_text("❌ Ошибка загрузки пользователей")
    
    async def _show_all_runs(self, query):
        """Показать все пробежки с ID для управления"""
        try:
            runs_result = self.db._execute_query('''
                SELECT r.run_id, u.first_name, u.username, r.distance, r.run_date 
                FROM runs r 
                JOIN users u ON r.user_id = u.user_id 
                ORDER BY r.run_date DESC 
                LIMIT 50
            ''')
            
            if not runs_result:
                text = "🏃 Пробежек пока нет"
            else:
                text = f"🏃 Последние {len(runs_result)} пробежек (ID для удаления):\n\n"
                for i, row in enumerate(runs_result, 1):
                    if self.db.use_postgres:
                        run_id = row['run_id']
                        first_name = row['first_name']
                        username = row['username']
                        distance = row['distance']
                        run_date = str(row['run_date'])[:16] if row['run_date'] else 'неизвестно'
                    else:
                        run_id = row[0]
                        first_name = row[1]
                        username = row[2]
                        distance = row[3]
                        run_date = str(row[4])[:16] if row[4] else 'неизвестно'
                    
                    name_display = f"@{username}" if username else first_name
                    text += f"{i}. ID:{run_id} | {name_display}: {distance} км ({run_date})\n"
                    
                    if len(text) > 3500:
                        text += f"\n... и еще {len(runs_result) - i} пробежек"
                        break
                
                text += f"\n\n🗑️ Удалить пробежку: /delete_run ID\nПример: /delete_run 123"
            
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")],
                [InlineKeyboardButton("🗑️ Удалить пробежку", callback_data="admin_delete_run")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка показа пробежек: {e}")
            await query.edit_message_text("❌ Ошибка загрузки пробежек")
    
    async def _add_run_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало добавления пробежки админом"""
        user = update.effective_user
        
        if not self._is_admin(user.id):
            await update.message.reply_text("❌ Эта команда только для администраторов")
            return ConversationHandler.END
        
        await update.message.reply_text(
            "➕ Добавление пробежки:\n\n"
            "Введите данные в формате:\n"
            "user_id дистанция\n\n"
            "Пример:\n"
            "123456789 5.2\n\n"
            "Или /cancel для отмены"
        )
        
        return ADMIN_ADD_RUN
    
    async def _add_run_finish(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Завершение добавления пробежки админом"""
        try:
            text = update.message.text.strip()
            parts = text.split()
            
            if len(parts) != 2:
                await update.message.reply_text("❌ Неверный формат. Нужно: user_id дистанция\nПример: 123456789 5.2")
                return ADMIN_ADD_RUN
            
            user_id = int(parts[0])
            distance = float(parts[1])
            
            # Получаем информацию о пользователе
            user_result = self.db._execute_query('SELECT first_name, username FROM users WHERE user_id = ?', (user_id,))
            
            if not user_result:
                await update.message.reply_text(f"❌ Пользователь с ID {user_id} не найден")
                return ADMIN_ADD_RUN
            
            if self.db.use_postgres:
                first_name = user_result[0]['first_name']
                username = user_result[0]['username']
            else:
                first_name = user_result[0][0]
                username = user_result[0][1]
            
            # Добавляем пробежку
            self.db.add_run(user_id, distance)
            
            name_display = f"@{username}" if username else first_name
            await update.message.reply_text(f"✅ Пробежка добавлена!\n{name_display}: {distance} км")
            
            return ConversationHandler.END
            
        except ValueError:
            await update.message.reply_text("❌ Ошибка в данных. user_id должно быть числом, дистанция - числом")
            return ADMIN_ADD_RUN
        except Exception as e:
            logger.error(f"Ошибка добавления пробежки админом: {e}")
            await update.message.reply_text("❌ Произошла ошибка при добавлении пробежки")
            return ConversationHandler.END
    
    async def _add_run_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена добавления пробежки"""
        await update.message.reply_text("❌ Добавление пробежки отменено")
        return ConversationHandler.END
    
    async def _button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        
        if not self._is_admin(user.id):
            await query.edit_message_text("❌ Нет прав для выполнения этой операции")
            return
        
        try:
            if data == "admin_db_stats":
                await self._show_db_stats(query)
            elif data == "admin_all_users":
                await self._show_all_users(query)
            elif data == "admin_all_runs":
                await self._show_all_runs(query)
            elif data == "admin_add_run":
                await query.edit_message_text(
                    "➕ Добавить пробежку:\n\n"
                    "Используйте команду:\n"
                    "/add_run\n\n"
                    "Затем введите:\n"
                    "user_id дистанция\n\n"
                    "Пример:\n"
                    "123456789 5.2"
                )
            elif data == "admin_delete_run":
                await query.edit_message_text(
                    "🗑️ Удалить пробежку:\n\n"
                    "Используйте команду:\n"
                    "/delete_run ID\n\n"
                    "Пример:\n"
                    "/delete_run 123\n\n"
                    "ID пробежки можно посмотреть в разделе 'Все пробежки'"
                )
            elif data == "admin_clear_db":
                # Создаем клавиатуру подтверждения для очистки
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Да, очистить", callback_data="confirm_clear"),
                        InlineKeyboardButton("❌ Отмена", callback_data="admin_back")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "⚠️ ВНИМАНИЕ!\n\n"
                    "Вы собираетесь полностью очистить базу данных.\n"
                    "Это удалит:\n"
                    "• Всех пользователей\n"
                    "• Все пробежки\n"
                    "• Статистику\n\n"
                    "Вы уверены?",
                    reply_markup=reply_markup
                )
            elif data == "confirm_clear":
                # Очищаем базу
                self.db._init_db()
                await query.edit_message_text("✅ База данных очищена!")
            elif data == "admin_back":
                # Возвращаемся в админ-панель
                keyboard = [
                    [
                        InlineKeyboardButton("📊 Статистика БД", callback_data="admin_db_stats"),
                    ],
                    [
                        InlineKeyboardButton("👥 Все пользователи", callback_data="admin_all_users"),
                        InlineKeyboardButton("🏃 Все пробежки", callback_data="admin_all_runs")
                    ],
                    [
                        InlineKeyboardButton("➕ Добавить пробежку", callback_data="admin_add_run"),
                        InlineKeyboardButton("🧹 Очистить БД", callback_data="admin_clear_db")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "⚙️ Админ-панель:\nВыберите действие:",
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Ошибка в обработчике кнопок: {e}")
            await query.edit_message_text("❌ Произошла ошибка при обработке запроса")
    
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
                "Добавь первую пробежку:\n"
                "• В группе: #япобегал 5.2км\n"
                "• Или в ЛС мне то же сообщение!"
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
            "• Отправь сообщение: #япобегал 5.2км\n"
            "• Или фото с подписью: #япобегал 5.2км\n\n"
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
        """Обработчик ВСЕХ сообщений в группах - парсинг #япобегал из текста и подписей"""
        message = update.message
        user = message.from_user
        
        # Получаем текст из сообщения или подписи к медиа
        text = ""
        if message.text:
            text = message.text
        elif message.caption:
            text = message.caption
        else:
            return  # Нет текста для парсинга
        
        if not text or '#япобегал' not in text.lower():
            return
        
        # Парсим дистанцию из текста
        distance = self._parse_distance_from_text(text)
        
        if distance:
            # ВАЖНО: Автоматически регистрируем пользователя при первой пробежке
            # НЕ нужно писать /start в ЛС!
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
                         f"Так держать! 💪\n\n"
                         f"Для просмотра статистики используй команду /stats"
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
        elif text == "⚙️ Админ-панель" and self._is_admin(user.id):
            await self._admin(update, context)
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
                "• Отправьте сообщение: #япобегал 5.2км\n"
                "• Или фото с подписью: #япобегал 5.2км\n"
                "• Бот автоматически запишет пробежку\n"
                "• Для статистики напишите боту в ЛС\n\n"
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
            text += f"{i}. {username} - {runner['total_distance']:.1f} км\n"
        
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
            text += f"{i}. {username} - {runner['total_distance']:.1f} км\n"
        
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
