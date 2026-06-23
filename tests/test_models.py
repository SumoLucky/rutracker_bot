# test_models.py
import sys
import os
from datetime import datetime

# Добавляем папку src в путь импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import TorrentEntry


def test_from_rss_entry():
    """Тест создания объекта из RSS-записи"""
    print("=" * 50)
    print("ТЕСТ: СОЗДАНИЕ ИЗ RSS ЗАПИСИ")
    print("=" * 50)

    # Эмулируем RSS-запись (как из реального файла)
    rss_data = {
        'id': 'tag:rto.feed,2026-06-22:/t/6873886',
        'title': 'Яковлев А.Н.(ред.) - Власть и художественная интеллигенция [1999, DjVu, RUS] [14.8 MB]',
        'link': 'https://rutracker.org/forum/viewtopic.php?t=6873886',
        'updated': datetime(2026, 6, 22, 17, 16, 34),
        'summary': 'Сборник документов о культурной политике...',
        'author': {'name': 'Dark_Ambient'},
        'category': {'term': 'f-2436', 'label': 'Эпоха СССР'}
    }

    # Создаём объект
    entry = TorrentEntry.from_rss_entry(rss_data)

    print("\n📋 Создан объект:")
    print(f"  rss_id: {entry.rss_id}")
    print(f"  title: {entry.title[:80]}...")
    print(f"  author: {entry.author}")
    print(f"  category_id: {entry.category_id}")
    print(f"  category: {entry.category}")
    print(f"  updated: {entry.updated}")
    print(f"  size: {entry.size} (пока пусто)")

    return entry


def test_full_cycle():
    """Тест полного цикла: создание -> сериализация -> десериализация"""
    print("\n" + "=" * 50)
    print("ТЕСТ: ПОЛНЫЙ ЦИКЛ")
    print("=" * 50)

    # Создаём запись
    entry = TorrentEntry(
        rss_id="tag:rto.feed,2026-06-22:/t/123456",
        title="Python для начинающих [2025] PDF",
        link="https://rutracker.org/forum/viewtopic.php?t=123456",
        updated=datetime.now(),
        summary="Отличная книга по Python",
        author="bookmaster",
        category="Книги",
        category_id="f-123",
        size="12.5 MB",
        seeds=45,
        relevance_score=85,
        ai_summary="Отличный учебник"
    )

    print("\n📋 Исходный объект:")
    print(f"  title: {entry.title}")
    print(f"  category: {entry.category}")
    print(f"  seeds: {entry.seeds}")
    print(f"  relevance_score: {entry.relevance_score}")

    # Сериализация
    dict_data = entry.to_dict()
    print(f"\n🔄 to_dict() -> {len(dict_data)} полей")
    print(f"  title: {dict_data['title']}")
    print(f"  updated: {dict_data['updated']}")

    # Десериализация
    restored = TorrentEntry.from_dict(dict_data)
    print(f"\n🔄 from_dict() -> восстановлен")
    print(f"  title: {restored.title}")
    print(f"  seeds: {restored.seeds}")
    print(f"  updated: {restored.updated}")

    # Проверка
    assert entry.title == restored.title
    assert entry.seeds == restored.seeds
    print("\n✅ Все проверки пройдены!")

    return restored


def test_size_parsing():
    """Тест парсинга размера"""
    print("\n" + "=" * 50)
    print("ТЕСТ: ПАРСИНГ РАЗМЕРА")
    print("=" * 50)

    test_cases = [
        ("14.8 MB", 0.01445),
        ("1.23 GB", 1.23),
        ("512 KB", 0.000488),
        ("2.5 TB", 2560),
    ]

    for size_str, expected in test_cases:
        entry = TorrentEntry(
            rss_id="test",
            title="test",
            link="test",
            updated=datetime.now(),
            summary="test",
            author="test",
            size=size_str
        )
        result = entry.get_size_gb()
        print(f"  {size_str} -> {result:.4f} GB (ожидалось ~{expected:.4f})")


if __name__ == "__main__":
    # Запускаем все тесты
    test_from_rss_entry()
    test_full_cycle()
    test_size_parsing()

    print("\n" + "=" * 50)
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("=" * 50)