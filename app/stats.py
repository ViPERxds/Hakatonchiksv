from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import datetime, timedelta
from typing import Dict, List
from app.database import Invoice


class StatisticsService:
    @staticmethod
    def get_user_stats(db: Session, user_id: int, days: int = 30) -> Dict:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        total_invoices = db.query(Invoice).filter(
            Invoice.user_id == user_id,
            Invoice.created_at >= start_date
        ).count()
        
        invoices = db.query(Invoice).filter(
            Invoice.user_id == user_id,
            Invoice.created_at >= start_date,
            Invoice.total_amount.isnot(None)
        ).all()
        
        total_sum = 0.0
        currency_counts = {}
        seller_counts = {}
        
        for invoice in invoices:
            try:
                amount_str = invoice.total_amount.replace(' ', '').replace(',', '.')
                amount_clean = ''.join(c for c in amount_str if c.isdigit() or c == '.')
                if amount_clean:
                    amount = float(amount_clean)
                    total_sum += amount
            except:
                pass
            
            currency = invoice.currency or 'RUB'
            currency_counts[currency] = currency_counts.get(currency, 0) + 1
            
            if invoice.seller:
                seller_counts[invoice.seller] = seller_counts.get(invoice.seller, 0) + 1
        monthly_stats = db.query(
            extract('month', Invoice.created_at).label('month'),
            extract('year', Invoice.created_at).label('year'),
            func.count(Invoice.id).label('count')
        ).filter(
            Invoice.user_id == user_id,
            Invoice.created_at >= start_date
        ).group_by(
            extract('month', Invoice.created_at),
            extract('year', Invoice.created_at)
        ).all()
        
        monthly_data = []
        for stat in monthly_stats:
            monthly_data.append({
                'month': int(stat.month),
                'year': int(stat.year),
                'count': stat.count
            })
        
        top_sellers = sorted(
            seller_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return {
            'total_invoices': total_invoices,
            'total_amount': round(total_sum, 2),
            'currency_counts': currency_counts,
            'top_sellers': [{'name': name, 'count': count} for name, count in top_sellers],
            'monthly_stats': monthly_data,
            'period_days': days
        }
    
    @staticmethod
    def get_recent_invoices(db: Session, user_id: int, limit: int = 10) -> List[Dict]:
        invoices = db.query(Invoice).filter(
            Invoice.user_id == user_id
        ).order_by(
            Invoice.created_at.desc()
        ).limit(limit).all()
        
        return [
            {
                'id': inv.id,
                'invoice_number': inv.invoice_number or 'N/A',
                'date': inv.date or 'N/A',
                'seller': inv.seller or 'N/A',
                'total_amount': inv.total_amount or 'N/A',
                'currency': inv.currency or 'RUB',
                'created_at': inv.created_at.strftime('%Y-%m-%d %H:%M'),
                'buyer': inv.buyer or None
            }
            for inv in invoices
        ]

