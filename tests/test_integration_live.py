# tests/test_integration_live.py
import sys
import os
import tempfile
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import Database
from rss_parser import RSSParser
from page_parser import PageParser
from models import TorrentEntry


def test_integration_live():
    """
    Интеграционный тест: RSS → парсинг страниц на реальных данных.
    Требует VPN и авторизации (если включена).
    """
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("ИНТЕГРАЦИОННЫЙ ТЕСТ (RSS → ПАРСИНГ СТРАНИЦ)")
    print("=" * 60)

    # Временная БД
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        test_db_path = tmp.name

    try:
        db = Database(test_db_path)
        rss = RSSParser(db)
        page = PageParser(db)

        # 1. Загружаем RSS (максимум 3 записи)
        print("\n📡 Шаг 1: Загрузка RSS...")
        stats_rss = rss.process_new_entries(max_entries=3)
        print(f"   RSS: загружено {stats_rss['total_fetched']}, "
              f"существовало {stats_rss['already_exists']}, "
              f"сохранено {stats_rss['saved']}, ошибок {stats_rss['errors']}")

        # 2. Проверяем, что записи появились
        unparsed = db.get_unparsed_entries(limit=5)
        print(f"\n📋 Непарсенных записей: {len(unparsed)}")
        if not unparsed:
            print("⚠️ Нет записей для парсинга. Тест прерывается.")
            return

        # 3. Парсим страницы
        print("\n🔍 Шаг 2: Парсинг страниц...")
        processed = page.process_entries(limit=3)
        print(f"   Обработано страниц: {processed}")

        # 4. Проверяем обновлённые записи
        parsed = db.get_entries_by_status(page_parsed=True, limit=5)
        print(f"\n📊 Спарсенных записей: {len(parsed)}")

        if parsed:
            print("\n📋 Пример спарсенной записи:")
            entry = parsed[0]
            print(f"  Название: {entry.title[:60]}...")
            print(f"  Размер: {entry.size}")
            print(f"  Сиды: {entry.seeds}")
            print(f"  Личи: {entry.leechers}")
            print(f"  Скачиваний: {entry.downloads}")
            print(f"  Категория: {entry.category}")
            print(f"  Описание (первые 200 символов): {entry.full_description[:200]}...")
            print(f"  Статус: is_page_parsed={entry.is_page_parsed}")

            # Проверяем, что поля заполнены
            assert entry.size != "Неизвестно"
            assert entry.seeds >= 0
            assert entry.category != "Неизвестно"
            assert len(entry.full_description) > 50
            assert entry.is_page_parsed == True

            print("\n✅ Интеграционный тест пройден!")
        else:
            print("⚠️ Нет спарсенных записей для проверки.")

        # 5. Статистика
        stats = db.get_stats()
        print("\n📈 Общая статистика БД:")
        print(f"  Всего: {stats.get('total', 0)}")
        print(f"  Спарсено: {stats.get('parsed', 0)}")
        print(f"  Проанализировано: {stats.get('analyzed', 0)}")
        print(f"  Отправлено: {stats.get('sent', 0)}")

    finally:
        # Удаляем временную БД
        os.unlink(test_db_path)
        print("\n🧹 Временная БД удалена.")


if __name__ == "__main__":
    test_integration_live()