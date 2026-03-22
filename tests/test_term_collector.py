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


