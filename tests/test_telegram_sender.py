# tests/test_telegram_sender.py
import sys
import os
import tempfile
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import Database
from rss_parser import RSSParser
from page_parser import PageParser
from ai_analyzer import AIAnalyzer
from telegram_sender import TelegramSender
from models import TorrentEntry
from datetime import datetime, timezone


def test_telegram_sender():
    logging.basicConfig(level=logging.INFO)
    print("=" * 50)
    print("ТЕСТ TELEGRAM SENDER (реальная отправка)")
    print("=" * 50)

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        test_db_path = tmp.name

    try:
        db = Database(test_db_path)

        # Прогоняем весь конвейер для пары записей
        rss = RSSParser(db)
        page = PageParser(db)
        ai = AIAnalyzer(db)
        sender = TelegramSender(db)

        print("\n1. Загрузка RSS...")
        rss.process_new_entries(max_entries=2)

        print("\n2. Парсинг страниц...")
        page.process_entries(limit=2)

        print("\n3. ИИ-анализ...")
        ai.process_entries(limit=2)

        # Проверяем, есть ли записи для отправки
        ready = db.get_ready_to_send_by_score(limit=1)
        if not ready:
            print("⚠️ Нет записей с достаточным рейтингом для отправки.")
            print("   Создаём тестовую запись с высоким рейтингом...")
            # Создаём запись с высоким рейтингом принудительно
            entry = TorrentEntry(
                rss_id="test:telegram_forced",
                title="Тестовая раздача для отправки",
                link="https://rutracker.org/forum/viewtopic.php?t=6873886",
                updated=datetime.now(timezone.utc).replace(tzinfo=None),
                summary="Тест",
                author="test_user",
                relevance_score=85.0,
                ai_summary="Это тестовое описание для проверки отправки в Telegram.",
                recommendation="download",
                ai_tags=["тест", "проверка"],
                is_page_parsed=True,
                is_ai_analyzed=True,
                is_sent=False,
                size="100 MB",
                seeds=10,
                leechers=5,
                downloads=100,
                category="Тестовая категория"
            )
            db.save_entry(entry)

        # 4. Отправка
        print("\n4. Отправка в Telegram...")
        sent = sender.send_entries(limit=1)
        print(f"   Отправлено: {sent}")

        if sent > 0:
            print("\n✅ Тест отправки пройден! Проверьте Telegram.")
        else:
            print("\n⚠️ Ничего не отправлено (возможно, нет записей с высоким рейтингом).")

    finally:
        os.unlink(test_db_path)


if __name__ == "__main__":
    test_telegram_sender()