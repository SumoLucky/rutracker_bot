# src/orchestrator.py
import logging
import time
from typing import Optional, Dict
from datetime import datetime

from database import Database
from rss_parser import RSSParser
from page_parser import PageParser
from ai_analyzer import AIAnalyzer
from telegram_sender import TelegramSender
from config import config

logger = logging.getLogger(__name__)


class Orchestrator:
    """Оркестратор — управляет последовательным запуском всех этапов"""

    def __init__(self, db: Database):
        self.db = db
        self.rss_parser = RSSParser(db)
        self.page_parser = PageParser(db)
        self.ai_analyzer = AIAnalyzer(db)
        self.telegram_sender = TelegramSender(db)
        self.interval_minutes = config.CHECK_INTERVAL_MINUTES

    def _log_stats(self, stats: Dict):
        """Записывает статистику выполнения в отдельный файл"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open('stats.log', 'a', encoding='utf-8') as f:
                f.write(f"{timestamp} | "
                        f"RSS: fetched={stats['rss'].get('total_fetched', 0)}, "
                        f"new={stats['rss'].get('saved', 0)}, "
                        f"exists={stats['rss'].get('already_exists', 0)}, "
                        f"errors={stats['rss'].get('errors', 0)} | "
                        f"Page: processed={stats['page'].get('processed', 0)}, "
                        f"errors={stats['page'].get('errors', 0)} | "
                        f"AI: processed={stats['ai'].get('processed', 0)}, "
                        f"errors={stats['ai'].get('errors', 0)} | "
                        f"Telegram: sent={stats['telegram'].get('sent', 0)}, "
                        f"errors={stats['telegram'].get('errors', 0)}\n")
        except Exception as e:
            logger.warning(f"Не удалось записать статистику в файл: {e}")

    def run_once(self) -> Dict:
        """
        Выполняет один полный цикл обработки:
        1. Загрузка новых записей из RSS.
        2. Парсинг страниц для новых записей.
        3. ИИ-анализ новых записей.
        4. Отправка в Telegram записей с рейтингом >= порога.
        Возвращает словарь со статистикой по каждому этапу.
        """
        stats = {
            'rss': {'total_fetched': 0, 'already_exists': 0, 'saved': 0, 'errors': 0},
            'page': {'processed': 0, 'errors': 0},
            'ai': {'processed': 0, 'errors': 0},
            'telegram': {'sent': 0, 'errors': 0},
        }

        logger.info("=" * 50)
        logger.info("ЗАПУСК ОРКЕСТРАТОРА (ОДНОКРАТНЫЙ ПРОГОН)")
        logger.info("=" * 50)

        # 1. RSS
        try:
            rss_stats = self.rss_parser.process_new_entries()
            stats['rss']['total_fetched'] = rss_stats.get('total_fetched', 0)
            stats['rss']['already_exists'] = rss_stats.get('already_exists', 0)
            stats['rss']['saved'] = rss_stats.get('saved', 0)
            stats['rss']['errors'] = rss_stats.get('errors', 0)
            logger.info(f"✅ RSS: всего={rss_stats.get('total_fetched', 0)}, "
                        f"существовало={rss_stats.get('already_exists', 0)}, "
                        f"сохранено={rss_stats.get('saved', 0)}, "
                        f"ошибок={rss_stats.get('errors', 0)}")
        except Exception as e:
            logger.error(f"Ошибка этапа RSS: {e}")
            stats['rss']['errors'] += 1

        # 2. Парсинг страниц
        try:
            page_processed = self.page_parser.process_entries()
            stats['page']['processed'] = page_processed
            logger.info(f"✅ Парсинг страниц: обработано {page_processed}")
        except Exception as e:
            logger.error(f"Ошибка этапа парсинга страниц: {e}")
            stats['page']['errors'] += 1

        # 3. ИИ-анализ (с проверкой ключа)
        if not config.DEEPSEEK_API_KEY:
            logger.warning("⚠️ DEEPSEEK_API_KEY не задан, этап ИИ-анализа пропущен")
        else:
            try:
                ai_processed = self.ai_analyzer.process_entries()
                stats['ai']['processed'] = ai_processed
                logger.info(f"✅ ИИ-анализ: обработано {ai_processed}")
            except Exception as e:
                logger.error(f"Ошибка этапа ИИ-анализа: {e}")
                stats['ai']['errors'] += 1

        # 4. Отправка в Telegram
        try:
            sent = self.telegram_sender.send_entries()
            stats['telegram']['sent'] = sent
            logger.info(f"✅ Отправка в Telegram: отправлено {sent}")
        except Exception as e:
            logger.error(f"Ошибка этапа отправки в Telegram: {e}")
            stats['telegram']['errors'] += 1

        # Общая статистика БД
        db_stats = self.db.get_stats()
        logger.info(f"📊 Статистика БД: всего={db_stats.get('total', 0)}, "
                    f"спарсено={db_stats.get('parsed', 0)}, "
                    f"проанализировано={db_stats.get('analyzed', 0)}, "
                    f"отправлено={db_stats.get('sent', 0)}")

        # Запись статистики в файл
        self._log_stats(stats)

        logger.info("=" * 50)
        logger.info("ПРОГОН ЗАВЕРШЁН")
        logger.info("=" * 50)

        return stats

    def run_forever(self):
        """
        Запускает бесконечный цикл с интервалом CHECK_INTERVAL_MINUTES.
        """
        logger.info(f"🔄 Оркестратор запущен в бесконечном режиме. "
                    f"Интервал: {self.interval_minutes} минут.")
        while True:
            try:
                self.run_once()
                logger.info(f"⏳ Ожидание {self.interval_minutes} минут до следующего запуска...")
                time.sleep(self.interval_minutes * 60)
            except KeyboardInterrupt:
                logger.info("Остановка оркестратора по запросу пользователя (Ctrl+C)")
                break
            except Exception as e:
                logger.error(f"Критическая ошибка в основном цикле: {e}")
                logger.info(f"Повторная попытка через {self.interval_minutes} минут...")
                time.sleep(self.interval_minutes * 60)