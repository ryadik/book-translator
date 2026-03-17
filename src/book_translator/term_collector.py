import json
import os
import re
import json_repair
from pathlib import Path
from typing import Dict, Any, List, Optional
from book_translator.logger import system_logger
from book_translator import db
from book_translator import glossary_manager
from book_translator.utils import parse_llm_json

def collect_and_deduplicate_terms(workspace_paths: Dict[str, Any]) -> Dict[str, Any]:
    terms_dir = workspace_paths.get("terms")
    if not terms_dir or not os.path.exists(terms_dir):
        return {}
    unique_terms = {}
    for filename in os.listdir(terms_dir):
        if not filename.endswith(".json"): continue
        file_path = os.path.join(terms_dir, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f: cli_output = json.load(f)
            if not (isinstance(cli_output, dict) and "response" in cli_output): continue
            response_str = cli_output["response"]
            match = re.search(r'```json\s*\n(.*?)\s*\n```', response_str, re.DOTALL)
            json_str = match.group(1) if match else response_str
            data = json_repair.loads(json_str)
            if not isinstance(data, dict): continue
            for category, items in data.items():
                if not isinstance(items, dict): continue
                for term_id, term_data in items.items():
                    if term_id not in unique_terms:
                        unique_terms[term_id] = {"category": category, "data": term_data}
        except (json.JSONDecodeError, IOError, TypeError) as e:
            system_logger.error(f"[TermCollector] Ошибка обработки файла '{filename}': {e}")
    final_structure = {"characters": {}, "terminology": {}, "expressions": {}}
    for term_id, term_info in unique_terms.items():
        cat = term_info["category"]
        if cat in final_structure:
            final_structure[cat][term_id] = term_info["data"]
    return final_structure

def _edit_term(term_data: Dict[str, Any]) -> Dict[str, Any]:
    system_logger.info("\n--- Редактирование термина ---")
    for key in ["ru", "jp", "romaji"]:
        new_val = input(f"  name.{key} (Enter, чтобы оставить '{term_data['name'].get(key, '')}'): ").strip()
        if new_val: term_data['name'][key] = new_val
    new_desc = input(f"  description (Enter, чтобы оставить '{term_data.get('description', '')}'): ").strip()
    if new_desc: term_data['description'] = new_desc
    new_context = input(f"  context (Enter, чтобы оставить '{term_data.get('context', '')}'): ").strip()
    if new_context: term_data['context'] = new_context
    system_logger.info(f"  Текущие псевдонимы: {[a.get('ru', '') for a in term_data.get('aliases', [])]}")
    if input("  Редактировать псевдонимы? (y/n): ").lower() == 'y':
        term_data['aliases'] = []
        while True:
            alias_ru = input("    Добавить псевдоним (RU) (Enter для завершения): ").strip()
            if not alias_ru: break
            term_data['aliases'].append({"ru": alias_ru})
    if "characteristics" in term_data: # Персонаж
        for key, val in term_data["characteristics"].items():
            new_val = input(f"  characteristics.{key} (Enter, чтобы оставить '{val}'): ").strip()
            if new_val: term_data["characteristics"][key] = new_val
    elif "type" in term_data: # Термин
        new_type = input(f"  type (Enter, чтобы оставить '{term_data['type']}'): ").strip()
        if new_type: term_data['type'] = new_type
    system_logger.info("--- Редактирование завершено ---")
    return term_data

def present_for_confirmation(new_terms: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not any(new_terms.values()):
        system_logger.info("\n[TermCollector] Новых терминов для добавления не найдено.")
        return {}
    term_list = []
    for category, items in new_terms.items():
        for term_id, data in items.items():
            term_list.append({"id": term_id, "category": category, "data": data})
    while True:
        system_logger.info("\n" + "="*40 + "\n  Найдены новые термины для подтверждения\n" + "="*40)
        for i, term in enumerate(term_list):
            term_data = term['data']
            jp_name = term_data.get('name', {}).get('jp') or term_data.get('term_jp', 'N/A')
            ru_name = term_data.get('name', {}).get('ru') or term_data.get('term_ru', 'N/A')
            system_logger.info(f"\n--- Термин #{i+1} ---\n  ID: {term['id']} (Категория: {term['category']})\n  JP: {jp_name}\n  RU: {ru_name}\n  Описание: {term_data.get('description', 'N/A')}\n  Контекст: {term_data.get('context', 'N/A')}")
        system_logger.info("\n" + "-"*40 + "\n  Команды: ok, del <номера>, edit <номер>, quit\n" + "-"*40)
        try: 
            if os.environ.get('AUTO_ACCEPT_TERMS') == '1':
                command = 'ok'
            else:
                command = input("\nВведите команду: ").strip().lower()
        except EOFError: return None
        if command in ['ok', 'yes', 'y']:
            final_terms = {"characters": {}, "terminology": {}, "expressions": {}}
            for term in term_list:
                if term["category"] in final_terms: final_terms[term["category"]][term["id"]] = term["data"]
            return final_terms
        if command in ['quit', 'exit', 'q']: return None
        parts = command.split()
        if not parts: continue
        action = parts[0]
        try:
            indices = [int(p) - 1 for p in parts[1:]]
            if not all(0 <= i < len(term_list) for i in indices):
                system_logger.warning("Ошибка: Неверный номер термина.")
                continue
            if action == 'del':
                for i in sorted(indices, reverse=True): del term_list[i]
                system_logger.info(f"Удалено {len(indices)} терминов.")
            elif action == 'edit':
                if len(indices) != 1:
                    system_logger.warning("Ошибка: Редактировать можно только один термин за раз.")
                    continue
                idx_to_edit = indices[0]
                term_list[idx_to_edit]["data"] = _edit_term(term_list[idx_to_edit]["data"])
            else: system_logger.warning(f"Неизвестная команда: '{action}'")
        except (ValueError, IndexError): system_logger.error("Ошибка: Неверный формат команды.")

def update_glossary_file(new_terms: Dict[str, Any], db_path: Path, source_lang: str = 'ja', target_lang: str = 'ru'):
    if not any(new_terms.values()):
        return
    system_logger.info(f"\n[TermCollector] Обновление SQLite глоссария: {db_path}")
    for cat in ["characters", "terminology", "expressions"]:
        for term_id, term_data in new_terms.get(cat, {}).items():
            term_jp = term_data.get("name", {}).get("jp", "")
            term_ru = term_data.get("name", {}).get("ru", "")
            if term_jp and term_ru:
                db.add_term(db_path, term_jp, term_ru, source_lang, target_lang)
    system_logger.info("[TermCollector] Глоссарий успешно обновлен.")


def collect_terms_from_responses(raw_responses: List[str]) -> Dict[str, Any]:
    """Parse LLM JSON responses from gemini-cli and deduplicate terms.

    Accepts raw response strings. Uses utils.parse_llm_json for robust parsing.
    """
    unique_terms = {}
    for response_str in raw_responses:
        try:
            data = parse_llm_json(response_str)
            if not isinstance(data, dict):
                continue
            for category, items in data.items():
                if not isinstance(items, dict):
                    continue
                for term_id, term_data in items.items():
                    if term_id not in unique_terms:
                        unique_terms[term_id] = {"category": category, "data": term_data}
        except Exception as e:
            system_logger.warning(f"[TermCollector] Не удалось распарсить ответ: {e}")
    final_structure = {"characters": {}, "terminology": {}, "expressions": {}}
    for term_id, term_info in unique_terms.items():
        cat = term_info["category"]
        if cat in final_structure:
            final_structure[cat][term_id] = term_info["data"]
    return final_structure


def save_approved_terms(terms: Dict[str, Any], glossary_db: Path,
                        source_lang: str = 'ja', target_lang: str = 'ru'):
    """Save approved terms to the series-level glossary database.
    
    Replaces update_glossary_file() — writes to series glossary.db instead of state.db.
    """
    count = 0
    for category, items in terms.items():
        for term_id, term_data in items.items():
            term_source = term_data.get('name', {}).get('jp') or \
                          term_data.get('term_jp') or \
                          term_data.get('term_source') or \
                          term_id
            term_target = term_data.get('name', {}).get('ru') or \
                          term_data.get('term_ru') or \
                          term_data.get('term_target', '')
            comment = term_data.get('description') or term_data.get('comment', '')
            if term_source and term_target:
                db.add_term(glossary_db, term_source, term_target,
                           source_lang, target_lang, comment)
                count += 1
    system_logger.info(f"[TermCollector] Saved {count} terms to glossary DB.")


def approve_via_tsv(terms: Dict[str, Any], tsv_path: Path, glossary_db: Path,
                   source_lang: str = 'ja', target_lang: str = 'ru'):
    """Generate TSV → wait for user edit → import approved terms.
    
    This is the TSV 'approval buffer' workflow.
    """
    # Convert from internal format to list of dicts for glossary_manager
    term_list = []
    for category, items in terms.items():
        for term_id, term_data in items.items():
            term_source = term_data.get('name', {}).get('jp') or \
                          term_data.get('term_jp') or \
                          term_data.get('term_source') or \
                          term_id
            term_target = term_data.get('name', {}).get('ru') or \
                          term_data.get('term_ru') or \
                          term_data.get('term_target', '')
            comment = term_data.get('description') or term_data.get('comment', '')
            
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
