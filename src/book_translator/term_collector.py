from pathlib import Path
from typing import Any
from book_translator.logger import system_logger
from book_translator import db
from book_translator import glossary_manager
from book_translator.utils import parse_llm_json


_EXPECTED_CATEGORIES = {"characters", "terminology", "expressions"}


def collect_terms_from_responses(raw_responses: list[str]) -> dict[str, Any]:
    """Parse LLM JSON responses from gemini-cli and deduplicate terms.

    Accepts raw response strings. Uses utils.parse_llm_json for robust parsing.
    """
    unique_terms = {}
    total = len(raw_responses)
    parsed_count = 0

    for response_str in raw_responses:
        if not response_str or not response_str.strip():
            system_logger.warning("[TermCollector] Пропуск пустого ответа (пустая строка)")
            continue
        try:
            data = parse_llm_json(response_str)
            if not isinstance(data, dict):
                system_logger.warning(f"[TermCollector] Ответ не является dict (тип: {type(data).__name__}). Пропуск.")
                continue
            if not data.keys() & _EXPECTED_CATEGORIES:
                system_logger.warning(
                    f"[TermCollector] Ответ не содержит ожидаемых категорий. "
                    f"Найдены ключи: {set(data.keys())}. Ожидались: {_EXPECTED_CATEGORIES}. Пропуск."
                )
                continue
            parsed_count += 1
            for category, items in data.items():
                if not isinstance(items, dict):
                    continue
                for term_id, term_data in items.items():
                    if term_id not in unique_terms:
                        unique_terms[term_id] = {"category": category, "data": term_data}
        except Exception as e:
            system_logger.warning(
                f"[TermCollector] Не удалось распарсить ответ: {e}. "
                f"Начало ответа: {response_str[:200]!r}"
            )

    system_logger.info(
        f"[TermCollector] Обработано {parsed_count}/{total} ответов, "
        f"найдено {len(unique_terms)} уникальных терминов."
    )
    final_structure = {"characters": {}, "terminology": {}, "expressions": {}}
    for term_id, term_info in unique_terms.items():
        cat = term_info["category"]
        if cat in final_structure:
            final_structure[cat][term_id] = term_info["data"]
    return final_structure


def save_approved_terms(terms: dict[str, Any], glossary_db: Path,
                        source_lang: str = 'ja', target_lang: str = 'ru'):
    """Save approved terms to the series-level glossary database.

    Replaces update_glossary_file() — writes to series glossary.db instead of state.db.
    """
    count = 0
    for category, items in terms.items():
        for term_id, term_data in items.items():
            term_source = term_data.get('source') or \
                          term_data.get('name', {}).get('source') or \
                          term_data.get('name', {}).get('jp') or \
                          term_data.get('term_source') or \
                          term_data.get('term_jp') or \
                          term_id
            term_target = term_data.get('target') or \
                          term_data.get('name', {}).get('target') or \
                          term_data.get('name', {}).get('ru') or \
                          term_data.get('term_target') or \
                          term_data.get('term_ru', '')
            comment = term_data.get('comment') or \
                      term_data.get('description', '')
            if term_source and term_target:
                db.add_term(glossary_db, term_source, term_target,
                           source_lang, target_lang, comment)
                count += 1
    system_logger.info(f"[TermCollector] Saved {count} terms to glossary DB.")


def approve_via_tsv(terms: dict[str, Any], tsv_path: Path, glossary_db: Path,
                   source_lang: str = 'ja', target_lang: str = 'ru'):
    """Generate TSV → wait for user edit → import approved terms.

    This is the TSV 'approval buffer' workflow.
    """
    term_list = []
    for category, items in terms.items():
        for term_id, term_data in items.items():
            term_source = term_data.get('source') or \
                          term_data.get('name', {}).get('source') or \
                          term_data.get('name', {}).get('jp') or \
                          term_data.get('term_source') or \
                          term_data.get('term_jp') or \
                          term_id
            term_target = term_data.get('target') or \
                          term_data.get('name', {}).get('target') or \
                          term_data.get('name', {}).get('ru') or \
                          term_data.get('term_target') or \
                          term_data.get('term_ru', '')
            comment = term_data.get('comment') or \
                      term_data.get('description', '')

            term_list.append({
                'term_source': term_source,
                'term_target': term_target,
                'comment': comment,
            })

    glossary_manager.generate_approval_tsv(term_list, tsv_path)
    print(f"\n📝 Отредактируйте файл: {tsv_path}")
    print("Удалите ненужные строки, исправьте переводы.")
    input("Нажмите Enter когда закончите...")
    count = glossary_manager.import_tsv(glossary_db, tsv_path, source_lang, target_lang)
    print(f"✅ Импортировано {count} терминов")
