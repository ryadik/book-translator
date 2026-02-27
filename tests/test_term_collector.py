import os
import json
import pytest
import json_repair
from unittest.mock import patch
import json
import pytest
from unittest.mock import patch
from term_collector import collect_and_deduplicate_terms, update_glossary_file, present_for_confirmation

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
    db_path = str(tmp_path / "test.db")
    import db
    db.init_db(db_path)
    
    # Initial glossary
    db.add_term(db_path, "test_project", "char1_jp", "Имя1")

    new_terms = {
        "characters": {
            "char2": {"name": {"jp": "char2_jp", "ru": "Имя2"}}
        },
        "terminology": {
            "term1": {"name": {"jp": "term1_jp", "ru": "Термин1"}}
        }
    }

    update_glossary_file(new_terms, db_path, "test_project")

    terms = db.get_terms(db_path, "test_project")
    term_jps = [t["term_jp"] for t in terms]
    
    assert "char1_jp" in term_jps
    assert "char2_jp" in term_jps
    assert "term1_jp" in term_jps
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
