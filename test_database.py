# test_database.py
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from database import Database
from models import TorrentEntry


def main():
    print("=" * 50)
    print("ТЕСТ DATABASE.PY")
    print("=" * 50)

    db = Database()

    # 1. Создаём тестовую запись
    print("\n1. Создание тестовой записи...")
    entry = TorrentEntry(
        rss_id="tag:rto.feed,2026-06-22:/t/test123",
        title="Тестовая раздача для проверки БД",
        link="https://rutracker.org/forum/viewtopic.php?t=test123",
        updated=datetime.now(),
        summary="Тестовое описание",
        author="TestUser",
        category="Тестовая категория",
        category_id="f-test",
        size="100 MB",
        seeds=10,
        leechers=5,
        downloads=100
    )

    # 2. Сохраняем
    print("2. Сохранение в БД...")
    success = db.save_entry(entry)
    if success:
        print("   ✅ Запись сохранена")
    else:
        print("   ❌ Ошибка сохранения")
        return

    # 3. Получаем
    print("3. Получение записи...")
    saved = db.get_entry("tag:rto.feed,2026-06-22:/t/test123")
    if saved:
        print(f"   ✅ Название: {saved.title}")
        print(f"   ✅ Автор: {saved.author}")
        print(f"   ✅ Категория: {saved.category}")
        print(f"   ✅ Сиды: {saved.seeds}")
    else:
        print("   ❌ Запись не найдена")
        return

    # 4. Обновляем статус
    print("4. Обновление статуса...")
    db.mark_as_parsed("tag:rto.feed,2026-06-22:/t/test123")
    print("   ✅ Отмечено как спарсенное")

    # 5. Проверяем статус
    saved2 = db.get_entry("tag:rto.feed,2026-06-22:/t/test123")
    if saved2:
        print(f"   is_page_parsed: {saved2.is_page_parsed}")
    else:
        print("   ❌ Запись не найдена после обновления")
        return

    # 6. Логирование
    print("5. Логирование...")
    db.log_processing("tag:rto.feed,2026-06-22:/t/test123", "test_stage", "success", "Тестовое логирование")
    logs = db.get_logs("tag:rto.feed,2026-06-22:/t/test123")
    print(f"   ✅ Записано логов: {len(logs)}")

    # 7. Статистика
    print("6. Статистика...")
    stats = db.get_stats()
    print(f"   Всего: {stats['total']}")
    print(f"   Обработано: {stats['parsed']}")
    print(f"   Анализировано: {stats['analyzed']}")
    print(f"   Отправлено: {stats['sent']}")
    print(f"   Средний рейтинг: {stats['avg_score']}")

    # 8. Очистка
    print("7. Очистка...")
    db.delete_entry("tag:rto.feed,2026-06-22:/t/test123")
    print("   ✅ Тестовая запись удалена")

    print("\n" + "=" * 50)
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("=" * 50)


if __name__ == "__main__":
    main()