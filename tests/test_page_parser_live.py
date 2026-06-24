# tests/test_page_parser_live.py
import sys
import os
import tempfile
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import Database
from page_parser import PageParser
from models import TorrentEntry
from datetime import datetime, timezone


def test_page_parser_live():
    """
    Тест с реальным HTTP-запросом к Rutracker.org.
    Требует включённого VPN или доступа к сайту.
    """
    logging.basicConfig(level=logging.INFO)
    print("=" * 50)
    print("ТЕСТ PAGE PARSER (РЕАЛЬНЫЙ ЗАПРОС)")
    print("=" * 50)

    # Создаём временную БД
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        test_db_path = tmp.name

    try:
        db = Database(test_db_path)

        # Создаём тестовую запись с реальной ссылкой
        entry = TorrentEntry(
            rss_id="test:page_parser_live",
            title="Тестовая раздача (живой запрос)",
            link="https://rutracker.org/forum/viewtopic.php?t=6873886",
            updated=datetime.now(timezone.utc).replace(tzinfo=None),
            summary="Тестовое описание",
            author="test_user"
        )
        db.save_entry(entry)

        # Запускаем парсер (реальный запрос)
        parser = PageParser(db)
        processed = parser.process_entries(limit=1)

        assert processed == 1, "Не удалось обработать запись"

        # Проверяем обновлённую запись
        updated_entry = db.get_entry("test:page_parser_live")
        print(f"  size: {updated_entry.size}")
        print(f"  seeds: {updated_entry.seeds}")
        print(f"  leechers: {updated_entry.leechers}")
        print(f"  downloads: {updated_entry.downloads}")
        print(f"  category: {updated_entry.category}")
        assert updated_entry is not None
        assert updated_entry.is_page_parsed == True
        assert updated_entry.size != "Неизвестно"
        assert updated_entry.seeds >= 0
        assert updated_entry.leechers >= 0
        assert updated_entry.downloads >= 0
        assert updated_entry.category != "Неизвестно"
        assert len(updated_entry.full_description) > 50

        print("\n✅ Все проверки пройдены!")
        print(f"  Размер: {updated_entry.size}")
        print(f"  Сиды: {updated_entry.seeds}")
        print(f"  Личи: {updated_entry.leechers}")
        print(f"  Скачиваний: {updated_entry.downloads}")
        print(f"  Категория: {updated_entry.category}")
        print(f"  Описание (первые 150 символов): {updated_entry.full_description[:150]}...")

    finally:
        os.unlink(test_db_path)


if __name__ == "__main__":
    test_page_parser_live()