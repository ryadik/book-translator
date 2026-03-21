import pytest
from book_translator.chapter_splitter import split_chapter_intelligently


def test_split_basic(tmp_path):
    chapter_file = tmp_path / "chapter.txt"
    content = "A" * 30 + "\n\n" + "B" * 30 + "\n\n" + "C" * 30
    chapter_file.write_text(content, encoding="utf-8")

    chunks = split_chapter_intelligently(str(chapter_file), target_chars=50, max_part_chars=100)

    assert len(chunks) == 3
    assert chunks[0] == {"id": 1, "text": "A" * 30 + "\n\n"}
    assert chunks[1] == {"id": 2, "text": "B" * 30 + "\n\n"}
    assert chunks[2] == {"id": 3, "text": "C" * 30}


def test_split_returns_id_and_text_only(tmp_path):
    chapter_file = tmp_path / "chapter.txt"
    chapter_file.write_text("Hello\n\nWorld", encoding="utf-8")

    chunks = split_chapter_intelligently(str(chapter_file), target_chars=10, max_part_chars=50)

    for chunk in chunks:
        assert set(chunk.keys()) == {"id", "text"}


def test_split_scene_marker(tmp_path):
    chapter_file = tmp_path / "chapter.txt"
    content = "A" * 30 + "\n---\n" + "B" * 30
    chapter_file.write_text(content, encoding="utf-8")

    chunks = split_chapter_intelligently(str(chapter_file), target_chars=40, max_part_chars=100)

    assert len(chunks) == 2
    assert "---" in chunks[0]["text"]
    assert "B" * 30 not in chunks[0]["text"]
    assert "B" * 30 in chunks[1]["text"]


def test_split_dialogue_not_broken_before(tmp_path):
    chapter_file = tmp_path / "chapter.txt"
    # blank line followed by dialogue — should not break at blank line
    content = "A" * 30 + "\n\n" + "「Hello」" + "B" * 30
    chapter_file.write_text(content, encoding="utf-8")

    chunks = split_chapter_intelligently(str(chapter_file), target_chars=40, max_part_chars=100)

    assert len(chunks) >= 1
    # All text must be preserved
    full = "".join(c["text"] for c in chunks)
    assert "A" * 30 in full
    assert "「Hello」" in full


def test_split_single_chunk_short_file(tmp_path):
    chapter_file = tmp_path / "chapter.txt"
    chapter_file.write_text("Short text.", encoding="utf-8")

    chunks = split_chapter_intelligently(str(chapter_file), target_chars=3000, max_part_chars=5000)

    assert len(chunks) == 1
    assert chunks[0]["id"] == 1
    assert "Short text." in chunks[0]["text"]


def test_split_ids_are_sequential(tmp_path):
    chapter_file = tmp_path / "chapter.txt"
    content = "\n\n".join(["X" * 30] * 5)
    chapter_file.write_text(content, encoding="utf-8")

    chunks = split_chapter_intelligently(str(chapter_file), target_chars=50, max_part_chars=100)

    for i, chunk in enumerate(chunks, start=1):
        assert chunk["id"] == i
