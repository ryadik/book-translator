import os
import json
import pytest
import json_repair
from unittest.mock import patch
from pathlib import Path
from book_translator.term_collector import collect_and_deduplicate_terms, update_glossary_file, present_for_confirmation

def test_collect_and_deduplicate_terms(tmp_path):
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    
    # Create dummy term files
    term1 = {
        "response": "```json\n" + json.dumps({
            "characters": {
                "char1": {"name": {"ru": "Имя1", "jp": "名前1"}}
            }
        }) + "\n```"
    }
    
    term2 = {
        "response": json.dumps({
            "characters": {
                "char1": {"name": {"ru": "Имя1", "jp": "名前1"}}, # Duplicate
                "char2": {"name": {"ru": "Имя2", "jp": "名前2"}}
            },
            "terminology": {
                "term1": {"name": {"ru": "Термин1", "jp": "用語1"}}
            }
        })
    }
    
    (terms_dir / "chunk_1.json").write_text(json.dumps(term1), encoding="utf-8")
    (terms_dir / "chunk_2.json").write_text(json.dumps(term2), encoding="utf-8")
    
    workspace_paths = {"terms": str(terms_dir)}
    result = collect_and_deduplicate_terms(workspace_paths)
    
    assert "characters" in result
    assert "terminology" in result
    assert "expressions" in result
    
    assert len(result["characters"]) == 2
    assert "char1" in result["characters"]
    assert "char2" in result["characters"]
    
    assert len(result["terminology"]) == 1
    assert "term1" in result["terminology"]

def test_collect_malformed_json(tmp_path):
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    
    # Malformed JSON: missing closing brace and trailing comma
    malformed_content = {
        "response": "```json\n" + "{\"characters\": {\"char3\": {\"name\": {\"ru\": \"Имя3\"}," + "\n```"
    }
    (terms_dir / "malformed.json").write_text(json.dumps(malformed_content), encoding="utf-8")
    
    workspace_paths = {"terms": str(terms_dir)}
    result = collect_and_deduplicate_terms(workspace_paths)
    
    assert "characters" in result
    assert "char3" in result["characters"]
    assert result["characters"]["char3"]["name"]["ru"] == "Имя3"

def test_update_glossary_file(tmp_path):
    # update_glossary_file uses new db.add_term signature.
    # We mock db.add_term in term_collector's namespace to capture calls.
    called_with = []

    def mock_add_term(db_path, term_jp, term_ru, source_lang, target_lang):
        called_with.append((term_jp, term_ru))

    new_terms = {
        "characters": {
            "char2": {"name": {"jp": "char2_jp", "ru": "Имя2"}}
        },
        "terminology": {
            "term1": {"name": {"jp": "term1_jp", "ru": "Термин1"}}
        }
    }

    with patch('book_translator.term_collector.db.add_term', side_effect=mock_add_term):
        update_glossary_file(new_terms, tmp_path / 'test.db')

    term_jps = [t[0] for t in called_with]
    assert 'char2_jp' in term_jps
    assert 'term1_jp' in term_jps

@patch('builtins.input', side_effect=['ok'])
def test_present_for_confirmation_ok(mock_input):
    new_terms = {
        "characters": {
            "char1": {"name": {"ru": "Имя1"}}
        }
    }
    
    result = present_for_confirmation(new_terms)
    assert result is not None
    assert "char1" in result["characters"]

@patch('builtins.input', side_effect=['quit'])
def test_present_for_confirmation_quit(mock_input):
    new_terms = {
        "characters": {
            "char1": {"name": {"ru": "Имя1"}}
        }
    }
    
    result = present_for_confirmation(new_terms)
    assert result is None

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
