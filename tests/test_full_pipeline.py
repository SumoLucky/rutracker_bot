# tests/test_full_pipeline.py
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import Database
from orchestrator import Orchestrator


def test_full_pipeline():
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("ИНТЕГРАЦИОННЫЙ ТЕСТ: ПОЛНЫЙ ПАЙПЛАЙН")
    print("=" * 60)

    db = Database()  # <-- убрали test_db_path
    orchestrator = Orchestrator(db)

    stats = orchestrator.run_once()

    print("\n📊 Статистика прогона:")
    print(f"  RSS: всего={stats['rss']['total_fetched']}, "
          f"существовало={stats['rss']['already_exists']}, "
          f"сохранено={stats['rss']['saved']}, "
          f"ошибок={stats['rss']['errors']}")
    print(f"  Парсинг: обработано {stats['page']['processed']}, ошибок {stats['page']['errors']}")
    print(f"  ИИ-анализ: обработано {stats['ai']['processed']}, ошибок {stats['ai']['errors']}")
    print(f"  Telegram: отправлено {stats['telegram']['sent']}, ошибок {stats['telegram']['errors']}")

    db_stats = db.get_stats()
    print(f"\n📈 Итоговая статистика БД:")
    print(f"  Всего: {db_stats.get('total', 0)}")
    print(f"  Спарсено: {db_stats.get('parsed', 0)}")
    print(f"  Проанализировано: {db_stats.get('analyzed', 0)}")
    print(f"  Отправлено: {db_stats.get('sent', 0)}")

    if db_stats.get('total', 0) > 0:
        assert db_stats.get('parsed', 0) > 0, "Записи не спарсены"
        assert db_stats.get('analyzed', 0) > 0, "Записи не проанализированы ИИ"

    print("\n✅ Интеграционный тест пройден!")


if __name__ == "__main__":
    test_full_pipeline()