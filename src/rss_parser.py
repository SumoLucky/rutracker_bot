# src/rss_parser.py
import feedparser
import logging
import time
import os
from datetime import datetime
from typing import List, Dict, Optional

import requests

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
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    def _log_raw_entries(self, entries: List[Dict], source: str = "rss"):
        """Сохраняет сырые RSS-записи в файл для отладки"""
        if not config.DEBUG:
            return
        log_file = "rss_feed.log"
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            max_lines = 200

            lines = []
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

            new_entries = []
            for entry in entries:
                new_entries.append(f"[{timestamp}] Source: {source}\n")
                new_entries.append(f"ID: {entry.get('id', 'N/A')}\n")
                new_entries.append(f"Title: {entry.get('title', 'N/A')}\n")
                new_entries.append(f"Link: {entry.get('link', 'N/A')}\n")
                new_entries.append(f"Category: {entry.get('category', 'N/A')}\n")
                new_entries.append("-"*60 + "\n")

            all_lines = lines + new_entries
            separator = "-"*60 + "\n"
            parts = ''.join(all_lines).split(separator)
            if len(parts) > max_lines:
                parts = parts[-max_lines:]

            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(separator.join(parts))
                if parts:
                    f.write(separator)

        except Exception as e:
            logger.warning(f"Не удалось записать RSS в лог: {e}")

    def fetch_feed(self, max_entries: Optional[int] = None) -> List[Dict]:
        """Загрузка RSS с повторными попытками"""
        if max_entries is None:
            max_entries = self.max_entries

        for attempt in range(1, self.retries + 1):
            try:
                logger.info(f"Загрузка RSS (попытка {attempt}/{self.retries}): {self.rss_url}")
                response = self.session.get(self.rss_url, timeout=self.timeout)
                response.raise_for_status()
                feed = feedparser.parse(response.text)

                if feed.bozo:
                    logger.warning(f"Предупреждение парсинга: {feed.bozo_exception}")

                if not hasattr(feed, 'entries') or not isinstance(feed.entries, list):
                    logger.warning("Нет записей в RSS ленте или поле entries отсутствует")
                    if attempt == self.retries:
                        return []
                    time.sleep(2 ** attempt)
                    continue

                entries = list(feed.entries[:max_entries])
                logger.info(f"Загружено {len(entries)} записей")
                self._log_raw_entries(entries, source="rss")
                return entries

            except Exception as e:
                logger.error(f"Ошибка загрузки RSS (попытка {attempt}): {e}")
                if attempt == self.retries:
                    logger.critical("Все попытки загрузки RSS провалились")
                    return []
                time.sleep(2 ** attempt)

        return []

    def process_new_entries(self, max_entries: Optional[int] = None) -> Dict[str, int]:
        """Обработка новых записей"""
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