# src/page_parser.py
import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, Optional

import requests
from bs4 import BeautifulSoup

from config import config
from database import Database

logger = logging.getLogger(__name__)


class PageParser:
    """Этап 2: Парсинг страниц раздач с авторизацией и сохранением кук"""

    SELECTORS = {
        'category': 'td.nav a',
        'size': '#tor-size-humn',
        'seeds': 'span.seed b',
        'leechers': 'span.leech b',
        'downloads': 'td.borderless',
        'description': 'div.post_body',
    }

    COOKIE_FILE = Path("cookies.json")

    def __init__(self, db: Database):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.timeout = config.PARSING_TIMEOUT
        self.delay = config.PARSING_DELAY
        self.max_retries = config.PARSING_RETRIES

        # Пытаемся загрузить куки из файла
        if self._load_cookies():
            logger.info("Куки загружены из файла")
            if not self._is_cookie_valid():
                logger.warning("Куки невалидны, выполняем логин")
                self._login()
        else:
            logger.info("Файл с куками не найден или пуст, выполняем логин")
            self._login()

    def _save_cookies(self):
        """Сохраняет текущие куки в файл"""
        try:
            cookies = self.session.cookies.get_dict()
            with open(self.COOKIE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            logger.debug("Куки сохранены в файл")
        except Exception as e:
            logger.error(f"Ошибка сохранения кук: {e}")

    def _load_cookies(self) -> bool:
        """Загружает куки из файла и устанавливает в сессию"""
        try:
            if not self.COOKIE_FILE.exists():
                return False
            with open(self.COOKIE_FILE, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            self.session.cookies.update(cookies)
            return True
        except Exception as e:
            logger.error(f"Ошибка загрузки кук: {e}")
            return False

    def _is_cookie_valid(self) -> bool:
        """Проверяет, валидны ли текущие куки, запросом к главной странице"""
        try:
            response = self.session.get("https://rutracker.org/forum/index.php", timeout=self.timeout)
            if response.status_code == 200:
                if "login.php" in response.url or "Вход" in response.text:
                    return False
                return True
            return False
        except Exception:
            return False

    def _login(self) -> bool:
        """Выполняет логин, сохраняет куки"""
        login_url = "https://rutracker.org/forum/login.php"
        try:
            logger.info("Загрузка страницы логина...")
            response = self.session.get(login_url, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Ищем form_token
            form_token = None
            script_match = re.search(r'BB\.form_token\s*=\s*[\'"]([^\'"]+)[\'"]', response.text)
            if script_match:
                form_token = script_match.group(1)
            else:
                token_input = soup.find('input', {'name': 'form_token'})
                if token_input:
                    form_token = token_input.get('value')

            if not form_token:
                logger.warning("Не удалось найти form_token, попытка без него")
                form_token = ""

            login_data = {
                'login_username': config.RUTRACKER_USERNAME,
                'login_password': config.RUTRACKER_PASSWORD,
                'login': 'вход',
                'redirect': 'index.php',
                'form_token': form_token,
            }
            logger.info("Отправка логина...")
            response = self.session.post(login_url, data=login_data, timeout=self.timeout)
            response.raise_for_status()

            if 'bb_session' in self.session.cookies:
                logger.info("Авторизация успешна")
                self._save_cookies()
                return True
            else:
                if "неверное имя пользователя или пароль" in response.text.lower():
                    logger.error("Неверный логин или пароль")
                else:
                    logger.warning("Авторизация не подтверждена")
                return False

        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return False

    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Загружает страницу, при 403 или пустом ответе пытается перелогиниться"""
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"Загрузка страницы (попытка {attempt}/{self.max_retries}): {url}")
                response = self.session.get(url, timeout=self.timeout)

                if response.status_code == 403:
                    logger.warning("Получен 403, пытаемся перелогиниться...")
                    if self._login():
                        logger.info("Перелогин успешен, повторяем запрос")
                        response = self.session.get(url, timeout=self.timeout)
                        response.raise_for_status()
                    else:
                        logger.error("Перелогин не удался")
                        return None

                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                if not soup.find('body') or len(response.text) < 100:
                    logger.warning("Получена пустая страница, возможно, требуется логин")
                    if attempt == 1 and self._login():
                        logger.info("Перелогин выполнен, повторяем запрос")
                        continue
                    else:
                        logger.error("Страница пуста после логина")
                        return None

                return soup

            except requests.exceptions.RequestException as e:
                logger.warning(f"Ошибка загрузки (попытка {attempt}): {e}")
                if attempt == self.max_retries:
                    logger.error(f"Не удалось загрузить страницу после {self.max_retries} попыток: {url}")
                    return None
                time.sleep(2 ** attempt)

            except Exception as e:
                logger.error(f"Неожиданная ошибка при загрузке {url}: {e}")
                return None

        return None

    def parse_page(self, url: str) -> Dict:
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
            links = soup.select('td.nav a')
            if links:
                return links[-1].get_text(strip=True)
            return 'Неизвестно'
        except (AttributeError, ValueError):
            return 'Неизвестно'

    def _parse_size(self, soup: BeautifulSoup) -> str:
        try:
            size_elem = soup.select_one('#tor-size-humn')
            if size_elem:
                return size_elem.get_text(strip=True)
            attach = soup.find('fieldset', class_='attach')
            if attach:
                ul = attach.find('ul', class_='inlined')
                if ul:
                    lis = ul.find_all('li')
                    if len(lis) >= 2:
                        return lis[-1].get_text(strip=True)
            return 'Неизвестно'
        except (AttributeError, ValueError):
            return 'Неизвестно'

    def _parse_seeds(self, soup: BeautifulSoup) -> int:
        try:
            seed_elem = soup.select_one('span.seed b')
            if seed_elem:
                return int(seed_elem.get_text(strip=True))
            return 0
        except (AttributeError, ValueError):
            return 0

    def _parse_leechers(self, soup: BeautifulSoup) -> int:
        try:
            leech_elem = soup.select_one('span.leech b')
            if leech_elem:
                return int(leech_elem.get_text(strip=True))
            return 0
        except (AttributeError, ValueError):
            return 0

    def _parse_downloads(self, soup: BeautifulSoup) -> int:
        try:
            td = soup.find('td', class_='borderless', string=re.compile(r'скачан', re.I))
            if td:
                b = td.find('b')
                if b:
                    text = b.get_text(strip=True)
                    match = re.search(r'(\d+)', text)
                    if match:
                        return int(match.group(1))
            return 0
        except (AttributeError, ValueError):
            return 0

    def _parse_description(self, soup: BeautifulSoup) -> str:
        try:
            post = soup.select_one('div.post_body')
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
        if limit is None:
            limit = config.PARSING_LIMIT

        entries = self.db.get_unparsed_entries(limit)
        processed = 0

        for entry in entries:
            try:
                logger.info(f"Парсинг: {entry.title[:50]}...")
                page_data = self.parse_page(entry.link)

                if page_data:
                    entry.category = page_data.get('category', entry.category)
                    entry.size = page_data.get('size', entry.size)
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
                else:
                    entry.is_page_parsed = True
                    self.db.save_entry(entry)
                    self.db.log_processing(
                        entry.rss_id,
                        'page_parser',
                        'warning',
                        'Страница спарсена частично или пустая'
                    )

                time.sleep(self.delay)

            except Exception as e:
                logger.error(f"Ошибка обработки {entry.rss_id}: {e}")
                entry.is_page_parsed = True
                self.db.save_entry(entry)
                self.db.log_processing(entry.rss_id, 'page_parser', 'error', str(e))

        logger.info(f"Обработано парсингом: {processed}/{len(entries)}")
        return processed