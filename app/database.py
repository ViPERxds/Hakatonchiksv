from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()


class Invoice(Base):
    __tablename__ = 'invoices'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    user_name = Column(String, nullable=True)
    file_name = Column(String, nullable=False)
    invoice_number = Column(String, nullable=True)
    date = Column(String, nullable=True)
    seller = Column(String, nullable=True)
    buyer = Column(String, nullable=True)
    total_amount = Column(String, nullable=True)
    currency = Column(String, nullable=True, default='RUB')
    extracted_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, default=datetime.utcnow)


class UserSettings(Base):
    __tablename__ = 'user_settings'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    notifications_enabled = Column(Integer, default=1)
    notification_time = Column(String, default="09:00")
    language = Column(String, default="ru")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


database_url = os.getenv("DATABASE_URL", "sqlite:///./invoices.db")
engine = create_engine(database_url, connect_args={"check_same_thread": False} if "sqlite" in database_url else {})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

