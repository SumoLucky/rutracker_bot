# src/telegram_sender.py
import logging
import time
import os
import html  # <-- добавить
from typing import Optional
from datetime import datetime

import telebot

from config import config
from database import Database
from models import TorrentEntry
from type_detector import get_type_emoji

logger = logging.getLogger(__name__)


class TelegramSender:
    """Этап 4: Отправка отфильтрованных записей в Telegram"""

    MAX_MESSAGE_LENGTH = 4096
    LOG_FILE = "sent_messages.log"
    MAX_LOG_LINES = 200

    def __init__(self, db: Database):
        self.db = db
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.CHAT_ID
        self.min_score = config.MIN_RELEVANCE_SCORE
        self.delay = config.SEND_DELAY
        self.retries = config.SEND_RETRIES

        if not self.token or not self.chat_id:
            logger.error("TELEGRAM_TOKEN или CHAT_ID не заданы, отправка невозможна")
            self.bot = None
        else:
            self.bot = telebot.TeleBot(self.token)

    def _log_sent_message(self, message: str):
        """Сохраняет отправленное сообщение в файл для отладки (только DEBUG)"""
        if not config.DEBUG:
            return
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            truncated = message[:2000] + "..." if len(message) > 2000 else message
            entry = f"[{timestamp}]\n{truncated}\n{'-'*60}\n"

            lines = []
            if os.path.exists(self.LOG_FILE):
                with open(self.LOG_FILE, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

            separator = '-'*60 + '\n'
            parts = ''.join(lines).split(separator)
            if len(parts) > self.MAX_LOG_LINES:
                parts = parts[-self.MAX_LOG_LINES:]

            with open(self.LOG_FILE, 'w', encoding='utf-8') as f:
                f.write(separator.join(parts))
                if parts:
                    f.write(separator)

        except Exception as e:
            logger.warning(f"Не удалось записать сообщение в лог: {e}")

    def _format_message(self, entry: TorrentEntry) -> str:
        content_type = entry.content_type or "неизвестно"
        emoji = get_type_emoji(content_type)

        # Экранируем все поля, которые могут содержать HTML-теги
        title = html.escape(entry.title)
        ai_summary = html.escape(entry.ai_summary)
        size = html.escape(entry.size)
        author = html.escape(entry.author)
        category = html.escape(entry.category)

        score = entry.relevance_score
        if score >= 80:
            rating_emoji = "🔥"
        elif score >= 60:
            rating_emoji = "⭐"
        elif score >= 40:
            rating_emoji = "📌"
        else:
            rating_emoji = "ℹ️"

        rec = entry.recommendation
        rec_emoji = {"download": "✅", "maybe": "🔄", "skip": "❌"}.get(rec, "ℹ️")
        rec_text = {"download": "скачать", "maybe": "возможно", "skip": "пропустить"}.get(rec, rec)

        tags_str = ""
        if entry.ai_tags:
            # Экранируем теги
            escaped_tags = [html.escape(tag) for tag in entry.ai_tags[:5]]
            tags_str = "\n" + " ".join(f"#{tag}" for tag in escaped_tags)

        updated_str = entry.updated.strftime('%d-%m-%Y %H:%M') if entry.updated else "Неизвестно"

        details = (
            f"📦 <b>Размер:</b> {size}\n"
            f"👤 <b>Автор:</b> {author}\n"
            f"📥 <b>Сиды:</b> {entry.seeds}  |  <b>Личи:</b> {entry.leechers}\n"
            f"📅 <b>Дата:</b> {updated_str}"
        )

        message = f"""
{emoji} <b>{content_type.capitalize()}:</b> {title}

📝 <b>Описание:</b>
{ai_summary}

📊 <b>Оценка:</b> {score}/100 ({rec_emoji} {rec_text})

<b>📌 Дополнительно:</b>
{details}
{tags_str}
"""
        return message.strip()

    def _send_with_retry(self, chat_id: str, text: str, parse_mode: str, disable_web_page_preview: bool) -> bool:
        for attempt in range(1, self.retries + 1):
            try:
                self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                )
                return True
            except Exception as e:
                logger.warning(f"Ошибка отправки (попытка {attempt}/{self.retries}): {e}")
                if attempt == self.retries:
                    logger.error(f"Не удалось отправить сообщение после {self.retries} попыток")
                    return False
                time.sleep(2 ** attempt)
        return False

    def send_entries(self, limit: Optional[int] = None) -> int:
        if not self.bot:
            logger.error("Бот не инициализирован, отправка невозможна")
            return 0

        entries = self.db.get_ready_to_send_by_score(
            min_score=self.min_score,
            limit=limit
        )

        if not entries:
            logger.info("Нет записей для отправки")
            return 0

        sent_count = 0
        for entry in entries:
            try:
                message = self._format_message(entry)

                if len(message) > self.MAX_MESSAGE_LENGTH:
                    logger.warning(f"Сообщение для {entry.rss_id} превышает {self.MAX_MESSAGE_LENGTH} символов, обрезаем")
                    message = message[:self.MAX_MESSAGE_LENGTH - 10] + "...\n(обрезано)"

                success = self._send_with_retry(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )

                if success:
                    self.db.mark_as_sent(entry.rss_id)
                    self.db.log_processing(
                        entry.rss_id,
                        'telegram_sender',
                        'success',
                        f'Отправлено (тип: {entry.content_type}, оценка: {entry.relevance_score})'
                    )
                    self._log_sent_message(message)
                    sent_count += 1
                    logger.info(f"✅ Отправлено: {entry.title[:50]}... (тип: {entry.content_type}, оценка: {entry.relevance_score})")
                    time.sleep(self.delay)
                else:
                    self.db.log_processing(
                        entry.rss_id,
                        'telegram_sender',
                        'error',
                        'Не удалось отправить после всех попыток'
                    )

            except Exception as e:
                logger.error(f"Ошибка отправки {entry.rss_id}: {e}")
                self.db.log_processing(entry.rss_id, 'telegram_sender', 'error', str(e))

        logger.info(f"Отправлено записей: {sent_count}/{len(entries)}")
        return sent_count