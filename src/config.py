# src/config.py
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # Telegram
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    CHAT_ID: str = os.getenv("CHAT_ID", "")

    # RSS
    RSS_URL: str = os.getenv("RSS_URL", "https://feed.rutracker.cc/atom/f/0.atom")
    RSS_MAX_ENTRIES: int = int(os.getenv("RSS_MAX_ENTRIES", "30"))
    RSS_TIMEOUT: int = int(os.getenv("RSS_TIMEOUT", "30"))
    RSS_RETRIES: int = int(os.getenv("RSS_RETRIES", "3"))

    # База данных
    DB_PATH: str = os.getenv("DB_PATH", "data/rutracker.db")

    # Парсинг страниц
    PARSING_DELAY: float = float(os.getenv("PARSING_DELAY", "0.5"))
    PARSING_TIMEOUT: int = int(os.getenv("PARSING_TIMEOUT", "15"))

    # ИИ
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    USE_LOCAL_AI: bool = os.getenv("USE_LOCAL_AI", "false").lower() == "true"
    LOCAL_AI_URL: str = os.getenv("LOCAL_AI_URL", "http://localhost:11434/api/generate")
    LOCAL_AI_MODEL: str = os.getenv("LOCAL_AI_MODEL", "llama2")

    # Фильтрация и отправка
    MIN_RELEVANCE_SCORE: int = int(os.getenv("MIN_RELEVANCE_SCORE", "50"))
    MAX_ENTRIES_PER_DAY: int = int(os.getenv("MAX_ENTRIES_PER_DAY", "20"))
    SEND_DELAY: float = float(os.getenv("SEND_DELAY", "1.0"))

    # Режимы
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))

    def __post_init__(self):
        if not self.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN не задан! Укажите в .env или переменных окружения.")
        if not self.CHAT_ID:
            raise ValueError("CHAT_ID не задан! Укажите в .env или переменных окружения.")


config = Config()