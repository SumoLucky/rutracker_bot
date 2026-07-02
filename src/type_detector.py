# src/type_detector.py
import re
import logging
from typing import Optional

from models import TorrentEntry
from database import Database

logger = logging.getLogger(__name__)

# Эмодзи для типов
TYPE_EMOJI = {
    "фильм": "🎬",
    "сериал": "📺",
    "анимация": "🎞️",
    "книга": "📚",
    "аудиокнига": "🎧",
    "музыка": "🎵",
    "игра": "🎮",
    "софт": "💻",
    "другое": "📦",
}

# Приоритет типов (для разрешения конфликтов)
PRIORITY = [
    "аудиокнига",
    "анимация",
    "сериал",
    "фильм",
    "книга",
    "музыка",
    "игра",
    "софт",
]

FIELD_WEIGHTS = {
    "title": 3,
    "category": 2,
    "ai_category": 2,
    "summary": 1,
    "full_description": 1,
    "size": 1,
}

RULES = [
    (r"(?i)\bфильм\b", "фильм", 1),
    (r"(?i)\bкино\b", "фильм", 1),
    (r"(?i)\bmovie\b", "фильм", 1),
    (r"(?i)\bдокументальн\b", "фильм", 1),
    (r"\[\s*фильм\s*\]", "фильм", 2),
    (r"\[\s*movie\s*\]", "фильм", 2),

    (r"(?i)\bсериал\b", "сериал", 1),
    (r"(?i)\bсезон\s*\d+\b", "сериал", 2),
    (r"(?i)\bсерия\s*\d+\b", "сериал", 2),
    (r"(?i)\bэпизод\s*\d+\b", "сериал", 2),
    (r"(?i)\bseries\b", "сериал", 1),
    (r"(?i)\bseason\s*\d+\b", "сериал", 2),
    (r"(?i)\bepisode\s*\d+\b", "сериал", 2),
    (r"(?i)\bS\d+E\d+\b", "сериал", 3),
    (r"\[\s*сериал\s*\]", "сериал", 2),
    (r"\[\s*series\s*\]", "сериал", 2),

    (r"(?i)\bаниме\b", "анимация", 2),
    (r"(?i)\bмультфильм\b", "анимация", 2),
    (r"(?i)\bмультсериал\b", "анимация", 2),
    (r"(?i)\bанимаци[яи]\b", "анимация", 1),
    (r"(?i)\bмультик\b", "анимация", 1),
    (r"(?i)\banime\b", "анимация", 2),
    (r"(?i)\bмульт\b", "анимация", 1),
    (r"\[\s*аниме\s*\]", "анимация", 2),
    (r"\[\s*мультфильм\s*\]", "анимация", 2),

    (r"(?i)\bкниг[аи]\b", "книга", 1),
    (r"(?i)\bучебник\b", "книга", 1),
    (r"(?i)\bжурнал\b", "книга", 1),
    (r"(?i)\bpdf\b", "книга", 1),
    (r"(?i)\bfb2\b", "книга", 1),
    (r"(?i)\bepub\b", "книга", 1),
    (r"\[\s*книга\s*\]", "книга", 2),
    (r"\[\s*book\s*\]", "книга", 2),

    (r"(?i)\bаудиокниг[аи]\b", "аудиокнига", 2),
    (r"(?i)\bаудиоспектакл[ьъ]\b", "аудиокнига", 2),
    (r"\[\s*аудиокнига\s*\]", "аудиокнига", 2),
    (r"\[аудио\]", "аудиокнига", 1),

    (r"(?i)\bмузык[аи]\b", "музыка", 1),
    (r"(?i)\bальбом\b", "музыка", 1),
    (r"(?i)\bпесн[яи]\b", "музыка", 1),
    (r"(?i)\bmp3\b", "музыка", 1),
    (r"(?i)\bflac\b", "музыка", 1),
    (r"(?i)\bsoundtrack\b", "музыка", 1),
    (r"(?i)\bсаундтрек\b", "музыка", 1),
    (r"\[\s*музыка\s*\]", "музыка", 2),
    (r"\[\s*music\s*\]", "музыка", 2),

    (r"(?i)\bигр[аы]\b", "игра", 1),
    (r"(?i)\bgame\b", "игра", 1),
    (r"(?i)\bgaming\b", "игра", 1),
    (r"(?i)\bplaystation\b", "игра", 2),
    (r"(?i)\bxbox\b", "игра", 2),
    (r"(?i)\bnintendo\b", "игра", 2),
    (r"(?i)\bsteam\b", "игра", 1),
    (r"\[\s*игра\s*\]", "игра", 2),
    (r"\[dl\]", "игра", 1),
    (r"\[портабл\]", "игра", 1),

    (r"(?i)\bсофт\b", "софт", 1),
    (r"(?i)\bsoftware\b", "софт", 1),
    (r"(?i)\bпрограмм[аы]\b", "софт", 1),
    (r"(?i)\bутилит[аы]\b", "софт", 1),
    (r"(?i)\bдрайвер\b", "софт", 1),
    (r"\[\s*софт\s*\]", "софт", 2),
    (r"\[win\]", "софт", 1),
    (r"\[mac\]", "софт", 1),
    (r"\[linux\]", "софт", 1),
]

