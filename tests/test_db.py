import pytest
import sqlite3
from pathlib import Path
from db import (
    connection,
    init_glossary_db,
    init_chunks_db,
    add_term,
    get_terms,
    delete_term,
    get_term_count,
    add_chunk,
    get_chunks,
    get_all_chapters,
    update_chunk_status,
    get_chunks_by_status,
    GLOSSARY_SCHEMA_VERSION,
    CHUNKS_SCHEMA_VERSION,
)


class TestGlossaryInit:
    def test_creates_glossary_table(self, tmp_path):
        db = tmp_path / 'glossary.db'
        init_glossary_db(db)
        with connection(db) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert 'glossary' in tables

    def test_sets_schema_version(self, tmp_path):
        db = tmp_path / 'glossary.db'
        init_glossary_db(db)
        with connection(db) as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
        assert version == GLOSSARY_SCHEMA_VERSION

    def test_idempotent_does_not_drop_data(self, tmp_path):
        db = tmp_path / 'glossary.db'
        init_glossary_db(db)
        add_term(db, 'キリト', 'Кирито')
        init_glossary_db(db)  # Call again
        terms = get_terms(db)
        assert len(terms) == 1

    def test_creates_parent_dirs(self, tmp_path):
        db = tmp_path / 'subdir' / 'glossary.db'
        init_glossary_db(db)
        assert db.is_file()


class TestChunksInit:
    def test_creates_chunks_table(self, tmp_path):
        db = tmp_path / 'chunks.db'
        init_chunks_db(db)
        with connection(db) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert 'chunks' in tables

    def test_sets_schema_version(self, tmp_path):
        db = tmp_path / 'chunks.db'
        init_chunks_db(db)
        with connection(db) as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
        assert version == CHUNKS_SCHEMA_VERSION

    def test_idempotent(self, tmp_path):
        db = tmp_path / 'chunks.db'
        init_chunks_db(db)
        add_chunk(db, 'chapter-01', 0, 'source text')
        init_chunks_db(db)  # Call again
        chunks = get_chunks(db, 'chapter-01')
        assert len(chunks) == 1


class TestGlossaryOperations:
    @pytest.fixture
    def glossary_db(self, tmp_path):
        db = tmp_path / 'glossary.db'
        init_glossary_db(db)
        return db

    def test_add_and_get_term(self, glossary_db):
        add_term(glossary_db, 'キリト', 'Кирито')
        terms = get_terms(glossary_db)
        assert len(terms) == 1
        assert terms[0]['term_source'] == 'キリト'
        assert terms[0]['term_target'] == 'Кирито'

    def test_get_terms_ordered_alphabetically(self, glossary_db):
        add_term(glossary_db, 'キリト', 'Кирито')
        add_term(glossary_db, 'アスナ', 'Асуна')
        terms = get_terms(glossary_db)
        assert terms[0]['term_source'] == 'アスナ'
        assert terms[1]['term_source'] == 'キリト'

    def test_add_term_upsert_updates_translation(self, glossary_db):
        add_term(glossary_db, 'キリト', 'Кирито')
        add_term(glossary_db, 'キリト', 'Кирито (исправлено)')
        terms = get_terms(glossary_db)
        assert len(terms) == 1
        assert terms[0]['term_target'] == 'Кирито (исправлено)'

    def test_add_term_with_comment(self, glossary_db):
        add_term(glossary_db, 'キリト', 'Кирито', comment='Главный герой')
        terms = get_terms(glossary_db)
        assert terms[0]['comment'] == 'Главный герой'

    def test_add_term_different_lang_pair(self, glossary_db):
        add_term(glossary_db, 'sword', 'меч', source_lang='en', target_lang='ru')
        add_term(glossary_db, 'キリト', 'Кирито', source_lang='ja', target_lang='ru')
        ja_terms = get_terms(glossary_db, 'ja', 'ru')
        en_terms = get_terms(glossary_db, 'en', 'ru')
        assert len(ja_terms) == 1
        assert len(en_terms) == 1

    def test_get_terms_filters_by_lang_pair(self, glossary_db):
        add_term(glossary_db, 'test', 'тест', source_lang='en', target_lang='ru')
        # Default lang pair is ja->ru, should not return en->ru terms
        ja_terms = get_terms(glossary_db)
        assert len(ja_terms) == 0

    def test_delete_term(self, glossary_db):
        add_term(glossary_db, 'キリト', 'Кирито')
        deleted = delete_term(glossary_db, 'キリト')
        assert deleted is True
        assert len(get_terms(glossary_db)) == 0

    def test_delete_nonexistent_returns_false(self, glossary_db):
        result = delete_term(glossary_db, 'nonexistent')
        assert result is False

    def test_get_term_count(self, glossary_db):
        add_term(glossary_db, 'キリト', 'Кирито')
        add_term(glossary_db, 'アスナ', 'Асуна')
        assert get_term_count(glossary_db) == 2

    def test_get_term_count_filters_lang(self, glossary_db):
        add_term(glossary_db, 'test', 'тест', source_lang='en', target_lang='ru')
        assert get_term_count(glossary_db, 'ja', 'ru') == 0
        assert get_term_count(glossary_db, 'en', 'ru') == 1


