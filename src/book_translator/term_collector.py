import sys
from pathlib import Path
from typing import Any
from book_translator.logger import system_logger
from book_translator import db
from book_translator import glossary_manager
from book_translator.utils import parse_llm_json


def _parse_terms_from_data(data: Any) -> list[dict]:
    """Extract a flat list of {source, target, comment} dicts from parsed LLM output.

    Accepts both the new flat array format and the old categorised dict format
    (backward compatibility for cached responses).
    """
    if isinstance(data, list):
        # New format: [{source, target, comment}, ...]
        terms = []
        for item in data:
            if isinstance(item, dict) and item.get('source') and item.get('target'):
                terms.append(item)
        return terms

    if isinstance(data, dict):
        # Old format: {characters: {id: {source, target, comment}}, ...}
        _LEGACY_CATEGORIES = {"characters", "terminology", "expressions"}
        if not (data.keys() & _LEGACY_CATEGORIES):
            return []
        terms = []
        for category, items in data.items():
            if not isinstance(items, dict):
                continue
            for term_id, term_data in items.items():
                if not isinstance(term_data, dict):
                    continue
                source = (term_data.get('source') or
                          term_data.get('name', {}).get('source') or
                          term_data.get('term_source') or
                          term_data.get('term_jp') or
                          term_id)
                target = (term_data.get('target') or
                          term_data.get('name', {}).get('target') or
                          term_data.get('term_target') or
                          term_data.get('term_ru', ''))
                comment = term_data.get('comment') or term_data.get('description', '')
                if source and target:
                    terms.append({'source': source, 'target': target, 'comment': comment})
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


def approve_via_tsv(terms: list[dict], tsv_path: Path, glossary_db_path: Path,
                    source_lang: str = 'ja', target_lang: str = 'ru'):
    """Generate TSV → wait for user edit → import approved terms."""
    term_list = [
        {
            'term_source': t.get('source', ''),
            'term_target': t.get('target', ''),
            'comment': t.get('comment', ''),
        }
        for t in terms
        if t.get('source') and t.get('target')
    ]

    glossary_manager.generate_approval_tsv(term_list, tsv_path)
    print(f"\n📝 Отредактируйте файл: {tsv_path}")
    print("Удалите ненужные строки, исправьте переводы.")
    if not sys.stdin.isatty():
        raise RuntimeError(
            f"Требуется интерактивное подтверждение терминов. "
            f"TSV сохранён: {tsv_path}"
        )
    input("Нажмите Enter когда закончите...")
    count = glossary_manager.import_tsv(glossary_db_path, tsv_path, source_lang, target_lang)
    print(f"✅ Импортировано {count} терминов")