COMPILED_RULES = [(re.compile(pattern), content_type, weight) for pattern, content_type, weight in RULES]


def detect_content_type(entry: TorrentEntry) -> str:
    """Определяет тип контента на основе всех доступных полей."""
    texts = {
        "title": entry.title or "",
        "category": entry.category or "",
        "ai_category": entry.ai_category or "",
        "summary": entry.summary or "",
        "full_description": entry.full_description or "",
    }
    size_gb = entry.get_size_gb()

    scores = {t: 0 for t in TYPE_EMOJI.keys() if t != "другое"}

    for field, text in texts.items():
        if not text:
            continue
        weight = FIELD_WEIGHTS.get(field, 1)
        text_lower = text.lower()
        for compiled_pattern, content_type, rule_weight in COMPILED_RULES:
            if compiled_pattern.search(text_lower):
                scores[content_type] += weight * rule_weight

    if size_gb > 0:
        if size_gb > 1.5 and scores.get("фильм", 0) > 0:
            scores["фильм"] += 2
        elif size_gb < 0.05 and scores.get("книга", 0) > 0:
            scores["книга"] += 1

    ai_cat = entry.ai_category or ""
    if ai_cat:
        for content_type in TYPE_EMOJI.keys():
            if content_type != "другое" and content_type.lower() in ai_cat.lower():
                scores[content_type] += 5

    best_type = "другое"
    best_score = 0
    for t in PRIORITY:
        if t in scores and scores[t] > best_score:
            best_score = scores[t]
            best_type = t

    return best_type


def get_type_emoji(content_type: str) -> str:
    return TYPE_EMOJI.get(content_type, "📦")


class TypeDetector:
    """Заполняет поле content_type для записей, у которых оно отсутствует."""

    def __init__(self, db: Database):
        self.db = db

    def process_entries(self, limit: Optional[int] = None) -> int:
        """
        Обрабатывает записи без типа (content_type пустой или NULL).
        Возвращает количество успешно обработанных записей.
        """
        entries = self.db.get_entries_without_type(limit=limit)
        if not entries:
            logger.info("Нет записей для определения типа")
            return 0

        processed = 0
        for entry in entries:
            content_type = detect_content_type(entry)
            entry.content_type = content_type
            if self.db.save_entry(entry):
                processed += 1
                logger.info(f"Определён тип для {entry.rss_id}: {content_type}")
            else:
                logger.warning(f"Не удалось сохранить тип для {entry.rss_id}")

        logger.info(f"Определено типов: {processed}/{len(entries)}")
        return processed