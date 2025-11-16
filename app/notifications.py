from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import Invoice, UserSettings
from typing import List, Dict


class NotificationService:
    """Сервис для управления уведомлениями"""
    
    @staticmethod
    def get_users_with_notifications_enabled(db: Session) -> List[int]:
        """Получить список пользователей с включенными уведомлениями"""
        settings = db.query(UserSettings).filter(
            UserSettings.notifications_enabled == 1
        ).all()
        return [s.user_id for s in settings]
    
    @staticmethod
    def get_pending_invoices(db: Session, user_id: int, days: int = 7) -> List[Dict]:
        """Получить счета, требующие оплаты в ближайшие N дней"""
        today = datetime.utcnow().date()
        end_date = today + timedelta(days=days)
        
        invoices = db.query(Invoice).filter(
            Invoice.user_id == user_id,
            Invoice.date.isnot(None)
        ).all()
        
        pending = []
        for invoice in invoices:
            try:
                # Парсим дату из строки
                date_str = invoice.date
                # Пробуем разные форматы
                for fmt in ['%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d', '%d.%m.%y']:
                    try:
                        invoice_date = datetime.strptime(date_str, fmt).date()
                        # Проверяем, нужно ли напоминание
                        if today <= invoice_date <= end_date:
                            # Пытаемся извлечь срок оплаты из данных
                            payment_terms = invoice.extracted_data.get('payment_terms', '')
                            days_to_pay = 0
                            if payment_terms:
                                # Извлекаем число дней
                                import re
                                match = re.search(r'(\d+)\s*дн', payment_terms, re.IGNORECASE)
                                if match:
                                    days_to_pay = int(match.group(1))
                            
                            due_date = invoice_date + timedelta(days=days_to_pay) if days_to_pay > 0 else invoice_date
                            
                            if today <= due_date <= end_date:
                                pending.append({
                                    'invoice_number': invoice.invoice_number or 'N/A',
                                    'date': invoice.date,
                                    'due_date': due_date.strftime('%d.%m.%Y'),
                                    'amount': invoice.total_amount or 'N/A',
                                    'currency': invoice.currency or 'RUB',
                                    'days_left': (due_date - today).days
                                })
                            break
                    except:
                        continue
            except:
                continue
        
        return pending
    
    @staticmethod
    def get_user_settings(db: Session, user_id: int) -> UserSettings:
        """Получить или создать настройки пользователя"""
        settings = db.query(UserSettings).filter(
            UserSettings.user_id == user_id
        ).first()
        
        if not settings:
            settings = UserSettings(
                user_id=user_id,
                notifications_enabled=1,
                notification_time="09:00"
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)
        
        return settings
    
    @staticmethod
    def toggle_notifications(db: Session, user_id: int) -> bool:
        """Переключить уведомления пользователя"""
        settings = NotificationService.get_user_settings(db, user_id)
        settings.notifications_enabled = 1 - settings.notifications_enabled
        settings.updated_at = datetime.utcnow()
        db.commit()
        return settings.notifications_enabled == 1

