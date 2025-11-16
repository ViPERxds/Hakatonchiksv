
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import aiohttp
import io
import json
from datetime import datetime


class TelegramBot:
    """Telegram бот для обработки счетов"""
    
    def __init__(self, token: str, api_url: str = "http://localhost:8000"):
        self.token = token
        self.api_url = api_url
        self.application = None
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        welcome_message = f"""
👋 Добро пожаловать, {user.first_name}!

Я помогу вам обрабатывать счета из PDF-файлов и фото.

📋 Основные возможности:
• Извлечение данных из PDF-счетов
• Обработка фото счетов с помощью OCR
• История обработанных счетов
• Статистика и аналитика
• Экспорт в Excel

📸 Просто отправьте PDF-файл или фото счета!

Используйте кнопки ниже для быстрого доступа к функциям.
"""
        # Создаем клавиатуру с основными командами
        keyboard = [
            [KeyboardButton("📄 Отправить PDF"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("📜 История"), KeyboardButton("📥 Экспорт в Excel")],
            [KeyboardButton("ℹ️ Помощь")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
📖 Справка по использованию бота:

📄 **Обработка счетов:**
1. Отправьте PDF-файл счета ИЛИ фото счета
2. Бот автоматически извлечет данные:
   • Номер счета
   • Дата
   • Продавец и покупатель
   • ИНН, КПП
   • Список товаров/услуг
   • Общая сумма
   • НДС
   • Валюта

📸 **Поддерживаемые форматы:**
• PDF файлы (скачанные и отсканированные)
• Фото счетов (JPG, PNG)
• Отсканированные документы

💡 **Советы для фото:**
• Сделайте четкое, хорошо освещенное фото
• Убедитесь, что весь текст виден
• Избегайте теней и бликов

📜 **История:**
• /history - просмотр последних счетов
• /history 20 - последние 20 счетов

📊 **Статистика:**
• /stats - статистика за 30 дней
• /stats 7 - статистика за 7 дней

📥 **Экспорт:**
• /export - экспорт всех счетов в Excel
• /export_stats - экспорт статистики в Excel

⚙️ **Настройки:**
• /settings - настройки уведомлений
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка PDF файлов"""
        document = update.message.document
        if not document.file_name.endswith('.pdf'):
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте файл в формате PDF"
            )
            return
        
        processing_msg = await update.message.reply_text(
            "⏳ Обрабатываю документ, пожалуйста, подождите..."
        )
        
        try:
            file = await context.bot.get_file(document.file_id)
            file_content = await file.download_as_bytearray()
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field(
                    'file',
                    io.BytesIO(file_content),
                    filename=document.file_name,
                    content_type='application/pdf'
                )
                
                user_id = update.effective_user.id
                user_name = update.effective_user.full_name
                
                data.add_field('user_id', str(user_id))
                data.add_field('user_name', user_name)
                
                async with session.post(
                    f"{self.api_url}/process-invoice",
                    data=data
                ) as response:
                    status = response.status
                    
                    if 200 <= status < 300:
                        result = await response.json()
                    elif 400 <= status < 500:
                        error_messages = {
                            400: "Некорректный запрос. Пожалуйста, убедитесь, что файл в формате PDF.",
                            401: "Ошибка авторизации.",
                            403: "Доступ запрещен.",
                            404: "Ресурс не найден.",
                            413: "Файл слишком большой.",
                            415: "Неподдерживаемый тип файла. Требуется PDF.",
                        }
                        error_text = error_messages.get(status, f"Ошибка клиента (код {status})")
                        await processing_msg.edit_text(f"❌ {error_text}")
                        return
                    elif 500 <= status < 600:
                        # Ошибка сервера (5xx)
                        await processing_msg.edit_text("❌ Внутренняя ошибка сервера. Попробуйте позже.")
                        return
                    else:
                        result = await response.json()
            
            # Отправляем результат для успешных ответов
            if result.get('success'):
                data = result.get('data', {})
                
                # Форматируем JSON для читаемости
                formatted_json = json.dumps(data, ensure_ascii=False, indent=2)
                
                # Создаем inline-кнопки для быстрых действий
                keyboard = [
                    [
                        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
                        InlineKeyboardButton("📜 История", callback_data="history")
                    ],
                    [
                        InlineKeyboardButton("📥 Экспорт в Excel", callback_data="export"),
                        InlineKeyboardButton("💾 Скачать JSON", callback_data="download_json")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                invoice_info = f"""✅ **Счет обработан!**

📄 Номер: {data.get('invoice_number', 'N/A')}
📅 Дата: {data.get('date', 'N/A')}
🏢 Продавец: {data.get('seller', 'N/A')[:50]}
💰 Сумма: {data.get('total_amount', 'N/A')} {data.get('currency', 'RUB')}
"""
                
                # Отправляем краткую информацию с кнопками
                await processing_msg.edit_text(
                    invoice_info,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                
                json_bytes = formatted_json.encode('utf-8')
                invoice_number = data.get('invoice_number', 'invoice')
                filename = f"invoice_{invoice_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
                download_keyboard = [[InlineKeyboardButton("💾 Скачать JSON файл", callback_data="download_current_json")]]
                download_markup = InlineKeyboardMarkup(download_keyboard)
                
                if len(formatted_json) < 4000:
                    await update.message.reply_text(
                        f"📋 **Полные данные:**\n\n```json\n{formatted_json}\n```",
                        parse_mode='Markdown',
                        reply_markup=download_markup
                    )
                else:
                    await update.message.reply_document(
                        document=io.BytesIO(json_bytes),
                        filename=filename,
                        caption="📋 Полные данные в формате JSON (файл слишком большой для отображения)",
                        reply_markup=download_markup
                    )
                
                context.user_data['last_json'] = {
                    'data': json_bytes,
                    'filename': filename
                }
            else:
                await processing_msg.edit_text(
                    f"❌ Ошибка обработки: {result.get('message', 'Неизвестная ошибка')}"
                )
        
        except Exception as e:
            await processing_msg.edit_text(
                f"❌ Произошла ошибка при обработке файла: {str(e)}"
            )
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка фото счетов через OCR"""
        photo = update.message.photo[-1]
        
        processing_msg = await update.message.reply_text(
            "⏳ Обрабатываю фото с помощью OCR, пожалуйста, подождите..."
        )
        
        try:
            file = await context.bot.get_file(photo.file_id)
            file_content = await file.download_as_bytearray()
            file_extension = '.jpg'
            if hasattr(photo, 'file_name') and photo.file_name:
                file_ext = os.path.splitext(photo.file_name.lower())[1]
                if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
                    file_extension = file_ext
            else:
                if hasattr(file, 'file_path') and file.file_path:
                    if '.png' in file.file_path.lower():
                        file_extension = '.png'
            
            filename = f"photo_{update.message.message_id}{file_extension}"
            
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field(
                    'file',
                    io.BytesIO(file_content),
                    filename=filename,
                    content_type='image/jpeg'
                )
                
                user_id = update.effective_user.id
                user_name = update.effective_user.full_name
                
                data.add_field('user_id', str(user_id))
                data.add_field('user_name', user_name)
                
                async with session.post(
                    f"{self.api_url}/process-image",
                    data=data
                ) as response:
                    status = response.status
                    
                    if 200 <= status < 300:
                        result = await response.json()
                    elif 400 <= status < 500:
                        error_messages = {
                            400: "Некорректный запрос. Убедитесь, что фото четкое и содержит текст.",
                            401: "Ошибка авторизации.",
                            403: "Доступ запрещен.",
                            404: "Ресурс не найден.",
                            413: "Файл слишком большой.",
                            415: "Неподдерживаемый тип файла. Поддерживаются: JPG, PNG, BMP, TIFF.",
                        }
                        error_text = error_messages.get(status, f"Ошибка клиента (код {status})")
                        await processing_msg.edit_text(f"❌ {error_text}")
                        return
                    elif 500 <= status < 600:
                        # Ошибка сервера (5xx)
                        await processing_msg.edit_text("❌ Внутренняя ошибка сервера. Попробуйте позже.")
                        return
                    else:
                        result = await response.json()
            
            # Отправляем результат для успешных ответов
            if result.get('success'):
                data = result.get('data', {})
                
                # Форматируем JSON для читаемости
                formatted_json = json.dumps(data, ensure_ascii=False, indent=2)
                
                # Создаем inline-кнопки для быстрых действий
                keyboard = [
                    [
                        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
                        InlineKeyboardButton("📜 История", callback_data="history")
                    ],
                    [
                        InlineKeyboardButton("📥 Экспорт в Excel", callback_data="export"),
                        InlineKeyboardButton("💾 Скачать JSON", callback_data="download_json")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                invoice_info = f"""✅ **Счет обработан из фото!**

📄 Номер: {data.get('invoice_number', 'N/A')}
📅 Дата: {data.get('date', 'N/A')}
🏢 Продавец: {data.get('seller', 'N/A')[:50]}
💰 Сумма: {data.get('total_amount', 'N/A')} {data.get('currency', 'RUB')}
"""
                
                # Отправляем краткую информацию с кнопками
                await processing_msg.edit_text(
                    invoice_info,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                
                json_bytes = formatted_json.encode('utf-8')
                invoice_number = data.get('invoice_number', 'invoice')
                json_filename = f"invoice_{invoice_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
                download_keyboard = [[InlineKeyboardButton("💾 Скачать JSON файл", callback_data="download_current_json")]]
                download_markup = InlineKeyboardMarkup(download_keyboard)
                
                if len(formatted_json) < 4000:
                    await update.message.reply_text(
                        f"📋 **Полные данные:**\n\n```json\n{formatted_json}\n```",
                        parse_mode='Markdown',
                        reply_markup=download_markup
                    )
                else:
                    await update.message.reply_document(
                        document=io.BytesIO(json_bytes),
                        filename=json_filename,
                        caption="📋 Полные данные в формате JSON (файл слишком большой для отображения)",
                        reply_markup=download_markup
                    )
                
                context.user_data['last_json'] = {
                    'data': json_bytes,
                    'filename': json_filename
                }
            else:
                await processing_msg.edit_text(
                    f"❌ Ошибка обработки: {result.get('message', 'Неизвестная ошибка')}\n\n"
                    "💡 Совет: Убедитесь, что фото четкое, хорошо освещено и содержит читаемый текст."
                )
        
        except Exception as e:
            await processing_msg.edit_text(
                f"❌ Произошла ошибка при обработке фото: {str(e)}\n\n"
                "💡 Попробуйте:\n"
                "• Сделать более четкое фото\n"
                "• Убедиться, что документ хорошо освещен\n"
                "• Убедиться, что текст читаемый"
            )
    
    async def history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /history"""
        user_id = update.effective_user.id
        limit = 10
        if context.args and len(context.args) > 0:
            try:
                limit = int(context.args[0])
                limit = min(limit, 50)
            except:
                pass
        
        msg = await update.message.reply_text("⏳ Загружаю историю...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/history/{user_id}",
                    params={"limit": limit}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        invoices = result.get('data', [])
                        
                        if not invoices:
                            await msg.edit_text("📭 История пуста. Обработайте первый счет!")
                            return
                        
                        text = f"📜 **Последние {len(invoices)} счетов:**\n\n"
                        for idx, inv in enumerate(invoices, 1):
                            text += f"{idx}. №{inv.get('invoice_number', 'N/A')} | "
                            text += f"{inv.get('date', 'N/A')} | "
                            text += f"{inv.get('total_amount', 'N/A')} {inv.get('currency', 'RUB')}\n"
                            text += f"   🏢 {inv.get('seller', 'N/A')[:40]}\n\n"
                        
                        keyboard = [[InlineKeyboardButton("📥 Экспорт в Excel", callback_data="export")]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await msg.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
                    else:
                        await msg.edit_text("❌ Ошибка при загрузке истории")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {str(e)}")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats"""
        user_id = update.effective_user.id
        days = 30
        if context.args and len(context.args) > 0:
            try:
                days = int(context.args[0])
                days = min(days, 365)
            except:
                pass
        
        msg = await update.message.reply_text("⏳ Рассчитываю статистику...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/stats/{user_id}",
                    params={"days": days}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        stats = result.get('data', {})
                        
                        text = f"📊 **Статистика за {days} дней:**\n\n"
                        text += f"📄 Всего счетов: {stats.get('total_invoices', 0)}\n"
                        text += f"💰 Общая сумма: {stats.get('total_amount', 0):,.2f} руб.\n\n"
                        
                        top_sellers = stats.get('top_sellers', [])
                        if top_sellers:
                            text += "🏆 **Топ поставщиков:**\n"
                            for idx, seller in enumerate(top_sellers[:5], 1):
                                text += f"{idx}. {seller.get('name', 'N/A')[:30]} - {seller.get('count', 0)} счетов\n"
                        
                        keyboard = [
                            [InlineKeyboardButton("📥 Экспорт статистики", callback_data="export_stats")],
                            [InlineKeyboardButton("📜 История", callback_data="history")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await msg.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
                    else:
                        await msg.edit_text("❌ Ошибка при загрузке статистики")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {str(e)}")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /export"""
        user_id = update.effective_user.id
        export_type = context.args[0] if context.args else "invoices"
        
        msg = await update.message.reply_text("⏳ Формирую Excel файл...")
        
        try:
            async with aiohttp.ClientSession() as session:
                if export_type == "stats":
                    url = f"{self.api_url}/export/stats/{user_id}"
                    filename = f"stats_{user_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
                else:
                    url = f"{self.api_url}/export/excel/{user_id}"
                    filename = f"invoices_{user_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
                
                async with session.get(url) as response:
                    if response.status == 200:
                        file_data = await response.read()
                        await msg.edit_text("✅ Файл готов!")
                        await update.message.reply_document(
                            document=io.BytesIO(file_data),
                            filename=filename
                        )
                    else:
                        await msg.edit_text("❌ Ошибка при экспорте")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {str(e)}")
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /settings"""
        user_id = update.effective_user.id
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/settings/{user_id}") as response:
                    if response.status == 200:
                        result = await response.json()
                        settings = result.get('data', {})
                        notifications_status = "Включены" if settings.get('notifications_enabled', 1) else "Выключены"
                        notification_time = settings.get('notification_time', '09:00')
                    else:
                        notifications_status = "Включены"
                        notification_time = "09:00"
        except:
            notifications_status = "Включены"
            notification_time = "09:00"
        
        text = f"""
⚙️ **Настройки:**

🔔 Уведомления: {notifications_status}
⏰ Время уведомлений: {notification_time}

Используйте кнопки ниже для изменения настроек.
"""
        keyboard = [
            [
                InlineKeyboardButton("🔔 Вкл/Выкл уведомления", callback_data="toggle_notifications"),
                InlineKeyboardButton("⏰ Изменить время", callback_data="change_time")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на inline-кнопки"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        if data == "stats":
            await self._show_stats_inline(query, user_id)
        elif data == "history":
            await self._show_history_inline(query, user_id)
        elif data == "export":
            await self._export_inline(query, user_id, "invoices")
        elif data == "export_stats":
            await self._export_inline(query, user_id, "stats")
        elif data == "download_json":
            await self._download_json_inline(query, user_id)
        elif data == "download_current_json":
            await self._download_current_json_inline(query, context)
        elif data == "toggle_notifications":
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.api_url}/settings/notifications/{user_id}/toggle"
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            enabled = result.get('enabled', False)
                            status = "включены" if enabled else "выключены"
                            await query.edit_message_text(f"🔔 Уведомления {status}!")
                        else:
                            await query.edit_message_text("❌ Ошибка при изменении настроек")
            except:
                await query.edit_message_text("🔔 Настройки уведомлений будут доступны в следующей версии.")
        elif data == "change_time":
            await query.edit_message_text("⏰ Настройка времени уведомлений будет доступна в следующей версии.")
    
    async def _show_stats_inline(self, query, user_id: int, days: int = 30):
        await query.edit_message_text("⏳ Рассчитываю статистику...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/stats/{user_id}",
                    params={"days": days}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        stats = result.get('data', {})
                        
                        text = f"📊 **Статистика за {days} дней:**\n\n"
                        text += f"📄 Всего счетов: {stats.get('total_invoices', 0)}\n"
                        text += f"💰 Общая сумма: {stats.get('total_amount', 0):,.2f} руб.\n\n"
                        
                        top_sellers = stats.get('top_sellers', [])
                        if top_sellers:
                            text += "🏆 **Топ поставщиков:**\n"
                            for idx, seller in enumerate(top_sellers[:5], 1):
                                text += f"{idx}. {seller.get('name', 'N/A')[:30]} - {seller.get('count', 0)} счетов\n"
                        
                        keyboard = [
                            [InlineKeyboardButton("📥 Экспорт статистики", callback_data="export_stats")],
                            [InlineKeyboardButton("📜 История", callback_data="history")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
                    else:
                        await query.edit_message_text("❌ Ошибка при загрузке статистики")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")
    
    async def _show_history_inline(self, query, user_id: int, limit: int = 10):
        await query.edit_message_text("⏳ Загружаю историю...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/history/{user_id}",
                    params={"limit": limit}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        invoices = result.get('data', [])
                        
                        if not invoices:
                            await query.edit_message_text("📭 История пуста. Обработайте первый счет!")
                            return
                        
                        text = f"📜 **Последние {len(invoices)} счетов:**\n\n"
                        for idx, inv in enumerate(invoices, 1):
                            text += f"{idx}. №{inv.get('invoice_number', 'N/A')} | "
                            text += f"{inv.get('date', 'N/A')} | "
                            text += f"{inv.get('total_amount', 'N/A')} {inv.get('currency', 'RUB')}\n"
                            text += f"   🏢 {inv.get('seller', 'N/A')[:40]}\n\n"
                        
                        keyboard = [[InlineKeyboardButton("📥 Экспорт в Excel", callback_data="export")]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
                    else:
                        await query.edit_message_text("❌ Ошибка при загрузке истории")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")
    
    async def _export_inline(self, query, user_id: int, export_type: str):
        await query.edit_message_text("⏳ Формирую Excel файл...")
        try:
            async with aiohttp.ClientSession() as session:
                if export_type == "stats":
                    url = f"{self.api_url}/export/stats/{user_id}"
                    filename = f"stats_{user_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
                else:
                    url = f"{self.api_url}/export/excel/{user_id}"
                    filename = f"invoices_{user_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
                
                async with session.get(url) as response:
                    if response.status == 200:
                        file_data = await response.read()
                        await query.edit_message_text("✅ Файл готов!")
                        await query.message.reply_document(
                            document=io.BytesIO(file_data),
                            filename=filename
                        )
                    else:
                        await query.edit_message_text("❌ Ошибка при экспорте")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")
    
    async def _download_json_inline(self, query, user_id: int):
        await query.edit_message_text("⏳ Загружаю последний счет...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/history/{user_id}",
                    params={"limit": 1}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        invoices = result.get('data', [])
                        
                        if not invoices:
                            await query.edit_message_text("📭 Нет обработанных счетов. Сначала обработайте PDF-файл.")
                            return
                        
                        invoice_id = invoices[0].get('id')
                        
                        if invoice_id:
                            await query.edit_message_text("⏳ Формирую JSON файл...")
                            async with session.get(
                                f"{self.api_url}/invoice/{invoice_id}/json"
                            ) as json_response:
                                if json_response.status == 200:
                                    json_result = await json_response.json()
                                    invoice_data = json_result.get('data', {})
                                    
                                    formatted_json = json.dumps(invoice_data, ensure_ascii=False, indent=2)
                                    json_bytes = formatted_json.encode('utf-8')
                                    invoice_number = invoice_data.get('invoice_number', 'unknown')
                                    filename = f"invoice_{invoice_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                                    
                                    await query.edit_message_text("✅ JSON файл готов!")
                                    await query.message.reply_document(
                                        document=io.BytesIO(json_bytes),
                                        filename=filename,
                                        caption="📋 Данные счета в формате JSON"
                                    )
                                else:
                                    await self._download_json_fallback(query, invoices[0])
                        else:
                            await self._download_json_fallback(query, invoices[0])
                    else:
                        await query.edit_message_text("❌ Ошибка при загрузке данных")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")
    
    async def _download_json_fallback(self, query, invoice_data: dict):
        await query.edit_message_text("⏳ Формирую JSON файл...")
        json_data = {
            "invoice_number": invoice_data.get('invoice_number'),
            "date": invoice_data.get('date'),
            "seller": invoice_data.get('seller'),
            "total_amount": invoice_data.get('total_amount'),
            "currency": invoice_data.get('currency', 'RUB'),
            "created_at": invoice_data.get('created_at')
        }
        
        formatted_json = json.dumps(json_data, ensure_ascii=False, indent=2)
        json_bytes = formatted_json.encode('utf-8')
        filename = f"invoice_{invoice_data.get('invoice_number', 'unknown')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        await query.edit_message_text("✅ JSON файл готов!")
        await query.message.reply_document(
            document=io.BytesIO(json_bytes),
            filename=filename,
            caption="📋 Данные счета в формате JSON"
        )
    
    async def _download_current_json_inline(self, query, context: ContextTypes.DEFAULT_TYPE):
        try:
            last_json = context.user_data.get('last_json')
            if last_json:
                await query.answer("📥 Отправляю JSON файл...")
                await query.message.reply_document(
                    document=io.BytesIO(last_json['data']),
                    filename=last_json['filename'],
                    caption="📋 Данные счета в формате JSON"
                )
            else:
                await query.answer("❌ JSON не найден. Обработайте счет заново.", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        text = update.message.text
        
        if text == "📄 Отправить PDF":
            await update.message.reply_text(
                "📄 Пожалуйста, отправьте PDF-файл или фото со счетом для обработки.\n\n"
                "Вы можете отправить:\n"
                "• PDF-файл (скачанный или отсканированный)\n"
                "• Фото счета (JPG, PNG)\n\n"
                "Просто отправьте файл или фото прямо в этот чат!"
            )
        elif text == "📊 Статистика":
            await self.stats_command(update, context)
        elif text == "📜 История":
            await self.history_command(update, context)
        elif text == "📥 Экспорт в Excel":
            context.args = []
            await self.export_command(update, context)
        elif text == "ℹ️ Помощь":
            await self.help_command(update, context)
        else:
            await update.message.reply_text(
                "Отправьте PDF-файл или фото со счетом для обработки или используйте команды из меню.\n\n"
                "Или нажмите кнопку '📄 Отправить PDF' для подсказки."
            )
    
    def run(self):
        """Запуск бота"""
        self.application = Application.builder().token(self.token).build()
        
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("history", self.history_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("export", self.export_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        
        self.application.add_handler(MessageHandler(filters.Document.PDF, self.handle_document))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        print("🤖 Бот запущен...")
        self.application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            close_loop=False
        )


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    api_url = os.getenv("API_URL", "http://localhost:8000")
    
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")
    
    bot = TelegramBot(token, api_url)
    bot.run()


if __name__ == "__main__":
    main()

