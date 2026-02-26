import os
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

def test_update_glossary_file(tmp_path):
    glossary_file = tmp_path / "glossary.json"
    
    # Initial glossary
    initial_data = {
        "characters": {
            "char1": {"name": {"ru": "Имя1"}}
        }
    }
    glossary_file.write_text(json.dumps(initial_data), encoding="utf-8")
    
    new_terms = {
        "characters": {
            "char2": {"name": {"ru": "Имя2"}}
        },
        "terminology": {
            "term1": {"name": {"ru": "Термин1"}}
        }
    }
    
    update_glossary_file(new_terms, str(glossary_file))
    
    updated_data = json.loads(glossary_file.read_text(encoding="utf-8"))
    
    assert "char1" in updated_data["characters"]
    assert "char2" in updated_data["characters"]
    assert "term1" in updated_data["terminology"]

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
