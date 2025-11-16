"""
Скрипт для запуска телеграм-бота
"""
import os
from dotenv import load_dotenv
from app.bot import TelegramBot

load_dotenv()

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    api_url = os.getenv("API_URL", "http://localhost:8000")
    
    if not token:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не установлен в .env файле")
        return
    
    bot = TelegramBot(token, api_url)
    bot.run()

if __name__ == "__main__":
    main()

