# src/telegram_sender.py
import logging
import time
from typing import Optional

import telebot

from config import config
from database import Database
from models import TorrentEntry

logger = logging.getLogger(__name__)


class TelegramSender:
    """Этап 4: Отправка отфильтрованных записей в Telegram"""

    MAX_MESSAGE_LENGTH = 4096

    def __init__(self, db: Database):
        self.db = db
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.CHAT_ID
        self.min_score = config.MIN_RELEVANCE_SCORE
        self.delay = config.SEND_DELAY
        self.retries = config.SEND_RETRIES  # добавим в config

        if not self.token or not self.chat_id:
            logger.error("TELEGRAM_TOKEN или CHAT_ID не заданы, отправка невозможна")
            self.bot = None
        else:
            self.bot = telebot.TeleBot(self.token)

    def _format_message(self, entry: TorrentEntry) -> str:
        """Формирует HTML-сообщение для отправки"""
        # Эмодзи для оценки
        score = entry.relevance_score
        if score >= 80:
            rating_emoji = "🔥"
        elif score >= 60:
            rating_emoji = "⭐"
        elif score >= 40:
            rating_emoji = "📌"
        else:
            rating_emoji = "ℹ️"

        # Рекомендация
        rec = entry.recommendation
        rec_emoji = {"download": "✅", "maybe": "🔄", "skip": "❌"}.get(rec, "ℹ️")
        rec_text = {"download": "скачать", "maybe": "возможно", "skip": "пропустить"}.get(rec, rec)

        # Теги (если есть)
        tags_str = ""
        if entry.ai_tags:
            tags_str = "\n" + " ".join(f"#{tag}" for tag in entry.ai_tags[:5])

        # Дата с fallback
        updated_str = entry.updated.strftime('%d-%m-%Y %H:%M') if entry.updated else "Неизвестно"

        # Краткая сводка
        details = (
            f"📦 <b>Размер:</b> {entry.size}\n"
            f"👤 <b>Автор:</b> {entry.author}\n"
            f"📥 <b>Сиды:</b> {entry.seeds}  |  <b>Личи:</b> {entry.leechers}\n"
            f"📅 <b>Дата:</b> {updated_str}"
        )

        message = f"""
{rating_emoji} <b>{entry.title}</b>

📝 <b>Описание:</b>
{entry.ai_summary}

📊 <b>Оценка:</b> {score}/100 ({rec_emoji} {rec_text})

<b>📌 Дополнительно:</b>
{details}
{tags_str}
"""
        return message.strip()

    def _send_with_retry(self, chat_id: str, text: str, parse_mode: str, disable_web_page_preview: bool) -> bool:
        """Отправка с повторными попытками"""
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
                time.sleep(2 ** attempt)  # экспоненциальная задержка
        return False

    def send_entries(self, limit: Optional[int] = None) -> int:
        """
        Отправляет все неотправленные записи с рейтингом >= порога.
        """
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
                # Формируем сообщение
                message = self._format_message(entry)

                # Обрезаем, если превышает лимит Telegram
                if len(message) > self.MAX_MESSAGE_LENGTH:
                    logger.warning(f"Сообщение для {entry.rss_id} превышает {self.MAX_MESSAGE_LENGTH} символов, обрезаем")
                    message = message[:self.MAX_MESSAGE_LENGTH - 10] + "...\n(обрезано)"

                # Отправляем с повторными попытками
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
                        f'Отправлено (оценка {entry.relevance_score})'
                    )
                    sent_count += 1
                    logger.info(f"✅ Отправлено: {entry.title[:50]}... (оценка {entry.relevance_score})")
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