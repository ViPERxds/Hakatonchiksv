"""
Модуль для планирования уведомлений
"""
import asyncio
from datetime import datetime, time
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.notifications import NotificationService
import aiohttp
import os


class NotificationScheduler:
    """Планировщик уведомлений"""
    
    def __init__(self, bot_token: str, api_url: str = "http://localhost:8000"):
        self.bot_token = bot_token
        self.api_url = api_url
        self.running = False
    
    async def send_notification(self, user_id: int, message: str):
        """Отправить уведомление пользователю через Telegram Bot API"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": user_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=data) as response:
                    return response.status == 200
            except:
                return False
    
    async def check_and_send_notifications(self):
        """Проверить и отправить уведомления о счетах к оплате"""
        db = SessionLocal()
        try:
            # Получаем пользователей с включенными уведомлениями
            user_ids = NotificationService.get_users_with_notifications_enabled(db)
            
            for user_id in user_ids:
                # Получаем счета, требующие оплаты
                pending = NotificationService.get_pending_invoices(db, user_id, days=7)
                
                if pending:
                    message = "🔔 **Напоминание о счетах к оплате:**\n\n"
                    for inv in pending[:5]:  # Максимум 5 счетов
                        days_text = f"{inv['days_left']} дн." if inv['days_left'] > 0 else "сегодня"
                        message += f"📄 №{inv['invoice_number']}\n"
                        message += f"   💰 {inv['amount']} {inv['currency']}\n"
                        message += f"   📅 Срок: {inv['due_date']} ({days_text})\n\n"
                    
                    if len(pending) > 5:
                        message += f"... и еще {len(pending) - 5} счетов"
                    
                    await self.send_notification(user_id, message)
        finally:
            db.close()
    
    async def run_scheduler(self):
        """Запустить планировщик уведомлений"""
        self.running = True
        
        while self.running:
            try:
                now = datetime.now()
                # Проверяем каждые 30 минут
                await asyncio.sleep(1800)  # 30 минут
                
                # Проверяем, нужно ли отправлять уведомления
                # (можно настроить на определенное время, например 09:00)
                await self.check_and_send_notifications()
            except Exception as e:
                print(f"Ошибка в планировщике: {str(e)}")
                await asyncio.sleep(60)  # Ждем минуту перед повтором
    
    def stop(self):
        """Остановить планировщик"""
        self.running = False

