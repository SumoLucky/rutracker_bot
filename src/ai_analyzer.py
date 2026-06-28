# src/ai_analyzer.py
import logging
import re
import json
from typing import Dict, Optional

from openai import OpenAI

from config import config
from database import Database
from models import TorrentEntry

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """Этап 3: ИИ-анализ записей с помощью DeepSeek API (OpenAI SDK)"""

    def __init__(self, db: Database):
        self.db = db
        self.api_key = config.DEEPSEEK_API_KEY
        self.model = config.DEEPSEEK_MODEL
        self.max_tokens = config.DEEPSEEK_MAX_TOKENS
        self.temperature = config.DEEPSEEK_TEMPERATURE
        self.timeout = config.DEEPSEEK_TIMEOUT
        self.base_url = config.DEEPSEEK_BASE_URL
        self.max_retries = config.DEEPSEEK_RETRIES

        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY не задан, ИИ-анализ будет пропущен")
            self.client = None
        else:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

    def _build_prompt(self, entry: TorrentEntry) -> str:
        """Формирует промпт для ИИ (на русском языке)"""
        description = entry.full_description[:3000] if entry.full_description else entry.summary

        prompt = """
Ты — эксперт по оценке контента на торрент-трекерах. Проанализируй следующую раздачу и верни ТОЛЬКО JSON-объект с указанными полями. **Все текстовые поля (category, tags, ai_summary, reason) должны быть строго на русском языке.**

Название: {title}
Категория: {category}
Размер: {size}
Сиды: {seeds}
Описание:
{description}

Требуется вернуть JSON строго в формате:
{{
  "relevance_score": <число от 0 до 100, насколько эта раздача полезна/интересна>,
  "category": <уточнённая категория (строка на русском), если категория не подходит, оставь пустой>,
  "tags": [<массив ключевых слов (строк на русском)>],
  "ai_summary": <краткое описание содержания на русском (1–2 предложения)>,
  "recommendation": <"download" | "maybe" | "skip">,
  "reason": <почему такая оценка (коротко на русском)>
}}

Не добавляй никакого пояснительного текста, только JSON.
""".format(
            title=entry.title,
            category=entry.category,
            size=entry.size,
            seeds=entry.seeds,
            description=description
        )

        # Для отладки (раскомментировать при необходимости)
        # logger.debug(f"Промпт для {entry.rss_id}:\n{prompt}")
        return prompt

    def _call_api(self, prompt: str) -> Optional[str]:
        """Отправляет запрос к DeepSeek через OpenAI SDK"""
        if not self.client:
            return None

        try:
            client_with_timeout = self.client.with_options(timeout=self.timeout)
            logger.info(f"Отправка запроса с max_tokens={self.max_tokens}")
            response = client_with_timeout.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты полезный ассистент, который всегда отвечает строго в формате JSON и на русском языке."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"},
                stream=False,
            )
            content = response.choices[0].message.content
            logger.debug(f"Ответ DeepSeek:\n{content}")
            return content
        except Exception as e:
            logger.error(f"Ошибка вызова DeepSeek API: {e}")
            return None

    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Извлекает и валидирует JSON из ответа"""
        if not response_text:
            logger.error("Пустой ответ от API")
            return None

        logger.debug(f"Сырой ответ для парсинга:\n{response_text}")

        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                else:
                    json_str = response_text.strip()
                    if not json_str.startswith('{') and not json_str.startswith('['):
                        logger.error("В ответе не найден JSON")
                        logger.error(f"Ответ целиком: {response_text[:2000]}")
                        return None

            json_str = re.sub(r'[\x00-\x1f\x7f]', '', json_str)
            data = json.loads(json_str)

            required_fields = ["relevance_score", "category", "tags", "ai_summary", "recommendation", "reason"]
            for field in required_fields:
                if field not in data:
                    logger.error(f"В ответе отсутствует поле {field}")
                    return None

            score = data["relevance_score"]
            if not isinstance(score, (int, float)) or score < 0 or score > 100:
                logger.error(f"Некорректное relevance_score: {score}")
                return None

            if data["recommendation"] not in ["download", "maybe", "skip"]:
                logger.error(f"Некорректное recommendation: {data['recommendation']}")
                return None

            tags = data.get("tags")
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                logger.error("Поле tags должно быть списком строк")
                return None
            data["tags"] = tags[:5]

            return data

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            logger.error(f"Невалидный JSON (первые 300 символов): {json_str[:300]}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при парсинге ответа: {e}")
            return None

    def _analyze_single(self, entry: TorrentEntry) -> Optional[TorrentEntry]:
        """Анализирует одну запись, обновляет её, учитывая счётчик попыток"""
        prompt = self._build_prompt(entry)
        response_text = self._call_api(prompt)

        if response_text:
            result = self._parse_response(response_text)
            if result:
                entry.relevance_score = float(result["relevance_score"])
                entry.ai_category = result.get("category", "")
                entry.ai_tags = result.get("tags", [])
                entry.ai_summary = result.get("ai_summary", "")
                entry.recommendation = result.get("recommendation", "unknown")
                entry.ai_analysis = result
                entry.is_ai_analyzed = True
                entry.ai_retries = 0
                entry.ai_last_error = ""
                return entry

        entry.ai_retries += 1
        entry.ai_last_error = "Ошибка API или парсинга ответа"

        if entry.ai_retries >= self.max_retries:
            entry.is_ai_analyzed = True
            logger.warning(
                f"Запись {entry.rss_id} превысила лимит попыток ({self.max_retries}), "
                "помечена как обработанная с ошибкой"
            )
        else:
            entry.is_ai_analyzed = False

        self.db.save_entry(entry)
        return None

    def process_entries(self, limit: Optional[int] = None) -> int:
        """
        Обрабатывает записи, требующие ИИ-анализа.
        Если limit не указан, обрабатываются все неанализированные записи.
        """
        if not self.api_key:
            logger.warning("API-ключ не задан, пропускаем ИИ-анализ")
            return 0

        entries = self.db.get_unanalyzed_entries(limit=limit)
        if not entries:
            logger.info("Нет записей для ИИ-анализа")
            return 0

        processed = 0
        for entry in entries:
            try:
                logger.info(f"Анализ: {entry.title[:50]}...")
                updated = self._analyze_single(entry)
                if updated:
                    if self.db.save_entry(updated):
                        processed += 1
                        self.db.log_processing(
                            entry.rss_id,
                            'ai_analyzer',
                            'success',
                            f'Оценка: {updated.relevance_score}, рекомендация: {updated.recommendation}'
                        )
                        logger.info(f"✅ Анализ успешен: {entry.title[:40]}... (оценка {updated.relevance_score})")
                    else:
                        self.db.log_processing(
                            entry.rss_id,
                            'ai_analyzer',
                            'error',
                            'Ошибка сохранения после анализа'
                        )
                else:
                    self.db.log_processing(
                        entry.rss_id,
                        'ai_analyzer',
                        'warning',
                        f'Анализ не удался (попытка {entry.ai_retries}/{self.max_retries})'
                    )
            except Exception as e:
                logger.error(f"Ошибка анализа {entry.rss_id}: {e}")
                self.db.log_processing(entry.rss_id, 'ai_analyzer', 'error', str(e))

        logger.info(f"Обработано ИИ-анализом: {processed}/{len(entries)}")
        return processed