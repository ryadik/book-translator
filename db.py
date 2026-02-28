"""
Database layer for book-translator.

Two separate SQLite databases:
- glossary.db: Series-wide glossary (one per series, at series root)
- chunks.db: Per-volume translation state (one per volume, at volume/.state/)

Both databases use PRAGMA user_version for schema versioning.
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

GLOSSARY_SCHEMA_VERSION = 1
CHUNKS_SCHEMA_VERSION = 1


@contextmanager
def connection(db_path: Path):
    """Open a WAL-mode SQLite connection as a context manager.
    
    WAL mode must be enabled on a real file path (not :memory:).
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    if str(db_path) != ':memory:':
        conn.execute('PRAGMA journal_mode = WAL')
    try:
        yield conn
    finally:
        conn.close()


def init_glossary_db(db_path: Path) -> None:
    """Initialize glossary database with schema version 1.
    
    Idempotent: safe to call multiple times. Does not drop existing data.
    
    Schema:
        glossary(id, term_source, term_target, source_lang, target_lang, comment, created_at)
        UNIQUE(term_source, source_lang, target_lang)
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connection(db_path) as conn:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version == 0:
            conn.executescript(f'''
                CREATE TABLE IF NOT EXISTS glossary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    term_source TEXT NOT NULL,
                    term_target TEXT NOT NULL,
                    source_lang TEXT NOT NULL DEFAULT 'ja',
                    target_lang TEXT NOT NULL DEFAULT 'ru',
                    comment TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(term_source, source_lang, target_lang)
                );
                PRAGMA user_version = {GLOSSARY_SCHEMA_VERSION};
            ''')


def init_chunks_db(db_path: Path) -> None:
    """Initialize chunks database with schema version 1.
    
    Idempotent: safe to call multiple times. Does not drop existing data.
    
    Schema:
        chunks(id, chapter_name, chunk_index, content_source, content_target, status, updated_at)
        UNIQUE(chapter_name, chunk_index)
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connection(db_path) as conn:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version == 0:
            conn.executescript(f'''
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_name TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content_source TEXT,
                    content_target TEXT,
                    status TEXT NOT NULL DEFAULT 'discovery_pending',
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(chapter_name, chunk_index)
                );
                PRAGMA user_version = {CHUNKS_SCHEMA_VERSION};
            ''')


# ─────────────────────────────────────────────────────────────────────────────
# Glossary operations
# ─────────────────────────────────────────────────────────────────────────────

def add_term(
    db_path: Path,
    term_source: str,
    term_target: str,
    source_lang: str = 'ja',
    target_lang: str = 'ru',
    comment: str = '',
) -> None:
    """Insert or replace a glossary term (upsert semantics).
    
    If a term with the same (term_source, source_lang, target_lang) exists,
    it is replaced entirely.
    """
    with connection(db_path) as conn:
        conn.execute(
            '''
            INSERT OR REPLACE INTO glossary
                (term_source, term_target, source_lang, target_lang, comment)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (term_source, term_target, source_lang, target_lang, comment),
        )
        conn.commit()


def get_terms(
    db_path: Path,
    source_lang: str = 'ja',
    target_lang: str = 'ru',
) -> List[Dict[str, Any]]:
    """Return all glossary terms for a language pair, ordered by term_source."""
    with connection(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT term_source, term_target, source_lang, target_lang, comment
            FROM glossary
            WHERE source_lang = ? AND target_lang = ?
            ORDER BY term_source
            ''',
            (source_lang, target_lang),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_term(
    db_path: Path,
    term_source: str,
    source_lang: str = 'ja',
    target_lang: str = 'ru',
) -> bool:
    """Delete a term. Returns True if a row was deleted."""
    with connection(db_path) as conn:
        cursor = conn.execute(
            'DELETE FROM glossary WHERE term_source = ? AND source_lang = ? AND target_lang = ?',
            (term_source, source_lang, target_lang),
        )
        conn.commit()
    return cursor.rowcount > 0


def get_term_count(db_path: Path, source_lang: str = 'ja', target_lang: str = 'ru') -> int:
    """Return the number of glossary terms for a language pair."""
    with connection(db_path) as conn:
        row = conn.execute(
            'SELECT COUNT(*) FROM glossary WHERE source_lang = ? AND target_lang = ?',
            (source_lang, target_lang),
        ).fetchone()
    return row[0]


# ─────────────────────────────────────────────────────────────────────────────
# Chunk operations
# ─────────────────────────────────────────────────────────────────────────────

def add_chunk(
    db_path: Path,
    chapter_name: str,
    chunk_index: int,
    content_source: Optional[str] = None,
    content_target: Optional[str] = None,
    status: str = 'discovery_pending',
) -> None:
    """Insert or replace a chunk (upsert semantics)."""
    with connection(db_path) as conn:
        conn.execute(
            '''
            INSERT OR REPLACE INTO chunks
                (chapter_name, chunk_index, content_source, content_target, status)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (chapter_name, chunk_index, content_source, content_target, status),
        )
        conn.commit()


def get_chunks(
    db_path: Path,
    chapter_name: str,
) -> List[Dict[str, Any]]:
    """Return all chunks for a chapter, ordered by chunk_index."""
    with connection(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT chapter_name, chunk_index, content_source, content_target, status
            FROM chunks
            WHERE chapter_name = ?
            ORDER BY chunk_index
            ''',
            (chapter_name,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_chapters(db_path: Path) -> List[str]:
    """Return a sorted list of all unique chapter names in the chunks DB."""
    with connection(db_path) as conn:
        rows = conn.execute(
            'SELECT DISTINCT chapter_name FROM chunks ORDER BY chapter_name'
        ).fetchall()
    return [r[0] for r in rows]


def update_chunk_status(
    db_path: Path,
    chapter_name: str,
    chunk_index: int,
    status: str,
) -> None:
    """Update the status of a specific chunk."""
    with connection(db_path) as conn:
        conn.execute(
            'UPDATE chunks SET status = ? WHERE chapter_name = ? AND chunk_index = ?',
            (status, chapter_name, chunk_index),
        )
        conn.commit()


def get_chunks_by_status(
    db_path: Path,
    chapter_name: str,
    status: str,
) -> List[Dict[str, Any]]:
    """Return chunks for a chapter that have the given status."""
    with connection(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT chapter_name, chunk_index, content_source, content_target, status
            FROM chunks
            WHERE chapter_name = ? AND status = ?
            ORDER BY chunk_index
            ''',
            (chapter_name, status),
        ).fetchall()
    return [dict(r) for r in rows]
