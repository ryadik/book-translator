import pytest
from book_translator.proofreader import apply_diffs


def _chunks(*texts):
    """Helper: create chunks with 1-based chunk_index (matches DB convention)."""
    return [{"chunk_index": i + 1, "content_target": t} for i, t in enumerate(texts)]


def test_apply_diffs_exact_match():
    chunks = _chunks("Это тестовое предложение.", "Второе предложение для теста.")
    diffs = [
        {"chunk_index": 1, "find": "тестовое", "replace": "проверочное"},
        {"chunk_index": 2, "find": "для теста", "replace": "для проверки"},
    ]

    updated, applied, skipped = apply_diffs(chunks, diffs)

    assert updated[0]["content_target"] == "Это проверочное предложение."
    assert updated[1]["content_target"] == "Второе предложение для проверки."
    # Ensure original chunks are not mutated
    assert chunks[0]["content_target"] == "Это тестовое предложение."
    assert applied == 2
    assert skipped == 0


def test_apply_diffs_1based_index_not_off_by_one():
    """BUG-1 regression: chunk_index=1 must patch the FIRST chunk, not the second."""
    chunks = _chunks("первый", "второй", "третий")
    diffs = [{"chunk_index": 1, "find": "первый", "replace": "FIXED"}]

    updated, applied, skipped = apply_diffs(chunks, diffs)

    assert updated[0]["content_target"] == "FIXED"
    assert updated[1]["content_target"] == "второй"
    assert updated[2]["content_target"] == "третий"


def test_apply_diffs_zero_matches():
    chunks = _chunks("Это тестовое предложение.")
    diffs = [{"chunk_index": 1, "find": "отсутствующее", "replace": "новое"}]

    updated, applied, skipped = apply_diffs(chunks, diffs)

    assert updated[0]["content_target"] == "Это тестовое предложение."
    assert applied == 0
    assert skipped == 1


def test_apply_diffs_multiple_matches():
    chunks = _chunks("Слово повторяется. Слово снова здесь.")
    diffs = [{"chunk_index": 1, "find": "Слово", "replace": "Термин"}]

    updated, applied, skipped = apply_diffs(chunks, diffs)

    # Should remain unchanged because "Слово" appears twice
    assert updated[0]["content_target"] == "Слово повторяется. Слово снова здесь."


def test_apply_diffs_invalid_index():
    chunks = _chunks("Это тестовое предложение.")
    diffs = [
        {"chunk_index": 99, "find": "тестовое", "replace": "проверочное"},
        {"chunk_index": "bad", "find": "тестовое", "replace": "проверочное"},
    ]

    updated, applied, skipped = apply_diffs(chunks, diffs)

    assert updated[0]["content_target"] == "Это тестовое предложение."


def test_apply_diffs_missing_keys():
    chunks = _chunks("Это тестовое предложение.")
    diffs = [
        {"chunk_index": 1, "find": "тестовое"},          # missing replace
        {"chunk_index": 1, "replace": "проверочное"},    # missing find
        {"find": "тестовое", "replace": "проверочное"},  # missing chunk_index
    ]

    updated, applied, skipped = apply_diffs(chunks, diffs)

    assert updated[0]["content_target"] == "Это тестовое предложение."


def test_apply_diffs_multiple_diffs_same_chunk():
    chunks = _chunks("Первое слово и второе слово.")
    diffs = [
        {"chunk_index": 1, "find": "Первое", "replace": "Один"},
        {"chunk_index": 1, "find": "второе", "replace": "два"},
    ]

    updated, applied, skipped = apply_diffs(chunks, diffs)

    assert updated[0]["content_target"] == "Один слово и два слово."
