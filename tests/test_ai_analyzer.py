# tests/test_ai_analyzer.py
import sys
import os
import tempfile
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import Database
from rss_parser import RSSParser
from page_parser import PageParser
from ai_analyzer import AIAnalyzer


def test_ai_analyzer():
    logging.basicConfig(level=logging.INFO)
    print("=" * 50)
    print("ТЕСТ ИИ-АНАЛИЗАТОРА (реальный API)")
    print("=" * 50)

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        test_db_path = tmp.name

    try:
        db = Database(test_db_path)

        # 1. Загружаем RSS и парсим страницы
        rss = RSSParser(db)
        page = PageParser(db)
        ai = AIAnalyzer(db)

        print("\n1. Загрузка RSS...")
        rss.process_new_entries(max_entries=2)

        print("\n2. Парсинг страниц...")
        page.process_entries(limit=2)

        # 3. Запускаем ИИ-анализ
        print("\n3. ИИ-анализ...")
        count = ai.process_entries(limit=2)
        print(f"   Обработано: {count}")

        # 4. Проверяем результат
        analyzed = db.get_entries_by_status(ai_analyzed=True, limit=2)
        if analyzed:
            print("\n📋 Пример проанализированной записи:")
            for entry in analyzed:
                print(f"  Название: {entry.title[:60]}...")
                print(f"  Оценка: {entry.relevance_score}")
                print(f"  Категория (ИИ): {entry.ai_category}")
                print(f"  Теги: {', '.join(entry.ai_tags[:3])}")
                print(f"  Рекомендация: {entry.recommendation}")
                print(f"  Краткое описание: {entry.ai_summary[:100]}...")
                print(f"  Причина: {entry.ai_analysis.get('reason', '')[:100]}...")
                assert entry.relevance_score > 0
                assert entry.ai_summary
                assert entry.recommendation in ["download", "maybe", "skip"]
        else:
            print("⚠️ Нет проанализированных записей")

        print("\n✅ ТЕСТ ЗАВЕРШЁН")
    finally:
        os.unlink(test_db_path)


if __name__ == "__main__":
    test_ai_analyzer()