# src/rss_parser.py
import feedparser
import logging
import time
import requests
from typing import List, Dict, Optional

from config import config
from models import TorrentEntry
from database import Database

logger = logging.getLogger(__name__)


class RSSParser:
    """Этап 1: Загрузка и парсинг RSS-ленты"""

    def __init__(self, db: Database):
        self.db = db
        self.rss_url = config.RSS_URL
        self.max_entries = config.RSS_MAX_ENTRIES
        self.timeout = config.RSS_TIMEOUT
        self.retries = config.RSS_RETRIES

    def fetch_feed(self, max_entries: Optional[int] = None) -> List[Dict]:
        if max_entries is None:
            max_entries = self.max_entries

        for attempt in range(1, self.retries + 1):
            try:
                logger.info(f"Загрузка RSS (попытка {attempt}/{self.retries}): {self.rss_url}")
                response = requests.get(self.rss_url, timeout=self.timeout)
                response.raise_for_status()
                feed = feedparser.parse(response.text)

                if feed.bozo:
                    logger.warning(f"Предупреждение парсинга: {feed.bozo_exception}")
                    if not feed.entries:
                        if attempt == self.retries:
                            return []
                        time.sleep(2 ** attempt)
                        continue

                entries = list(feed.entries[:max_entries])
                logger.info(f"Загружено {len(entries)} записей")
                return entries

            except Exception as e:
                logger.error(f"Ошибка загрузки RSS (попытка {attempt}): {e}")
                if attempt == self.retries:
                    logger.critical("Все попытки загрузки RSS провалились")
                    return []
                time.sleep(2 ** attempt)

        return []
    
    def process_new_entries(self, max_entries: Optional[int] = None) -> Dict[str, int]:
        """
        Обработка новых записей: загрузка, создание объектов, сохранение в БД.

        Returns:
            Словарь со статистикой:
            {
                'total_fetched': int,
                'already_exists': int,
                'saved': int,
                'errors': int
            }
        """
        raw_entries = self.fetch_feed(max_entries)
        stats = {
            'total_fetched': len(raw_entries),
            'already_exists': 0,
            'saved': 0,
            'errors': 0
        }

        for raw in raw_entries:
            try:
                entry = TorrentEntry.from_rss_entry(raw)
                rss_id = entry.rss_id

                if self.db.entry_exists(rss_id):
                    stats['already_exists'] += 1
                    continue

                if self.db.save_entry(entry):
                    stats['saved'] += 1
                    self.db.log_processing(
                        rss_id,
                        'rss_parser',
                        'success',
                        f'Новая запись: {entry.title[:50]}...'
                    )
                    logger.info(f"Добавлена запись: {entry.title[:50]}...")
                else:
                    stats['errors'] += 1
                    self.db.log_processing(
                        rss_id,
                        'rss_parser',
                        'error',
                        'Ошибка сохранения в БД'
                    )
            except Exception as e:
                stats['errors'] += 1
                rss_id = raw.get('id', 'unknown')
                logger.error(f"Ошибка обработки записи {rss_id}: {e}")
                self.db.log_processing(
                    rss_id,
                    'rss_parser',
                    'error',
                    str(e)
                )

        logger.info(
            f"Обработано RSS: всего={stats['total_fetched']}, "
            f"существовало={stats['already_exists']}, "
            f"сохранено={stats['saved']}, ошибок={stats['errors']}"
        )
        return stats