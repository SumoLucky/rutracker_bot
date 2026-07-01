# Комментарий для проверки автодеплоя измененный в седьмой раз
# main.py
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta  # <-- исправлено

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from config import config
from database import Database
from fastapi import FastAPI, Request
from orchestrator import Orchestrator
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import subprocess
import hmac
import hashlib

DEPLOY_SECRET = os.getenv("DEPLOY_SECRET", "ваш_секрет_замените_на_сервере")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rutracker_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

application = None
scheduler = None


# ========== Telegram-команды ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот для фильтрации раздач Rutracker запущен!\n"
        "Новые раздачи будут приходить автоматически, если они соответствуют вашим интересам."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Доступные команды:\n"
        "/start — показать приветствие\n"
        "/help — эта справка\n"
        "/status — статус бота и статистика"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = Database()
    stats = db.get_stats()
    await update.message.reply_text(
        f"📊 Статистика бота:\n"
        f"Всего записей: {stats.get('total', 0)}\n"
        f"Спарсено: {stats.get('parsed', 0)}\n"
        f"Проанализировано: {stats.get('analyzed', 0)}\n"
        f"Отправлено: {stats.get('sent', 0)}"
    )


# ========== Фоновая задача ==========
def run_orchestrator():
    """Запуск основного пайплайна (RSS → парсинг → ИИ → Telegram)"""
    try:
        logger.info("🔄 Запуск плановой обработки...")
        db = Database()
        orchestrator = Orchestrator(db)
        stats = orchestrator.run_once()
        logger.info(f"✅ Плановая обработка завершена: {stats}")
    except Exception as e:
        logger.error(f"Ошибка в плановой обработке: {e}")


# ========== FastAPI ==========
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan-менеджер: настройка при старте, очистка при остановке"""
    global application, scheduler

    # 1. Инициализируем Telegram-приложение с таймаутами
    application = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .build()
    )

    # 2. Регистрируем команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status))

    # 3. Настраиваем webhook (если URL задан)
    webhook_url = config.WEBHOOK_URL
    if webhook_url:
        webhook_url = f"{webhook_url.rstrip('/')}/webhook"
        try:
            await application.bot.set_webhook(webhook_url)
            logger.info(f"✅ Webhook установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Ошибка установки webhook: {e}")
    else:
        logger.warning("⚠️ WEBHOOK_URL не задан, webhook не установлен")

    # 4. Запускаем планировщик
    scheduler = BackgroundScheduler()
    first_run_delay = 0 if config.RUN_ON_START else 10
    scheduler.add_job(
        run_orchestrator,
        'interval',
        minutes=config.CHECK_INTERVAL_MINUTES,
        next_run_time=datetime.now() + timedelta(seconds=first_run_delay)
    )
    scheduler.start()
    logger.info(f"✅ Планировщик запущен (интервал: {config.CHECK_INTERVAL_MINUTES} мин, "
                f"первый запуск через {first_run_delay} сек)")

    yield

    # Очистка при остановке
    if scheduler:
        scheduler.shutdown()
    if application:
        try:
            await application.bot.delete_webhook()
        except:
            pass
        await application.shutdown()
    logger.info("✅ Приложение остановлено")


app = FastAPI(lifespan=lifespan, title="Rutracker Bot")


@app.post("/webhook")
async def webhook(request: Request):
    """Эндпоинт для webhook от Telegram — всегда возвращает 200 OK"""
    global application
    if application is None:
        logger.error("Application not initialized")
        return {"status": "error", "message": "Application not initialized"}

    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        # Всё равно возвращаем 200, чтобы Telegram не пересылал повторно
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "Rutracker Bot is running", "status": "ok"}


@app.post("/deploy")
async def deploy(request: Request):
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        return {"status": "error", "message": "Missing signature"}

    body = await request.body()
    expected = "sha256=" + hmac.new(
        DEPLOY_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return {"status": "error", "message": "Invalid signature"}

    subprocess.Popen(
        ["/bin/bash", "/home/rutracker/bot/deploy.sh"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return {"status": "ok", "message": "Deploy started"}

# ========== Точка входа ==========
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=config.DEBUG,
    )