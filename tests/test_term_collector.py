import json
import pytest
from pathlib import Path


def test_collect_terms_from_responses():
    """Test collect_terms_from_responses with raw JSON string."""
    from book_translator.term_collector import collect_terms_from_responses
    raw = json.dumps({
        "response": '{"characters": {"\u30ad\u30ea\u30c8": {"term_jp": "\u30ad\u30ea\u30c8", "term_ru": "\u041a\u0438\u0440\u0438\u0442\u043e", "comment": "\u0433\u0435\u0440\u043e\u0439"}}}'
    })
    result = collect_terms_from_responses([raw])
    assert "characters" in result
    assert "\u30ad\u30ea\u30c8" in result["characters"]
    assert result["characters"]["\u30ad\u30ea\u30c8"]["term_ru"] == "\u041a\u0438\u0440\u0438\u0442\u043e"


def test_collect_terms_from_responses_empty():
    from book_translator.term_collector import collect_terms_from_responses
    result = collect_terms_from_responses([])
    assert all(not v for v in result.values())


def test_collect_skips_empty_strings():
    """Пустые строки пропускаются, термины из валидных ответов сохраняются."""
    from book_translator.term_collector import collect_terms_from_responses
    valid = json.dumps({"characters": {"hero": {"source": "Hero", "target": "Герой", "comment": ""}}})
    result = collect_terms_from_responses(["", "   ", valid])
    assert "hero" in result["characters"]


def test_collect_skips_wrapper_dict_keys():
    """Ответ только с ключами обёртки (session_id/response) после FIX-1 бросает ValueError и пропускается."""
    from book_translator.term_collector import collect_terms_from_responses
    # FIX-1: parse_llm_json теперь бросает ValueError для обёртки с пустым response
    wrapper = json.dumps({"session_id": "abc", "response": ""})
    result = collect_terms_from_responses([wrapper])
    assert all(not v for v in result.values())


def test_collect_skips_non_category_dict():
    """Dict без ожидаемых категорий пропускается с warning."""
    from book_translator.term_collector import collect_terms_from_responses
    wrong = json.dumps({"session_id": "abc", "data": "some data"})
    result = collect_terms_from_responses([wrong])
    assert all(not v for v in result.values())


def test_save_approved_terms(tmp_path):
    """Test save_approved_terms writes to glossary DB (старый формат term_jp/term_ru)."""
    from book_translator.term_collector import save_approved_terms
    from book_translator.db import init_glossary_db, get_terms
    glossary_db = tmp_path / 'glossary.db'
    init_glossary_db(glossary_db)

    terms = {
        "characters": {
            "\u30ad\u30ea\u30c8": {"term_jp": "\u30ad\u30ea\u30c8", "term_ru": "\u041a\u0438\u0440\u0438\u0442\u043e", "comment": ""}
        }
    }
    save_approved_terms(terms, glossary_db)

    result = get_terms(glossary_db)
    assert len(result) == 1
    assert result[0]['term_source'] == '\u30ad\u30ea\u30c8'
    assert result[0]['term_target'] == '\u041a\u0438\u0440\u0438\u0442\u043e'


def test_save_approved_terms_new_format(tmp_path):
    """Новый формат (source/target/comment) сохраняется корректно."""
    from book_translator.term_collector import save_approved_terms
    from book_translator.db import init_glossary_db, get_terms
    glossary_db = tmp_path / 'glossary.db'
    init_glossary_db(glossary_db)

    terms = {
        "characters": {
            "hero": {"source": "Hero", "target": "Герой", "comment": "Главный персонаж"}
        }
    }
    save_approved_terms(terms, glossary_db)

    result = get_terms(glossary_db)
    assert len(result) == 1
    assert result[0]['term_source'] == 'Hero'
    assert result[0]['term_target'] == 'Герой'
    assert result[0]['comment'] == 'Главный персонаж'


def test_save_approved_terms_old_name_format(tmp_path):
    """Старый формат name.source/name.target по-прежнему работает."""
    from book_translator.term_collector import save_approved_terms
    from book_translator.db import init_glossary_db, get_terms
    glossary_db = tmp_path / 'glossary.db'
    init_glossary_db(glossary_db)

    terms = {
        "characters": {
            "hero": {"name": {"source": "Hero", "target": "Герой"}, "description": "Главный"}
        }
    }
    save_approved_terms(terms, glossary_db)

    result = get_terms(glossary_db)
    assert len(result) == 1
    assert result[0]['term_source'] == 'Hero'
    assert result[0]['term_target'] == 'Герой'
