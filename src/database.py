# src/database.py
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager

from config import config
from models import TorrentEntry

logger = logging.getLogger(__name__)


class Database:
    """Класс для работы с базой данных SQLite"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.DB_PATH
        self._init_db()
        logger.info(f"База данных инициализирована: {self.db_path}")

    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для соединения с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Включаем поддержку внешних ключей
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Создание таблиц и индексов"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS torrents (
                    rss_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    link TEXT NOT NULL,
                    updated TIMESTAMP,
                    summary TEXT,
                    author TEXT,
                    category_id TEXT,
                    category TEXT,
                    size TEXT,
                    seeds INTEGER DEFAULT 0,
                    leechers INTEGER DEFAULT 0,
                    downloads INTEGER DEFAULT 0,
                    full_description TEXT,
                    ai_analysis TEXT,
                    ai_retries INTEGER DEFAULT 0,
                    ai_last_error TEXT,
                    relevance_score REAL DEFAULT 0,
                    ai_summary TEXT,
                    recommendation TEXT,
                    ai_tags TEXT,
                    ai_category TEXT,
                    is_page_parsed BOOLEAN DEFAULT 0,
                    is_ai_analyzed BOOLEAN DEFAULT 0,
                    is_sent BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Индексы
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_updated ON torrents(updated DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON torrents(is_page_parsed, is_ai_analyzed, is_sent)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_relevance ON torrents(relevance_score DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON torrents(category)')

            # Таблица логов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processing_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rss_id TEXT,
                    stage TEXT,
                    status TEXT,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (rss_id) REFERENCES torrents(rss_id) ON DELETE CASCADE
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_log_rss_id ON processing_log(rss_id)')

            conn.commit()
            logger.info("Таблицы созданы/проверены")

    # ========== CRUD ==========

    def save_entry(self, entry: TorrentEntry) -> bool:
        try:
            data = entry.to_dict()
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO torrents (
                        rss_id, title, link, updated, summary, author,
                        category_id, category, size, seeds, leechers, downloads, full_description,
                        ai_analysis, ai_retries, ai_last_error, relevance_score, ai_summary, recommendation, ai_tags, ai_category,
                        is_page_parsed, is_ai_analyzed, is_sent,
                        created_at, updated_at
                    ) VALUES (
                        :rss_id, :title, :link, :updated, :summary, :author,
                        :category_id, :category, :size, :seeds, :leechers, :downloads, :full_description,
                        :ai_analysis, :ai_retries, :ai_last_error, :relevance_score, :ai_summary, :recommendation, :ai_tags, :ai_category,
                        :is_page_parsed, :is_ai_analyzed, :is_sent,
                        :created_at, :updated_at
                    )
                ''', data)
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка сохранения {entry.rss_id}: {e}")
            return False

    def get_entry(self, rss_id: str) -> Optional[TorrentEntry]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM torrents WHERE rss_id = ?', (rss_id,))
            row = cursor.fetchone()
            if row:
                return TorrentEntry.from_dict(dict(row))
            return None

    def entry_exists(self, rss_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM torrents WHERE rss_id = ?', (rss_id,))
            return cursor.fetchone() is not None

    def delete_entry(self, rss_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM processing_log WHERE rss_id = ?', (rss_id,))
            cursor.execute('DELETE FROM torrents WHERE rss_id = ?', (rss_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ========== Получение по статусам ==========

    def get_entries_by_status(
        self,
        page_parsed: Optional[bool] = None,
        ai_analyzed: Optional[bool] = None,
        sent: Optional[bool] = None,
        limit: Optional[int] = None,
        order_by: str = "updated DESC"
    ) -> List[TorrentEntry]:
        """Получение записей с фильтром по статусам"""
        # Безопасная проверка order_by
        allowed_orders = ["updated DESC", "updated ASC", "relevance_score DESC", "created_at DESC"]
        if order_by not in allowed_orders:
            order_by = "updated DESC"

        conditions = []
        params = []
        if page_parsed is not None:
            conditions.append("is_page_parsed = ?")
            params.append(1 if page_parsed else 0)
        if ai_analyzed is not None:
            conditions.append("is_ai_analyzed = ?")
            params.append(1 if ai_analyzed else 0)
        if sent is not None:
            conditions.append("is_sent = ?")
            params.append(1 if sent else 0)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT * FROM torrents {where} ORDER BY {order_by}"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [TorrentEntry.from_dict(dict(row)) for row in rows]

    def get_unparsed_entries(self, limit: Optional[int] = None) -> List[TorrentEntry]:
        return self.get_entries_by_status(page_parsed=False, ai_analyzed=False, sent=False, limit=limit)

    def get_unanalyzed_entries(self, limit: Optional[int] = None) -> List[TorrentEntry]:
        """Получение записей, которые спарсены, но не проанализированы ИИ"""
        return self.get_entries_by_status(page_parsed=True, ai_analyzed=False, sent=False, limit=limit)

    def get_ready_to_send(self, limit: Optional[int] = None) -> List[TorrentEntry]:
        return self.get_entries_by_status(page_parsed=True, ai_analyzed=True, sent=False, limit=limit)

    def get_ready_to_send_by_score(self, min_score: Optional[int] = None, limit: Optional[int] = None) -> List[TorrentEntry]:
        if min_score is None:
            min_score = config.MIN_RELEVANCE_SCORE
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = '''
                SELECT * FROM torrents 
                WHERE is_page_parsed = 1 AND is_ai_analyzed = 1 AND is_sent = 0
                  AND relevance_score >= ?
                ORDER BY relevance_score DESC, updated DESC
            '''
            params = [min_score]
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [TorrentEntry.from_dict(dict(row)) for row in rows]

    def get_recent_entries(self, hours: int = 24, limit: Optional[int] = None) -> List[TorrentEntry]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = '''
                SELECT * FROM torrents 
                WHERE updated > datetime('now', ?)
                ORDER BY updated DESC
            '''
            params = [f'-{hours} hours']
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [TorrentEntry.from_dict(dict(row)) for row in rows]

    # ========== Обновление статусов ==========

    def update_status(self, rss_id: str, page_parsed: Optional[bool] = None,
                      ai_analyzed: Optional[bool] = None, sent: Optional[bool] = None) -> bool:
        updates = []
        params = []
        if page_parsed is not None:
            updates.append("is_page_parsed = ?")
            params.append(1 if page_parsed else 0)
        if ai_analyzed is not None:
            updates.append("is_ai_analyzed = ?")
            params.append(1 if ai_analyzed else 0)
        if sent is not None:
            updates.append("is_sent = ?")
            params.append(1 if sent else 0)
        if not updates:
            return True
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(rss_id)
        query = f"UPDATE torrents SET {', '.join(updates)} WHERE rss_id = ?"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0

    def mark_as_parsed(self, rss_id: str) -> bool:
        return self.update_status(rss_id, page_parsed=True)
    def mark_as_analyzed(self, rss_id: str) -> bool:
        return self.update_status(rss_id, ai_analyzed=True)
    def mark_as_sent(self, rss_id: str) -> bool:
        return self.update_status(rss_id, sent=True)

    # ========== Логи ==========

    def log_processing(self, rss_id: str, stage: str, status: str, message: str = ""):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO processing_log (rss_id, stage, status, message)
                VALUES (?, ?, ?, ?)
            ''', (rss_id, stage, status, message))
            conn.commit()

    def get_logs(self, rss_id: str, limit: int = 20) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM processing_log WHERE rss_id = ?
                ORDER BY created_at DESC LIMIT ?
            ''', (rss_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def cleanup_logs(self, days: int = 30) -> int:
        """Очистка старых логов"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM processing_log
                WHERE created_at < datetime('now', ?)
            ''', (f'-{days} days',))
            conn.commit()
            deleted = cursor.rowcount
            logger.info(f"Удалено старых логов: {deleted}")
            return deleted

    # ========== Статистика ==========

    def get_stats(self) -> Dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_page_parsed = 1 THEN 1 ELSE 0 END) as parsed,
                    SUM(CASE WHEN is_ai_analyzed = 1 THEN 1 ELSE 0 END) as analyzed,
                    SUM(CASE WHEN is_sent = 1 THEN 1 ELSE 0 END) as sent,
                    AVG(relevance_score) as avg_score,
                    MAX(relevance_score) as max_score,
                    SUM(CASE WHEN relevance_score >= ? AND is_sent = 0 THEN 1 ELSE 0 END) as pending_high_score
                FROM torrents
            ''', (config.MIN_RELEVANCE_SCORE,))
            stats = dict(cursor.fetchone())

            cursor.execute('''
                SELECT category, COUNT(*) as count, AVG(relevance_score) as avg_score
                FROM torrents
                WHERE category != '' AND category IS NOT NULL
                GROUP BY category ORDER BY count DESC LIMIT 10
            ''')
            stats['top_categories'] = [dict(row) for row in cursor.fetchall()]

            cursor.execute('''
                SELECT COUNT(*) as new_today
                FROM torrents WHERE updated > datetime('now', '-1 day')
            ''')
            stats['new_today'] = cursor.fetchone()[0]

            cursor.execute('''
                SELECT 
                    SUM(CASE WHEN is_page_parsed = 0 THEN 1 ELSE 0 END) as pending_parse,
                    SUM(CASE WHEN is_page_parsed = 1 AND is_ai_analyzed = 0 THEN 1 ELSE 0 END) as pending_ai,
                    SUM(CASE WHEN is_ai_analyzed = 1 AND is_sent = 0 THEN 1 ELSE 0 END) as pending_send
                FROM torrents
            ''')
            pending = dict(cursor.fetchone())
            stats.update(pending)
            return stats

    # ========== Очистка ==========

    def cleanup_old_entries(self, days: int = 30) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM torrents 
                WHERE created_at < datetime('now', ?) AND is_sent = 1
            ''', (f'-{days} days',))
            conn.commit()
            deleted = cursor.rowcount
            logger.info(f"Удалено старых записей: {deleted}")
            return deleted

    def vacuum(self):
        with self.get_connection() as conn:
            conn.execute('VACUUM')
            logger.info("База данных оптимизирована")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = Database()
    print("База данных готова.")