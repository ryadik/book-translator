import pytest
from book_translator.proofreader import apply_diffs

def test_apply_diffs_exact_match():
    chunks = [
        {"content_target": "Это тестовое предложение."},
        {"content_target": "Второе предложение для теста."}
    ]
    diffs = [
        {"chunk_index": 0, "find": "тестовое", "replace": "проверочное"},
        {"chunk_index": 1, "find": "для теста", "replace": "для проверки"}
    ]
    
    updated_chunks = apply_diffs(chunks, diffs)
    
    assert updated_chunks[0]["content_target"] == "Это проверочное предложение."
    assert updated_chunks[1]["content_target"] == "Второе предложение для проверки."
    # Ensure original chunks are not mutated
    assert chunks[0]["content_target"] == "Это тестовое предложение."

def test_apply_diffs_zero_matches():
    chunks = [
        {"content_target": "Это тестовое предложение."}
    ]
    diffs = [
        {"chunk_index": 0, "find": "отсутствующее", "replace": "новое"}
    ]
    
    updated_chunks = apply_diffs(chunks, diffs)
    
    # Should remain unchanged
    assert updated_chunks[0]["content_target"] == "Это тестовое предложение."

def test_apply_diffs_multiple_matches():
    chunks = [
        {"content_target": "Слово повторяется. Слово снова здесь."}
    ]
    diffs = [
        {"chunk_index": 0, "find": "Слово", "replace": "Термин"}
    ]
    
    updated_chunks = apply_diffs(chunks, diffs)
    
    # Should remain unchanged because "Слово" appears twice
    assert updated_chunks[0]["content_target"] == "Слово повторяется. Слово снова здесь."

def test_apply_diffs_invalid_index():
    chunks = [
        {"content_target": "Это тестовое предложение."}
    ]
    diffs = [
        {"chunk_index": 5, "find": "тестовое", "replace": "проверочное"},
        {"chunk_index": -1, "find": "тестовое", "replace": "проверочное"}
    ]
    
    updated_chunks = apply_diffs(chunks, diffs)
    
    # Should remain unchanged
    assert updated_chunks[0]["content_target"] == "Это тестовое предложение."

def test_apply_diffs_missing_keys():
    chunks = [
        {"content_target": "Это тестовое предложение."}
    ]
    diffs = [
        {"chunk_index": 0, "find": "тестовое"}, # Missing replace
        {"chunk_index": 0, "replace": "проверочное"}, # Missing find
        {"find": "тестовое", "replace": "проверочное"} # Missing chunk_index
    ]
    
    updated_chunks = apply_diffs(chunks, diffs)
    
    # Should remain unchanged
    assert updated_chunks[0]["content_target"] == "Это тестовое предложение."

def test_apply_diffs_multiple_diffs_same_chunk():
    chunks = [
        {"content_target": "Первое слово и второе слово."}
    ]
    diffs = [
        {"chunk_index": 0, "find": "Первое", "replace": "Один"},
        {"chunk_index": 0, "find": "второе", "replace": "два"}
    ]
    
    updated_chunks = apply_diffs(chunks, diffs)
    
    assert updated_chunks[0]["content_target"] == "Один слово и два слово."
