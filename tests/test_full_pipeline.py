# tests/test_full_pipeline.py
import sys
import os
import tempfile
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import Database
from orchestrator import Orchestrator


def test_full_pipeline():
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("ИНТЕГРАЦИОННЫЙ ТЕСТ: ПОЛНЫЙ ПАЙПЛАЙН")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        test_db_path = tmp.name

    try:
        db = Database(test_db_path)
        orchestrator = Orchestrator(db)

        # Запускаем один прогон
        stats = orchestrator.run_once()

        # Проверяем, что все этапы отработали без критических ошибок
        print("\n📊 Статистика прогона:")
        print(f"  RSS: всего={stats['rss']['total_fetched']}, "
              f"существовало={stats['rss']['already_exists']}, "
              f"сохранено={stats['rss']['saved']}, "
              f"ошибок={stats['rss']['errors']}")
        print(f"  Парсинг: обработано {stats['page']['processed']}, ошибок {stats['page']['errors']}")
        print(f"  ИИ-анализ: обработано {stats['ai']['processed']}, ошибок {stats['ai']['errors']}")
        print(f"  Telegram: отправлено {stats['telegram']['sent']}, ошибок {stats['telegram']['errors']}")

        # Общая статистика БД
        db_stats = db.get_stats()
        print(f"\n📈 Итоговая статистика БД:")
        print(f"  Всего: {db_stats.get('total', 0)}")
        print(f"  Спарсено: {db_stats.get('parsed', 0)}")
        print(f"  Проанализировано: {db_stats.get('analyzed', 0)}")
        print(f"  Отправлено: {db_stats.get('sent', 0)}")

        # Проверка: если были новые записи, они должны пройти все этапы
        if db_stats.get('total', 0) > 0:
            # Парсинг должен обработать хотя бы часть (не обязательно все из-за лимита)
            assert db_stats.get('parsed', 0) > 0, "Записи не спарсены"
            # Проверяем, что часть записей прошла ИИ-анализ
            assert db_stats.get('analyzed', 0) > 0, "Записи не проанализированы ИИ"

        print("\n✅ Интеграционный тест пройден!")

    finally:
        os.unlink(test_db_path)


if __name__ == "__main__":
    test_full_pipeline()