# test_config.py
import sys
import os

# Добавляем папку src в путь импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from config import config

def main():
    print("=" * 50)
    print("ПРОВЕРКА КОНФИГУРАЦИИ")
    print("=" * 50)

    # Проверяем загрузку всех параметров
    print(f"TELEGRAM_TOKEN: {config.TELEGRAM_TOKEN[:15]}... (длина {len(config.TELEGRAM_TOKEN)})")
    print(f"CHAT_ID: {config.CHAT_ID}")
    print(f"RSS_URL: {config.RSS_URL}")
    print(f"DB_PATH: {config.DB_PATH}")
    print(f"PARSING_DELAY: {config.PARSING_DELAY} сек")
    print(f"MIN_RELEVANCE_SCORE: {config.MIN_RELEVANCE_SCORE}")
    print(f"MAX_ENTRIES_PER_DAY: {config.MAX_ENTRIES_PER_DAY}")
    print(f"USE_LOCAL_AI: {config.USE_LOCAL_AI}")
    print(f"DEBUG: {config.DEBUG}")
    print(f"CHECK_INTERVAL_MINUTES: {config.CHECK_INTERVAL_MINUTES} мин")

    print("\n" + "=" * 50)
    print("✅ КОНФИГУРАЦИЯ ЗАГРУЖЕНА УСПЕШНО")
    print("=" * 50)


if __name__ == "__main__":
    main()