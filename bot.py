import os
import logging
from datetime import datetime
from typing import Optional

from telegram import (
    Update, 
    InlineKeyboardMarkup,
    InlineKeyboardButton
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

from database import Database

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
DISTANCE, CONFIRMATION = range(2)

class RunningBot:
    def __init__(self, token: str, db: Database):
        self.token = token
        self.db = db
        self.application = Application.builder().token(token).build()
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        # Обработчики для личных сообщений (группа 1 - высокий приоритет)
        self.application.add_handler(CommandHandler("start", self._start_private), group=1)
        self.application.add_handler(CommandHandler("stats", self._show_stats), group=1)
        self.application.add_handler(CommandHandler("help", self._help), group=1)
        
        # ConversationHandler для добавления пробежки (только в ЛС)
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("add", self._add_run_start),
                MessageHandler(filters.TEXT & filters.Regex(r'#япобегал'), self._add_run_start)
            ],
            states={
                DISTANCE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_distance)
                ],
                CONFIRMATION: [
                    CallbackQueryHandler(self._confirm_run, pattern=r'^confirm_'),
                    CallbackQueryHandler(self._cancel_run, pattern=r'^cancel_')
                ]
            },
            fallbacks=[CommandHandler("cancel", self._cancel_conversation)],
        )
        self.application.add_handler(conv_handler, group=1)
        
        # Обработчик для кнопки в группе (группа 2 - низкий приоритет)
        self.application.add_handler(CallbackQueryHandler(self._group_button_handler, pattern=r'^add_run$'), group=2)
        
        # Обработчик для любых сообщений в группах
        self.application.add_handler(MessageHandler(filters.ChatType.GROUPS, self._group_message_handler), group=2)
    
    async def _start_private(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start в личных сообщениях"""
        user = update.effective_user
        chat = update.effective_chat
        
        # Работаем только в личных сообщениях
        if chat.type != "private":
            await update.message.reply_text(
                "Пожалуйста, напишите мне в личные сообщения для регистрации и управления пробежками!"
            )
            return
        
        if not self.db.user_exists(user.id):
            self.db.add_user(user.id, user.first_name, user.last_name, user.username)
            await update.message.reply_text(
                f"🏃 Добро пожаловать, {user.first_name}!\n\n"
                "Вы успешно зарегистрированы в беговом боте!\n\n"
                "Доступные команды:\n"
                "/add - Добавить пробежку\n"
                "/stats - Посмотреть статистику\n"
                "/help - Помощь\n\n"
                "Или просто отправьте сообщение с хештегом #япобегал и дистанцией!"
            )
        else:
            await update.message.reply_text(
                f"С возвращением, {user.first_name}!\n\n"
                "Доступные команды:\n"
                "/add - Добавить пробежку\n" 
                "/stats - Посмотреть статистику\n"
                "/help - Помощь\n\n"
                "Или просто отправьте сообщение с хештегом #япобегал и дистанцией!"
            )
    
    async def _add_run_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало добавления пробежки"""
        user = update.effective_user
        chat = update.effective_chat
        
        # Работаем только в личных сообщениях
        if chat.type != "private":
            await update.message.reply_text(
                "Пожалуйста, перейдите в личные сообщения с ботом чтобы добавить пробежку!"
            )
            return ConversationHandler.END
        
        if not self.db.user_exists(user.id):
            await update.message.reply_text(
                "Пожалуйста, сначала зарегистрируйтесь с помощью команды /start"
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            "🏃 Введите дистанцию вашей пробежки:\n\n"
            "Примеры:\n"
            "• 5 км\n"
            "• 10.5 км\n" 
            "• 7.2 км\n\n"
            "Или отправьте /cancel для отмены"
        )
        
        return DISTANCE
    
    async def _receive_distance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка введенной дистанции"""
        text = update.message.text
        user = update.effective_user
        
        # Парсим дистанцию
        try:
            distance = self._parse_distance(text)
            if distance <= 0:
                raise ValueError("Дистанция должна быть положительной")
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Неверный формат дистанции. Пожалуйста, введите дистанцию в формате:\n"
                "• 5 км\n"
                "• 10.5 км\n"
                "• 7.2 км\n\n"
                "Или отправьте /cancel для отмены"
            )
            return DISTANCE
        
        # Сохраняем дистанцию в контексте
        context.user_data['distance'] = distance
        
        # Создаем клавиатуру для подтверждения
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{distance}"),
                InlineKeyboardButton("❌ Отменить", callback_data="cancel_run")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📝 Подтвердите добавление пробежки:\n"
            f"Дистанция: {distance} км\n\n"
            "Бот автоматически добавит хештег #modern",
            reply_markup=reply_markup
        )
        
        return CONFIRMATION
    
    async def _confirm_run(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение добавления пробежки"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        distance = context.user_data.get('distance', 0)
        
        # Добавляем пробежку в базу
        self.db.add_run(user.id, distance)
        
        # Получаем общую статистику
        total_runs = self.db.get_user_stats(user.id)['total_runs']
        total_distance = self.db.get_user_stats(user.id)['total_distance']
        
        await query.edit_message_text(
            f"✅ Пробежка добавлена!\n"
            f"Дистанция: {distance} км\n"
            f"Всего пробежек: {total_runs}\n"
            f"Общая дистанция: {total_distance:.1f} км\n\n"
            f"Теперь вы можете поделиться этим в чате: #япобегал {distance}км"
        )
        
        # Очищаем данные
        context.user_data.clear()
        return ConversationHandler.END
    
    async def _cancel_run(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена добавления пробежки"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "❌ Добавление пробежки отменено"
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def _cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена диалога"""
        await update.message.reply_text(
            "Добавление пробежки отменено"
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def _show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику пользователя"""
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type != "private":
            await update.message.reply_text(
                "Пожалуйста, перейдите в личные сообщения с ботом чтобы посмотреть статистику!"
            )
            return
        
        if not self.db.user_exists(user.id):
            await update.message.reply_text(
                "Пожалуйста, сначала зарегистрируйтесь с помощью команды /start"
            )
            return
        
        stats = self.db.get_user_stats(user.id)
        
        if stats['total_runs'] == 0:
            await update.message.reply_text(
                "📊 У вас пока нет пробежек.\n"
                "Добавьте первую пробежку с помощью команды /add"
            )
        else:
            await update.message.reply_text(
                f"📊 Ваша статистика:\n\n"
                f"Всего пробежек: {stats['total_runs']}\n"
                f"Общая дистанция: {stats['total_distance']:.1f} км\n"
                f"Средняя дистанция: {stats['average_distance']:.1f} км\n"
                f"Последняя пробежка: {stats['last_run_distance']} км"
            )
    
    async def _help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        chat = update.effective_chat
        
        if chat.type != "private":
            await update.message.reply_text(
                "ℹ️ Этот бот помогает отслеживать пробежки.\n\n"
                "Для использования перейдите в личные сообщения с ботом!"
            )
            return
        
        await update.message.reply_text(
            "🏃 Помощь по беговому боту:\n\n"
            "Доступные команды:\n"
            "/start - Регистрация и начало работы\n"
            "/add - Добавить пробежку\n"
            "/stats - Посмотреть статистику\n"
            "/help - Эта справка\n\n"
            "Быстрое добавление:\n"
            "Отправьте сообщение с хештегом #япобегал и дистанцией\n"
            "Пример: #япобегал 5.2км\n\n"
            "В групповых чатах используйте кнопку 'Добавить пробежку' "
            "для быстрого перехода к боту в ЛС"
        )
    
    async def _group_button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопки в группе"""
        query = update.callback_query
        user = query.from_user
        
        # Всегда показываем сообщение о переходе в ЛС
        await query.answer(
            "Перейдите в личные сообщения с ботом чтобы добавить пробежку!", 
            show_alert=True
        )
    
    async def _group_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик сообщений в группах"""
        # Игнорируем сообщения в группах, если они не команды
        if update.message.text and not update.message.text.startswith('/'):
            return
        
        # Для команд в группах показываем сообщение о переходе в ЛС
        if update.message.text and update.message.text.startswith('/'):
            await update.message.reply_text(
                "ℹ️ Для работы с ботом перейдите в личные сообщения!"
            )
    
    def _parse_distance(self, text: str) -> float:
        """Парсит дистанцию из текста"""
        # Убираем лишние пробелы и приводим к нижнему регистру
        text = text.lower().strip()
        
        # Убираем "км", "km" и другие варианты
        text = text.replace('км', '').replace('km', '').strip()
        
        # Заменяем запятые на точки
        text = text.replace(',', '.')
        
        # Парсим число
        return float(text)
    
    def run(self):
        """Запуск бота"""
        logger.info("Бот запущен...")
        self.application.run_polling()
