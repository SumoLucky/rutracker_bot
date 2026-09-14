# src/page_parser.py
import logging
import re
import time
from typing import Dict, Optional, Any

import requests
from bs4 import BeautifulSoup

from config import config
from database import Database

logger = logging.getLogger(__name__)


class PageParser:
    """Этап 2: Парсинг страниц раздач через FlareSolverr (обход Cloudflare Challenge)"""

    SELECTORS = {
        'category_links': 'td.nav a',
        'size': '#tor-size-humn',
        'size_attach_ul': 'fieldset.attach ul.inlined',
        'seeds': 'span.seed b',
        'leechers': 'span.leech b',
        'downloads_td': 'td.borderless',
        'description': 'div.post_body',
    }

    def __init__(self, db: Database):
        self.db = db
        self.delay = config.PARSING_DELAY
        self.max_retries = config.PARSING_RETRIES
        self.flaresolverr_url = config.FLARESOLVERR_URL
        self.flaresolverr_timeout_ms = config.FLARESOLVERR_TIMEOUT_MS
        # Сессии временно отключены — FlareSolverr с сессией не справляется на этом IP
        # Работаем без сессий: каждый запрос = новый временный браузер
        logger.info("PageParser: сессии FlareSolverr отключены, работаем без них")

    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """
        Загружает страницу через FlareSolverr с повторными попытками.
        Работает без сессий: FlareSolverr создаёт временный браузер на каждый запрос.
        """
        request_timeout = (self.flaresolverr_timeout_ms / 1000) + 30

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"Загрузка через FlareSolverr (попытка {attempt}/{self.max_retries}): {url}")

                payload = {
                    "cmd": "request.get",
                    "url": url,
                    "maxTimeout": self.flaresolverr_timeout_ms,
                }

                response = requests.post(
                    self.flaresolverr_url,
                    json=payload,
                    timeout=request_timeout
                )
                data = response.json()

                if data.get("status") != "ok":
                    message = data.get("message", "")
                    logger.warning(f"FlareSolverr вернул ошибку: {message}")

                    if attempt == self.max_retries:
                        return None
                    time.sleep(2 ** attempt)
                    continue

                solution = data.get("solution") or {}
                status = solution.get("status", 0)
                html = solution.get("response", "")

                if status != 200:
                    logger.warning(f"FlareSolverr вернул статус {status} для {url}")
                    if attempt == self.max_retries:
                        return None
                    time.sleep(2 ** attempt)
                    continue

                soup = BeautifulSoup(html, 'html.parser')

                if not soup.find('body') or len(html) < 100:
                    logger.warning("Получена пустая страница")
                    if attempt == self.max_retries:
                        return None
                    time.sleep(2 ** attempt)
                    continue

                return soup

            except requests.exceptions.RequestException as e:
                logger.warning(f"Ошибка запроса к FlareSolverr (попытка {attempt}): {e}")
                if attempt == self.max_retries:
                    logger.error(f"Не удалось загрузить страницу после {self.max_retries} попыток: {url}")
                    return None
                time.sleep(2 ** attempt)

            except Exception as e:
                logger.error(f"Неожиданная ошибка при загрузке {url}: {e}", exc_info=True)
                return None

        return None

    def parse_page(self, url: str) -> Dict[str, Any]:
        """Парсит страницу раздачи и возвращает словарь с извлечёнными данными"""
        soup = self._fetch_page(url)
        if soup is None:
            return {}

        return {
            'category': self._parse_category(soup),
            'size': self._parse_size(soup),
            'seeds': self._parse_seeds(soup),
            'leechers': self._parse_leechers(soup),
            'downloads': self._parse_downloads(soup),
            'full_description': self._parse_description(soup),
        }

    def _parse_category(self, soup: BeautifulSoup) -> str:
        try:
            links = soup.select(self.SELECTORS['category_links'])
            if links:
                return links[-1].get_text(strip=True)
            return ''
        except (AttributeError, ValueError):
            return ''

    def _parse_size(self, soup: BeautifulSoup) -> str:
        try:
            size_elem = soup.select_one(self.SELECTORS['size'])
            if size_elem:
                return size_elem.get_text(strip=True)
            attach_ul = soup.select_one(self.SELECTORS['size_attach_ul'])
            if attach_ul:
                lis = attach_ul.find_all('li')
                if len(lis) >= 2:
                    return lis[-1].get_text(strip=True)
            return ''
        except (AttributeError, ValueError):
            return ''

    def _parse_seeds(self, soup: BeautifulSoup) -> int:
        try:
            seed_elem = soup.select_one(self.SELECTORS['seeds'])
            if seed_elem:
                m = re.search(r'\d+', seed_elem.get_text(strip=True))
                return int(m.group()) if m else 0
            return 0
        except (AttributeError, ValueError):
            return 0

    def _parse_leechers(self, soup: BeautifulSoup) -> int:
        try:
            leech_elem = soup.select_one(self.SELECTORS['leechers'])
            if leech_elem:
                m = re.search(r'\d+', leech_elem.get_text(strip=True))
                return int(m.group()) if m else 0
            return 0
        except (AttributeError, ValueError):
            return 0

    def _parse_downloads(self, soup: BeautifulSoup) -> int:
        try:
            for td in soup.select(self.SELECTORS['downloads_td']):
                text = td.get_text(' ', strip=True).lower()
                if 'скачан' in text:
                    b = td.find('b')
                    if b:
                        m = re.search(r'([\d\s]+)', b.get_text(strip=True))
                        if m:
                            return int(m.group(1).replace(' ', '').replace('\xa0', ''))
            return 0
        except (AttributeError, ValueError):
            return 0

    def _parse_description(self, soup: BeautifulSoup) -> str:
        try:
            post = soup.select_one(self.SELECTORS['description'])
            if post:
                for tag in post.find_all(['script', 'style']):
                    tag.decompose()
                text = post.get_text(separator=' ', strip=True)
                text = re.sub(r'\s+', ' ', text)
                return text[:5000]
            return ''
        except (AttributeError, ValueError):
            return ''

    def process_entries(self, limit: Optional[int] = None) -> int:
        """Обрабатывает непарсенные записи из БД"""
        if limit is None:
            limit = config.PARSING_LIMIT

        entries = self.db.get_unparsed_entries(limit)
        processed = 0

        for entry in entries:
            try:
                logger.info(f"Парсинг: {entry.title[:50]}...")
                page_data = self.parse_page(entry.link)

                # Если страница не загружена — увеличиваем счётчик попыток
                if not page_data:
                    entry.parse_attempts = (entry.parse_attempts or 0) + 1

                    if entry.parse_attempts >= config.PARSING_MAX_ATTEMPTS:
                        entry.is_page_parsed = True
                        logger.warning(
                            f"Пропускаем после {entry.parse_attempts} неудач: {entry.title[:40]}..."
                        )
                        self.db.log_processing(
                            entry.rss_id,
                            'page_parser',
                            'error',
                            f'Превышен лимит попыток парсинга ({entry.parse_attempts})'
                        )
                    else:
                        logger.info(
                            f"Неудача {entry.parse_attempts}/{config.PARSING_MAX_ATTEMPTS}: "
                            f"{entry.title[:40]}..."
                        )
                        self.db.log_processing(
                            entry.rss_id,
                            'page_parser',
                            'warning',
                            f'Неудача парсинга ({entry.parse_attempts}/{config.PARSING_MAX_ATTEMPTS})'
                        )

                    self.db.save_entry(entry)
                    continue

                # Обновляем только осмысленные строковые значения
                cat = page_data.get('category')
                if cat and cat != 'Неизвестно':
                    entry.category = cat

                size = page_data.get('size')
                if size and size != 'Неизвестно':
                    entry.size = size

                # Числовые значения перезаписываем всегда
                entry.seeds = page_data.get('seeds', 0)
                entry.leechers = page_data.get('leechers', 0)
                entry.downloads = page_data.get('downloads', 0)
                entry.full_description = page_data.get('full_description', '')

                entry.is_page_parsed = True

                if self.db.save_entry(entry):
                    processed += 1
                    self.db.log_processing(
                        entry.rss_id,
                        'page_parser',
                        'success',
                        f'Размер: {entry.size}, сиды: {entry.seeds}'
                    )
                    logger.info(f"✅ Парсинг успешен: {entry.title[:40]}...")
                else:
                    self.db.log_processing(
                        entry.rss_id,
                        'page_parser',
                        'error',
                        'Ошибка сохранения после парсинга'
                    )

            except Exception as e:
                logger.error(f"Ошибка обработки {entry.rss_id}: {e}", exc_info=True)
                self.db.log_processing(entry.rss_id, 'page_parser', 'error', str(e))

            finally:
                time.sleep(self.delay)

        logger.info(f"Успешно распарсено: {processed}/{len(entries)}")
        return processed