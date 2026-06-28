# tests/test_rss_parser.py
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import Database
from rss_parser import RSSParser


def test_rss_parser():
    logging.basicConfig(level=logging.INFO)
    print("=" * 50)
    print("ТЕСТ RSS ПАРСЕРА")
    print("=" * 50)

    # Используем основную БД (или временную, если хотите)
    db = Database()  # <-- убрали test_db_path
    parser = RSSParser(db)

    stats = parser.process_new_entries(max_entries=5)
    print("\n📊 Результат обработки:")
    print(f"  Всего в RSS: {stats['total_fetched']}")
    print(f"  Уже существовало: {stats['already_exists']}")
    print(f"  Сохранено новых: {stats['saved']}")
    print(f"  Ошибок: {stats['errors']}")

    entries = db.get_unparsed_entries(limit=3)
    if entries:
        print("\n📋 Первые записи:")
        for i, entry in enumerate(entries, 1):
            print(f"  {i}. {entry.title[:60]}...")
            print(f"     Автор: {entry.author}, Категория: {entry.category or entry.category_id}")
            print(f"     Дата: {entry.updated}")

    assert stats['saved'] > 0, "Не удалось сохранить ни одной записи"
    print("\n✅ ТЕСТ ПРОЙДЕН")


if __name__ == "__main__":
    test_rss_parser()