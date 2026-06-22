# src/models.py
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, List
import json
import re


@dataclass
class TorrentEntry:
    """Модель данных раздачи Rutracker (адаптирована под реальную структуру RSS)"""

    # === RSS данные (обязательные) ===
    rss_id: str  # tag:rto.feed,2026-06-22:/t/6873886
    title: str  # Название раздачи
    link: str  # Ссылка на страницу
    updated: datetime  # Дата обновления (из RSS)
    summary: str  # Краткое описание (может быть с HTML)
    author: str  # Автор раздачи

    # === Категория из RSS ===
    category_id: str = ""  # f-2436 (term)
    category: str = ""  # Эпоха СССР (label)

    # === Данные с парсинга страницы (заполняются позже) ===
    size: str = ""  # 14.8 MB
    seeds: int = 0
    leechers: int = 0
    downloads: int = 0
    full_description: str = ""  # Полное описание со страницы

    # === Данные ИИ-анализа ===
    ai_analysis: Dict = None  # Полный JSON-ответ ИИ
    relevance_score: float = 0.0  # 0-100
    ai_summary: str = ""  # Краткое описание от ИИ
    recommendation: str = "unknown"  # download | maybe | skip
    ai_tags: List[str] = None  # Теги от ИИ

    # === Статусы обработки ===
    is_page_parsed: bool = False
    is_ai_analyzed: bool = False
    is_sent: bool = False

    # === Служебные поля ===
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        """Инициализация после создания"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.ai_analysis is None:
            self.ai_analysis = {}
        if self.ai_tags is None:
            self.ai_tags = []

    def to_dict(self) -> Dict:
        """Преобразование объекта в словарь для сохранения в БД"""
        data = asdict(self)

        # Преобразуем datetime в ISO-строки
        for key in ['updated', 'created_at', 'updated_at']:
            if data.get(key) and isinstance(data[key], datetime):
                data[key] = data[key].isoformat()

        # Преобразуем словарь ai_analysis в JSON-строку
        if isinstance(data.get('ai_analysis'), dict):
            data['ai_analysis'] = json.dumps(data['ai_analysis'], ensure_ascii=False)
        # Преобразуем список ai_tags в JSON-строку
        if isinstance(data.get('ai_tags'), list):
            data['ai_tags'] = json.dumps(data['ai_tags'], ensure_ascii=False)
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'TorrentEntry':
        """Создание объекта из словаря (из БД)"""
        clean_data = data.copy()

        # Восстанавливаем datetime из ISO-строк
        for key in ['updated', 'created_at', 'updated_at']:
            if clean_data.get(key) and isinstance(clean_data[key], str):
                try:
                    clean_data[key] = datetime.fromisoformat(clean_data[key])
                except ValueError:
                    try:
                        clean_data[key] = datetime.strptime(clean_data[key], '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        clean_data[key] = datetime.now()

        # Восстанавливаем ai_analysis из JSON-строки
        if clean_data.get('ai_analysis') and isinstance(clean_data['ai_analysis'], str):
            try:
                clean_data['ai_analysis'] = json.loads(clean_data['ai_analysis'])
            except json.JSONDecodeError:
                clean_data['ai_analysis'] = {}

        # Восстанавливаем ai_tags из JSON-строки
        if clean_data.get('ai_tags') and isinstance(clean_data['ai_tags'], str):
            try:
                clean_data['ai_tags'] = json.loads(clean_data['ai_tags'])
            except json.JSONDecodeError:
                clean_data['ai_tags'] = []

        return cls(**clean_data)

    @classmethod
    def from_rss_entry(cls, rss_entry: Dict) -> 'TorrentEntry':
        """Создание объекта из сырых данных RSS"""
        # Извлекаем категорию
        category_id = ""
        category_label = ""
        if 'category' in rss_entry:
            if isinstance(rss_entry['category'], dict):
                category_id = rss_entry['category'].get('term', '')
                category_label = rss_entry['category'].get('label', '')
            elif isinstance(rss_entry['category'], str):
                category_label = rss_entry['category']

        # Очищаем summary от HTML (опционально)
        summary = rss_entry.get('summary', '')
        if summary:
            # Простая очистка от HTML-тегов
            summary = re.sub(r'<[^>]+>', '', summary)
            # Ограничиваем длину
            if len(summary) > 1000:
                summary = summary[:1000] + '...'

        return cls(
            rss_id=rss_entry.get('id', ''),
            title=rss_entry.get('title', 'Без названия'),
            link=rss_entry.get('link', ''),
            updated=rss_entry.get('updated', datetime.now()),
            summary=summary,
            author=rss_entry.get('author', {}).get('name', 'Неизвестно') if isinstance(rss_entry.get('author'),
                                                                                       dict) else rss_entry.get(
                'author', 'Неизвестно'),
            category_id=category_id,
            category=category_label
        )

    def get_short_info(self) -> str:
        """Краткая информация о раздаче для логов"""
        return f"{self.title[:50]}... (категория: {self.category or self.category_id}, оценка: {self.relevance_score})"

    def get_size_gb(self) -> float:
        """Получение размера в гигабайтах (для фильтрации)"""
        if not self.size:
            return 0.0
        try:
            # Парсим строку вида "14.8 MB", "1.23 GB" и т.д.
            match = re.search(r'(\d+\.?\d*)\s*(TB|GB|MB|KB|ГБ|МБ|КБ)', self.size, re.I)
            if match:
                value = float(match.group(1))
                unit = match.group(2).upper()
                multipliers = {
                    'KB': 1 / (1024 * 1024),
                    'MB': 1 / 1024,
                    'GB': 1,
                    'TB': 1024,
                    'КБ': 1 / (1024 * 1024),
                    'МБ': 1 / 1024,
                    'ГБ': 1,
                }
                return value * multipliers.get(unit, 1)
        except:
            pass
        return 0.0