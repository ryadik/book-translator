import json
import pytest
from pathlib import Path


# ─── collect_terms_from_responses ────────────────────────────────────────────

def test_collect_new_flat_array_format():
    """New format: LLM returns a flat JSON array."""
    from book_translator.term_collector import collect_terms_from_responses
    raw = json.dumps([
        {"source": "キリト", "target": "Кирито", "comment": "male, protagonist"},
        {"source": "ソードスキル", "target": "Навык меча", "comment": "combat skill"},
    ])
    result = collect_terms_from_responses([raw])
    assert len(result) == 2
    sources = {t['source'] for t in result}
    assert "キリト" in sources
    assert "ソードスキル" in sources


def test_collect_deduplicates_by_source():
    """Same source across two responses — kept only once."""
    from book_translator.term_collector import collect_terms_from_responses
    r1 = json.dumps([{"source": "hero", "target": "Герой", "comment": ""}])
    r2 = json.dumps([{"source": "hero", "target": "Герой", "comment": "dupe"}])
    result = collect_terms_from_responses([r1, r2])
    assert len(result) == 1


def test_collect_skips_empty_strings():
    """Empty strings are skipped; valid responses are collected."""
    from book_translator.term_collector import collect_terms_from_responses
    valid = json.dumps([{"source": "hero", "target": "Герой", "comment": ""}])
    result = collect_terms_from_responses(["", "   ", valid])
    assert len(result) == 1
    assert result[0]['source'] == 'hero'


def test_collect_empty_array_returns_empty():
    """LLM returns [] — no terms."""
    from book_translator.term_collector import collect_terms_from_responses
    result = collect_terms_from_responses([json.dumps([])])
    assert result == []


def test_collect_empty_input_returns_empty():
    from book_translator.term_collector import collect_terms_from_responses
    assert collect_terms_from_responses([]) == []


def test_collect_wrapper_with_empty_response_skipped():
    """Gemini-cli wrapper with empty inner response raises ValueError → caught, skipped."""
    from book_translator.term_collector import collect_terms_from_responses
    wrapper = json.dumps({"session_id": "abc", "response": ""})
    result = collect_terms_from_responses([wrapper])
    assert result == []


def test_collect_backward_compat_old_category_format():
    """Old format with categories dict is still parsed correctly."""
    from book_translator.term_collector import collect_terms_from_responses
    old_format = json.dumps({
        "characters": {
            "キリト": {"term_jp": "キリト", "term_ru": "Кирито", "comment": "герой"}
        },
        "terminology": {},
        "expressions": {},
    })
    result = collect_terms_from_responses([old_format])
    assert len(result) == 1
    assert result[0]['source'] == 'キリト'
    assert result[0]['target'] == 'Кирито'


# ─── save_approved_terms ──────────────────────────────────────────────────────

def test_save_approved_terms(tmp_path):
    """save_approved_terms writes flat list to glossary DB."""
    from book_translator.term_collector import save_approved_terms
    from book_translator.db import init_glossary_db, get_terms
    glossary_db = tmp_path / 'glossary.db'
    init_glossary_db(glossary_db)

    terms = [
        {"source": "キリト", "target": "Кирито", "comment": "male, protagonist"},
        {"source": "ソードスキル", "target": "Навык меча", "comment": "combat skill"},
    ]
    save_approved_terms(terms, glossary_db)

    result = get_terms(glossary_db)
    assert len(result) == 2
    sources = {r['term_source'] for r in result}
    assert "キリト" in sources
    assert "ソードスキル" in sources


def test_save_approved_terms_comment_stored(tmp_path):
    from book_translator.term_collector import save_approved_terms
    from book_translator.db import init_glossary_db, get_terms
    glossary_db = tmp_path / 'glossary.db'
    init_glossary_db(glossary_db)

    save_approved_terms([{"source": "Hero", "target": "Герой", "comment": "main character"}], glossary_db)
    result = get_terms(glossary_db)
    assert result[0]['comment'] == 'main character'


def test_save_approved_terms_skips_incomplete(tmp_path):
    """Terms without source or target are skipped."""
    from book_translator.term_collector import save_approved_terms
    from book_translator.db import init_glossary_db, get_terms
    glossary_db = tmp_path / 'glossary.db'
    init_glossary_db(glossary_db)

    save_approved_terms([
        {"source": "Hero", "target": ""},      # empty target
        {"source": "", "target": "Герой"},     # empty source
        {"source": "Valid", "target": "Верно", "comment": ""},
    ], glossary_db)
    result = get_terms(glossary_db)
    assert len(result) == 1
    assert result[0]['term_source'] == 'Valid'
