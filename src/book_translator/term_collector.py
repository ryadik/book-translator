from pathlib import Path
from typing import Any
from book_translator.logger import system_logger
from book_translator.utils import parse_llm_json


def _parse_terms_from_data(data: Any) -> list[dict]:
    """Extract a flat list of {source, target, comment} dicts from parsed LLM output.

    Accepts only the flat array format: [{source, target, comment}, ...]
    """
    if isinstance(data, list):
        terms = []
        for item in data:
            if isinstance(item, dict) and item.get('source') and item.get('target'):
                terms.append(item)
        return terms

    return []


def collect_terms_from_responses(raw_responses: list[str]) -> list[dict]:
    """Parse LLM JSON responses and return deduplicated flat term list.

    Each term: {'source': str, 'target': str, 'comment': str}
    """
    seen_sources: set[str] = set()
    unique_terms: list[dict] = []
    total = len(raw_responses)
    parsed_count = 0

    for response_str in raw_responses:
        if not response_str or not response_str.strip():
            system_logger.warning("[TermCollector] Пропуск пустого ответа (пустая строка)")
            continue
        try:
            data = parse_llm_json(response_str)
            terms = _parse_terms_from_data(data)
            if not terms and data:
                system_logger.warning(
                    f"[TermCollector] Ответ не содержит терминов в ожидаемом формате. "
                    f"Тип данных: {type(data).__name__}. Пропуск."
                )
                continue
            parsed_count += 1
            for term in terms:
                src = term.get('source', '')
                if src and src not in seen_sources:
                    seen_sources.add(src)
                    unique_terms.append(term)
        except Exception as e:
            system_logger.warning(
                f"[TermCollector] Не удалось распарсить ответ: {e}. "
                f"Начало ответа: {response_str[:200]!r}"
            )

    system_logger.info(
        f"[TermCollector] Обработано {parsed_count}/{total} ответов, "
        f"найдено {len(unique_terms)} уникальных терминов."
    )
    return unique_terms


