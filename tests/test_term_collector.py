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


def test_save_approved_terms(tmp_path):
    """Test save_approved_terms writes to glossary DB."""
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
