# tests/test_type_detector.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import TorrentEntry
from type_detector import detect_content_type
from datetime import datetime, timezone

def test_detector():
    # Тестовая запись: фильм
    entry = TorrentEntry(
        rss_id="test1",
        title="Аватар 2 (2025) 4K",
        link="",
        updated=datetime.now(timezone.utc).replace(tzinfo=None),
        summary="Научно-фантастический фильм",
        author="test",
        category="Фильмы",
        full_description="Фильм про синих существ",
        size="10.5 GB"
    )
    assert detect_content_type(entry) == "фильм"

    # Тестовая запись: сериал
    entry2 = TorrentEntry(
        rss_id="test2",
        title="Игра престолов S01E01",
        link="",
        updated=datetime.now(timezone.utc).replace(tzinfo=None),
        summary="Первый эпизод сериала",
        author="test",
        category="Сериалы",
        full_description="Сериал по мотивам книг",
        size="3.2 GB"
    )
    assert detect_content_type(entry2) == "сериал"

    # Тестовая запись: аниме
    entry3 = TorrentEntry(
        rss_id="test3",
        title="Наруто [аниме]",
        link="",
        updated=datetime.now(timezone.utc).replace(tzinfo=None),
        summary="",
        author="test",
        category="Аниме",
        full_description="Японское аниме",
        size="5 GB"
    )
    assert detect_content_type(entry3) == "анимация"

    print("Все тесты детектора пройдены!")

if __name__ == "__main__":
    test_detector()