class TestChunkOperations:
    @pytest.fixture
    def chunks_db(self, tmp_path):
        db = tmp_path / 'chunks.db'
        init_chunks_db(db)
        return db

    def test_add_and_get_chunk(self, chunks_db):
        add_chunk(chunks_db, 'chapter-01', 0, 'source text')
        chunks = get_chunks(chunks_db, 'chapter-01')
        assert len(chunks) == 1
        assert chunks[0]['content_source'] == 'source text'
        assert chunks[0]['status'] == 'discovery_pending'

    def test_composite_key_prevents_collision(self, chunks_db):
        # Same index, different chapters — both should exist
        add_chunk(chunks_db, 'prologue', 0, 'prologue source')
        add_chunk(chunks_db, 'chapter-01', 0, 'chapter source')
        prologue_chunks = get_chunks(chunks_db, 'prologue')
        chapter_chunks = get_chunks(chunks_db, 'chapter-01')
        assert len(prologue_chunks) == 1
        assert len(chapter_chunks) == 1

    def test_get_chunks_ordered_by_index(self, chunks_db):
        add_chunk(chunks_db, 'chapter-01', 2, 'third')
        add_chunk(chunks_db, 'chapter-01', 0, 'first')
        add_chunk(chunks_db, 'chapter-01', 1, 'second')
        chunks = get_chunks(chunks_db, 'chapter-01')
        assert [c['chunk_index'] for c in chunks] == [0, 1, 2]

    def test_get_chunks_only_returns_requested_chapter(self, chunks_db):
        add_chunk(chunks_db, 'chapter-01', 0, 'ch1')
        add_chunk(chunks_db, 'chapter-02', 0, 'ch2')
        chunks = get_chunks(chunks_db, 'chapter-01')
        assert len(chunks) == 1
        assert chunks[0]['content_source'] == 'ch1'

    def test_add_chunk_upsert(self, chunks_db):
        add_chunk(chunks_db, 'ch', 0, 'original', status='discovery_pending')
        add_chunk(chunks_db, 'ch', 0, 'original', 'translated', status='translation_done')
        chunks = get_chunks(chunks_db, 'ch')
        assert len(chunks) == 1
        assert chunks[0]['status'] == 'translation_done'

    def test_get_all_chapters(self, chunks_db):
        add_chunk(chunks_db, 'chapter-01', 0)
        add_chunk(chunks_db, 'prologue', 0)
        add_chunk(chunks_db, 'chapter-02', 0)
        chapters = get_all_chapters(chunks_db)
        assert chapters == ['chapter-01', 'chapter-02', 'prologue']

    def test_update_chunk_status(self, chunks_db):
        add_chunk(chunks_db, 'ch', 0, status='discovery_pending')
        update_chunk_status(chunks_db, 'ch', 0, 'translation_done')
        chunks = get_chunks(chunks_db, 'ch')
        assert chunks[0]['status'] == 'translation_done'

    def test_get_chunks_by_status(self, chunks_db):
        add_chunk(chunks_db, 'ch', 0, status='discovery_pending')
        add_chunk(chunks_db, 'ch', 1, status='translation_done')
        add_chunk(chunks_db, 'ch', 2, status='discovery_pending')
        pending = get_chunks_by_status(chunks_db, 'ch', 'discovery_pending')
        assert len(pending) == 2
        done = get_chunks_by_status(chunks_db, 'ch', 'translation_done')
        assert len(done) == 1

    def test_get_empty_chapter_returns_empty_list(self, chunks_db):
        chunks = get_chunks(chunks_db, 'nonexistent')
        assert chunks == []
