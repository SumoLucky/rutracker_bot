# src/models.py
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
import json
import re
import calendar
import html


@dataclass
class TorrentEntry:
    """Модель данных раздачи Rutracker (адаптирована под структуру RSS)"""

    # === RSS данные (обязательные) ===
    rss_id: str
    title: str
    link: str
    updated: datetime
    summary: str
    author: str

    # === Категория из RSS ===
    category_id: str = ""
    category: str = ""

    # === Данные с парсинга страницы (заполняются позже) ===
    size: str = ""
    seeds: int = 0
    leechers: int = 0
    downloads: int = 0
    full_description: str = ""

    # === Данные ИИ-анализа ===
    ai_analysis: Dict = None
    relevance_score: float = 0.0
    ai_summary: str = ""
    recommendation: str = "unknown"
    ai_tags: List[str] = None

    # === Статусы обработки ===
    is_page_parsed: bool = False
    is_ai_analyzed: bool = False
    is_sent: bool = False

    # === Служебные поля ===
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            # naive UTC (без зоны)
            self.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if self.ai_analysis is None:
            self.ai_analysis = {}
        if self.ai_tags is None:
            self.ai_tags = []

    def to_dict(self) -> Dict:
        data = asdict(self)
        for key in ['updated', 'created_at', 'updated_at']:
            if data.get(key) and isinstance(data[key], datetime):
                data[key] = data[key].isoformat()
        if isinstance(data.get('ai_analysis'), dict):
            data['ai_analysis'] = json.dumps(data['ai_analysis'], ensure_ascii=False)
        if isinstance(data.get('ai_tags'), list):
            data['ai_tags'] = json.dumps(data['ai_tags'], ensure_ascii=False)
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'TorrentEntry':
        clean_data = data.copy()
        for key in ['updated', 'created_at', 'updated_at']:
            if clean_data.get(key) and isinstance(clean_data[key], str):
                try:
                    clean_data[key] = datetime.fromisoformat(clean_data[key])
                except ValueError:
                    try:
                        clean_data[key] = datetime.strptime(clean_data[key], '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        clean_data[key] = datetime.now(timezone.utc).replace(tzinfo=None)
        if clean_data.get('ai_analysis') and isinstance(clean_data['ai_analysis'], str):
            try:
                clean_data['ai_analysis'] = json.loads(clean_data['ai_analysis'])
            except:
                clean_data['ai_analysis'] = {}
        if clean_data.get('ai_tags') and isinstance(clean_data['ai_tags'], str):
            try:
                clean_data['ai_tags'] = json.loads(clean_data['ai_tags'])
            except:
                clean_data['ai_tags'] = []
        return cls(**clean_data)

    @classmethod
    def from_rss_entry(cls, raw_entry: Dict[str, Any]) -> 'TorrentEntry':
        """
        Создание объекта TorrentEntry из сырых данных RSS (feedparser).
        Выполняет полную нормализацию данных.
        """
        # --- ID ---
        rss_id = raw_entry.get('id', '')
        if not rss_id:
            link = raw_entry.get('link', '')
            if link:
                match = re.search(r't=(\d+)', link)
                if match:
                    rss_id = f"generated:{match.group(1)}"
                else:
                    rss_id = f"generated:{hash(link)}"
            else:
                rss_id = f"generated:{calendar.timegm(datetime.now(timezone.utc).utctimetuple())}"

        # --- Дата (используем calendar.timegm для корректного UTC) ---
        if hasattr(raw_entry, 'updated_parsed') and raw_entry.updated_parsed:
            updated_dt = datetime.fromtimestamp(
                calendar.timegm(raw_entry.updated_parsed),
                tz=timezone.utc
            ).replace(tzinfo=None)
        elif hasattr(raw_entry, 'published_parsed') and raw_entry.published_parsed:
            updated_dt = datetime.fromtimestamp(
                calendar.timegm(raw_entry.published_parsed),
                tz=timezone.utc
            ).replace(tzinfo=None)
        else:
            updated_dt = datetime.now(timezone.utc).replace(tzinfo=None)

        # --- Автор ---
        author_data = raw_entry.get('author', '')
        if isinstance(author_data, dict):
            author = author_data.get('name', 'Неизвестно')
        else:
            author = str(author_data) if author_data else 'Неизвестно'

        # --- Категория ---
        category_data = raw_entry.get('category', {})
        category_id = ''
        category_label = ''
        if isinstance(category_data, dict):
            category_id = category_data.get('term', '')
            category_label = category_data.get('label', '')
        elif isinstance(category_data, str):
            category_label = category_data

        # --- Описание (очистка HTML и сущностей) ---
        summary = raw_entry.get('summary', '')
        if summary:
            summary = re.sub(r'<[^>]+>', '', summary)
            summary = html.unescape(summary)
            if len(summary) > 1000:
                summary = summary[:1000] + '...'

        return cls(
            rss_id=rss_id,
            title=raw_entry.get('title', 'Без названия'),
            link=raw_entry.get('link', ''),
            updated=updated_dt,
            summary=summary,
            author=author,
            category_id=category_id,
            category=category_label
        )

    def get_short_info(self) -> str:
        return f"{self.title[:50]}... (категория: {self.category or self.category_id}, оценка: {self.relevance_score})"

    def get_size_gb(self) -> float:
        if not self.size:
            return 0.0
        try:
            match = re.search(r'(\d+\.?\d*)\s*(TB|GB|MB|KB|ГБ|МБ|КБ)', self.size, re.I)
            if match:
                value = float(match.group(1))
                unit = match.group(2).upper()
                multipliers = {
                    'KB': 1 / (1024 * 1024), 'MB': 1 / 1024, 'GB': 1, 'TB': 1024,
                    'КБ': 1 / (1024 * 1024), 'МБ': 1 / 1024, 'ГБ': 1,
                }
                return value * multipliers.get(unit, 1)
        except:
            pass
        return 0.0