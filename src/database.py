# src/database.py
import logging
from typing import List, Dict, Optional
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from config import config
from models import TorrentEntry

logger = logging.getLogger(__name__)


class Database:
    """Работа с PostgreSQL"""

    def __init__(self):
        self.database_url = config.DATABASE_URL
        if not self.database_url:
            raise ValueError("DATABASE_URL не задан!")
        self._init_db()

    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для соединения с БД"""
        conn = psycopg2.connect(self.database_url)
        conn.autocommit = False
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Создание таблиц и индексов"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
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
                        relevance_score REAL DEFAULT 0,
                        ai_summary TEXT,
                        recommendation TEXT,
                        ai_tags TEXT,
                        ai_category TEXT,
                        is_page_parsed BOOLEAN DEFAULT FALSE,
                        is_ai_analyzed BOOLEAN DEFAULT FALSE,
                        is_sent BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cur.execute("CREATE INDEX IF NOT EXISTS idx_updated ON torrents(updated DESC)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_status ON torrents(is_page_parsed, is_ai_analyzed, is_sent)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_relevance ON torrents(relevance_score DESC)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_category ON torrents(category)")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS processing_log (
                        id SERIAL PRIMARY KEY,
                        rss_id TEXT,
                        stage TEXT,
                        status TEXT,
                        message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (rss_id) REFERENCES torrents(rss_id) ON DELETE CASCADE
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_log_rss_id ON processing_log(rss_id)")

                conn.commit()
                logger.info("Таблицы созданы/проверены (PostgreSQL)")

    # ========== CRUD ==========

    def save_entry(self, entry: TorrentEntry) -> bool:
        try:
            data = entry.to_dict()
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO torrents (
                            rss_id, title, link, updated, summary, author,
                            category_id, category, size, seeds, leechers, downloads, full_description,
                            ai_analysis, relevance_score, ai_summary, recommendation, ai_tags, ai_category,
                            is_page_parsed, is_ai_analyzed, is_sent,
                            created_at, updated_at
                        ) VALUES (
                            %(rss_id)s, %(title)s, %(link)s, %(updated)s, %(summary)s, %(author)s,
                            %(category_id)s, %(category)s, %(size)s, %(seeds)s, %(leechers)s, %(downloads)s, %(full_description)s,
                            %(ai_analysis)s, %(relevance_score)s, %(ai_summary)s, %(recommendation)s, %(ai_tags)s, %(ai_category)s,
                            %(is_page_parsed)s, %(is_ai_analyzed)s, %(is_sent)s,
                            %(created_at)s, %(updated_at)s
                        )
                        ON CONFLICT (rss_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            link = EXCLUDED.link,
                            updated = EXCLUDED.updated,
                            summary = EXCLUDED.summary,
                            author = EXCLUDED.author,
                            category_id = EXCLUDED.category_id,
                            category = EXCLUDED.category,
                            size = EXCLUDED.size,
                            seeds = EXCLUDED.seeds,
                            leechers = EXCLUDED.leechers,
                            downloads = EXCLUDED.downloads,
                            full_description = EXCLUDED.full_description,
                            ai_analysis = EXCLUDED.ai_analysis,
                            relevance_score = EXCLUDED.relevance_score,
                            ai_summary = EXCLUDED.ai_summary,
                            recommendation = EXCLUDED.recommendation,
                            ai_tags = EXCLUDED.ai_tags,
                            ai_category = EXCLUDED.ai_category,
                            is_page_parsed = EXCLUDED.is_page_parsed,
                            is_ai_analyzed = EXCLUDED.is_ai_analyzed,
                            is_sent = EXCLUDED.is_sent,
                            updated_at = CURRENT_TIMESTAMP
                    """, data)
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Ошибка сохранения {entry.rss_id}: {e}")
            return False

    def get_entry(self, rss_id: str) -> Optional[TorrentEntry]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM torrents WHERE rss_id = %s", (rss_id,))
                row = cur.fetchone()
                if row:
                    return TorrentEntry.from_dict(dict(row))
                return None

    def entry_exists(self, rss_id: str) -> bool:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM torrents WHERE rss_id = %s", (rss_id,))
                return cur.fetchone() is not None

    def delete_entry(self, rss_id: str) -> bool:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM processing_log WHERE rss_id = %s", (rss_id,))
                cur.execute("DELETE FROM torrents WHERE rss_id = %s", (rss_id,))
                conn.commit()
                return cur.rowcount > 0

    # ========== Получение по статусам ==========

    def get_entries_by_status(
        self,
        page_parsed: Optional[bool] = None,
        ai_analyzed: Optional[bool] = None,
        sent: Optional[bool] = None,
        limit: Optional[int] = None,
        order_by: str = "updated DESC"
    ) -> List[TorrentEntry]:
        allowed_orders = ["updated DESC", "updated ASC", "relevance_score DESC", "created_at DESC"]
        if order_by not in allowed_orders:
            order_by = "updated DESC"

        conditions = []
        params = []
        if page_parsed is not None:
            conditions.append("is_page_parsed = %s")
            params.append(page_parsed)
        if ai_analyzed is not None:
            conditions.append("is_ai_analyzed = %s")
            params.append(ai_analyzed)
        if sent is not None:
            conditions.append("is_sent = %s")
            params.append(sent)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT * FROM torrents {where} ORDER BY {order_by}"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
                return [TorrentEntry.from_dict(dict(row)) for row in rows]

    def get_unparsed_entries(self, limit: Optional[int] = None) -> List[TorrentEntry]:
        return self.get_entries_by_status(page_parsed=False, ai_analyzed=False, sent=False, limit=limit)

    def get_unanalyzed_entries(self, limit: Optional[int] = None) -> List[TorrentEntry]:
        return self.get_entries_by_status(page_parsed=True, ai_analyzed=False, sent=False, limit=limit)

    def get_ready_to_send(self, limit: Optional[int] = None) -> List[TorrentEntry]:
        return self.get_entries_by_status(page_parsed=True, ai_analyzed=True, sent=False, limit=limit)

    def get_ready_to_send_by_score(self, min_score: Optional[int] = None, limit: Optional[int] = None) -> List[TorrentEntry]:
        if min_score is None:
            min_score = config.MIN_RELEVANCE_SCORE
        query = """
            SELECT * FROM torrents
            WHERE is_page_parsed = TRUE AND is_ai_analyzed = TRUE AND is_sent = FALSE
              AND relevance_score >= %s
            ORDER BY relevance_score DESC, updated DESC
        """
        params = [min_score]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
                return [TorrentEntry.from_dict(dict(row)) for row in rows]

    def get_recent_entries(self, hours: int = 24, limit: Optional[int] = None) -> List[TorrentEntry]:
        query = """
            SELECT * FROM torrents
            WHERE updated > NOW() - INTERVAL %s HOUR
            ORDER BY updated DESC
        """
        params = [hours]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
                return [TorrentEntry.from_dict(dict(row)) for row in rows]

    # ========== Обновление статусов ==========

    def update_status(self, rss_id: str, page_parsed: Optional[bool] = None,
                      ai_analyzed: Optional[bool] = None, sent: Optional[bool] = None) -> bool:
        updates = []
        params = []
        if page_parsed is not None:
            updates.append("is_page_parsed = %s")
            params.append(page_parsed)
        if ai_analyzed is not None:
            updates.append("is_ai_analyzed = %s")
            params.append(ai_analyzed)
        if sent is not None:
            updates.append("is_sent = %s")
            params.append(sent)
        if not updates:
            return True
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(rss_id)
        query = f"UPDATE torrents SET {', '.join(updates)} WHERE rss_id = %s"
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                conn.commit()
                return cur.rowcount > 0

    def mark_as_parsed(self, rss_id: str) -> bool:
        return self.update_status(rss_id, page_parsed=True)

    def mark_as_analyzed(self, rss_id: str) -> bool:
        return self.update_status(rss_id, ai_analyzed=True)

    def mark_as_sent(self, rss_id: str) -> bool:
        return self.update_status(rss_id, sent=True)

    # ========== Логи ==========

    def log_processing(self, rss_id: str, stage: str, status: str, message: str = ""):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO processing_log (rss_id, stage, status, message)
                    VALUES (%s, %s, %s, %s)
                """, (rss_id, stage, status, message))
                conn.commit()

    def get_logs(self, rss_id: str, limit: int = 20) -> List[Dict]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM processing_log
                    WHERE rss_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (rss_id, limit))
                return [dict(row) for row in cur.fetchall()]

    def cleanup_logs(self, days: int = 30) -> int:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM processing_log
                    WHERE created_at < NOW() - INTERVAL %s DAY
                """, (days,))
                conn.commit()
                return cur.rowcount

    # ========== Статистика ==========

    def get_stats(self) -> Dict:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN is_page_parsed THEN 1 ELSE 0 END) as parsed,
                        SUM(CASE WHEN is_ai_analyzed THEN 1 ELSE 0 END) as analyzed,
                        SUM(CASE WHEN is_sent THEN 1 ELSE 0 END) as sent,
                        AVG(relevance_score) as avg_score,
                        MAX(relevance_score) as max_score,
                        SUM(CASE WHEN relevance_score >= %s AND NOT is_sent THEN 1 ELSE 0 END) as pending_high_score
                    FROM torrents
                """, (config.MIN_RELEVANCE_SCORE,))
                stats = dict(cur.fetchone())

                cur.execute("""
                    SELECT category, COUNT(*) as count, AVG(relevance_score) as avg_score
                    FROM torrents
                    WHERE category != '' AND category IS NOT NULL
                    GROUP BY category
                    ORDER BY count DESC
                    LIMIT 10
                """)
                stats['top_categories'] = [dict(row) for row in cur.fetchall()]

                cur.execute("""
                    SELECT COUNT(*) as new_today
                    FROM torrents
                    WHERE updated > NOW() - INTERVAL '1 day'
                """)
                row = cur.fetchone()
                stats['new_today'] = row['new_today'] if row else 0

                cur.execute("""
                    SELECT
                        SUM(CASE WHEN NOT is_page_parsed THEN 1 ELSE 0 END) as pending_parse,
                        SUM(CASE WHEN is_page_parsed AND NOT is_ai_analyzed THEN 1 ELSE 0 END) as pending_ai,
                        SUM(CASE WHEN is_ai_analyzed AND NOT is_sent THEN 1 ELSE 0 END) as pending_send
                    FROM torrents
                """)
                pending = dict(cur.fetchone())
                stats.update(pending)
                return stats

    # ========== Очистка ==========

    def cleanup_old_entries(self, days: int = 30) -> int:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM torrents
                    WHERE created_at < NOW() - INTERVAL %s DAY AND is_sent = TRUE
                """, (days,))
                conn.commit()
                return cur.rowcount

    def vacuum(self):
        """Обновление статистики планировщика PostgreSQL"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("ANALYZE")
                conn.commit()
                logger.info("Статистика БД обновлена (ANALYZE)")