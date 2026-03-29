"""
Database layer for book-translator.

Two separate SQLite databases:
- glossary.db: Series-wide glossary (one per series, at series root)
- chunks.db: Per-volume translation state (one per volume, at volume/.state/)

Both databases use PRAGMA user_version for schema versioning.

Schema Versions:
- chunks v1: initial (chunks table only)
- chunks v2: added chapter_state table for pipeline stage tracking
"""
import sqlite3
from pathlib import Path
from typing import Any
from contextlib import contextmanager

GLOSSARY_SCHEMA_VERSION = 1
CHUNKS_SCHEMA_VERSION = 2


@contextmanager
def connection(db_path: Path):
    """Open a WAL-mode SQLite connection as a context manager.
    
    WAL mode must be enabled on a real file path (not :memory:).
    """
    conn = sqlite3.connect(str(db_path), timeout=30)
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
    """Initialize chunks database.

    Idempotent: safe to call multiple times. Does not drop existing data.
    Applies schema migrations if current version is behind CHUNKS_SCHEMA_VERSION.

    Schema v1:
        chunks(id, chapter_name, chunk_index, content_source, content_target, status, updated_at)
    Schema v2:
        + chapter_state(chapter_name TEXT PRIMARY KEY, pipeline_stage TEXT, updated_at TEXT)
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connection(db_path) as conn:
        current_version = conn.execute('PRAGMA user_version').fetchone()[0]

        if current_version < 1:
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
            ''')

        if current_version < 2:
            conn.executescript(f'''
                CREATE TABLE IF NOT EXISTS chapter_state (
                    chapter_name TEXT PRIMARY KEY,
                    pipeline_stage TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
            ''')

        conn.execute(f'PRAGMA user_version = {CHUNKS_SCHEMA_VERSION}')
        conn.commit()


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
    """Insert or update a glossary term (upsert semantics).

    If a term with the same (term_source, source_lang, target_lang) exists,
    only term_target and comment are updated — id and created_at are preserved.
    """
    with connection(db_path) as conn:
        conn.execute(
            '''
            INSERT INTO glossary
                (term_source, term_target, source_lang, target_lang, comment)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(term_source, source_lang, target_lang) DO UPDATE SET
                term_target = excluded.term_target,
                comment     = excluded.comment
            ''',
            (term_source, term_target, source_lang, target_lang, comment),
        )
        conn.commit()


def get_terms(
    db_path: Path,
    source_lang: str = 'ja',
    target_lang: str = 'ru',
) -> list[dict[str, Any]]:
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



# ─────────────────────────────────────────────────────────────────────────────
# Chunk operations
# ─────────────────────────────────────────────────────────────────────────────

def add_chunk(
    db_path: Path,
    chapter_name: str,
    chunk_index: int,
    content_source: str | None = None,
    content_target: str | None = None,
    status: str = 'discovery_pending',
) -> None:
    """Insert or update a chunk (upsert semantics).

    If a chunk with the same (chapter_name, chunk_index) exists,
    only content_source, content_target and status are updated — id is preserved.
    """
    with connection(db_path) as conn:
        conn.execute(
            '''
            INSERT INTO chunks
                (chapter_name, chunk_index, content_source, content_target, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chapter_name, chunk_index) DO UPDATE SET
                content_source = excluded.content_source,
                content_target = excluded.content_target,
                status         = excluded.status,
                updated_at     = datetime('now')
            ''',
            (chapter_name, chunk_index, content_source, content_target, status),
        )
        conn.commit()


def get_chunks(
    db_path: Path,
    chapter_name: str,
) -> list[dict[str, Any]]:
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


def get_all_chapters(db_path: Path) -> list[str]:
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
    """Update the status of a specific chunk without touching content."""
    with connection(db_path) as conn:
        conn.execute(
            "UPDATE chunks SET status = ?, updated_at = datetime('now') WHERE chapter_name = ? AND chunk_index = ?",
            (status, chapter_name, chunk_index),
        )
        conn.commit()


def update_chunk_content(
    db_path: Path,
    chapter_name: str,
    chunk_index: int,
    content_target: str,
    status: str,
) -> None:
    """Update translated content and status of a specific chunk."""
    with connection(db_path) as conn:
        conn.execute(
            "UPDATE chunks SET content_target = ?, status = ?, updated_at = datetime('now') WHERE chapter_name = ? AND chunk_index = ?",
            (content_target, status, chapter_name, chunk_index),
        )
        conn.commit()


def batch_update_chunks_content(
    db_path: Path,
    chapter_name: str,
    updates: list[dict],
) -> None:
    """Atomically update content_target and status for multiple chunks.

    Each dict in updates must have: chunk_index, content_target, status.
    All updates are committed in a single transaction.
    """
    with connection(db_path) as conn:
        for u in updates:
            conn.execute(
                'UPDATE chunks SET content_target = ?, status = ?, updated_at = datetime(\'now\') '
                'WHERE chapter_name = ? AND chunk_index = ?',
                (u['content_target'], u['status'], chapter_name, u['chunk_index']),
            )
        conn.commit()


def batch_update_chunk_statuses(
    db_path: Path,
    chapter_name: str,
    updates: list[tuple[int, str]],
) -> None:
    """Atomically update status for multiple chunks in a single transaction.

    Args:
        db_path: Path to chunks.db.
        chapter_name: Chapter whose chunks are being updated.
        updates: List of (chunk_index, new_status) tuples.

    All updates commit together — partial application on crash is impossible.
    """
    with connection(db_path) as conn:
        for chunk_index, new_status in updates:
            conn.execute(
                "UPDATE chunks SET status = ?, updated_at = datetime('now') "
                "WHERE chapter_name = ? AND chunk_index = ?",
                (new_status, chapter_name, chunk_index),
            )
        conn.commit()


def clear_chapter(db_path: Path, chapter_name: str) -> None:
    """Delete all chunks and chapter_state records for a specific chapter."""
    with connection(db_path) as conn:
        conn.execute('DELETE FROM chunks WHERE chapter_name = ?', (chapter_name,))
        conn.execute('DELETE FROM chapter_state WHERE chapter_name = ?', (chapter_name,))
        conn.commit()


def clear_chapter_state(db_path: Path, chapter_name: str) -> None:
    """Delete only chapter_state for a specific chapter."""
    with connection(db_path) as conn:
        conn.execute('DELETE FROM chapter_state WHERE chapter_name = ?', (chapter_name,))
        conn.commit()



def get_chunk_status_counts(
    db_path: Path,
    chapter_name: str,
) -> dict[str, int]:
    """Return chunk counts grouped by status for a chapter."""
    with connection(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT status, COUNT(*) AS count
            FROM chunks
            WHERE chapter_name = ?
            GROUP BY status
            ''',
            (chapter_name,),
        ).fetchall()
    return {str(r['status']): int(r['count']) for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# Chapter pipeline state operations
# ─────────────────────────────────────────────────────────────────────────────

VALID_STAGES = frozenset({'discovery', 'translation', 'proofreading', 'global_proofreading', 'complete'})


def set_chapter_stage(db_path: Path, chapter_name: str, stage: str) -> None:
    """Set the current pipeline stage for a chapter.

    Valid stages: 'discovery', 'translation', 'proofreading',
                  'global_proofreading', 'complete'
    """
    if stage not in VALID_STAGES:
        raise ValueError(f"Invalid stage: {stage!r}. Must be one of {sorted(VALID_STAGES)}")
    with connection(db_path) as conn:
        conn.execute(
            '''
            INSERT INTO chapter_state (chapter_name, pipeline_stage, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(chapter_name) DO UPDATE
            SET pipeline_stage = excluded.pipeline_stage,
                updated_at = excluded.updated_at
            ''',
            (chapter_name, stage),
        )
        conn.commit()


def get_chapter_stage(db_path: Path, chapter_name: str) -> str | None:
    """Get the current pipeline stage for a chapter.

    Returns None if the chapter has not been started yet.
    """
    with connection(db_path) as conn:
        row = conn.execute(
            'SELECT pipeline_stage FROM chapter_state WHERE chapter_name = ?',
            (chapter_name,),
        ).fetchone()
    return row[0] if row else None


def reset_chapter_stage(
    db_path: Path,
    chapter_name: str,
    to_stage: str,
    chunk_status: str,
) -> None:
    """Reset pipeline to a given stage by updating chapter_state and chunk statuses.

    Args:
        db_path: Path to chunks.db
        chapter_name: Chapter to reset
        to_stage: The stage to rewind to (e.g. 'discovery')
        chunk_status: Status to assign to all chunks (e.g. 'discovery_pending')
    """
    with connection(db_path) as conn:
        conn.execute(
            "UPDATE chunks SET status = ?, updated_at = datetime('now') WHERE chapter_name = ?",
            (chunk_status, chapter_name),
        )
        conn.execute(
            '''
            INSERT INTO chapter_state (chapter_name, pipeline_stage, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(chapter_name) DO UPDATE
            SET pipeline_stage = excluded.pipeline_stage,
                updated_at = excluded.updated_at
            ''',
            (chapter_name, to_stage),
        )
        conn.commit()


def promote_chapter_stage(
    db_path: Path,
    chapter_name: str,
    next_stage: str,
    expected_statuses: set[str],
    status_mapping: dict[str, str] | None = None,
) -> None:
    """Atomically validate chunk statuses, update them, and advance chapter stage.

    Args:
        db_path: Path to chunks.db.
        chapter_name: Chapter to promote.
        next_stage: Stage to write into chapter_state.
        expected_statuses: All chunk statuses must belong to this set.
        status_mapping: Optional {old_status: new_status} updates applied before
            advancing chapter_state.

    Raises:
        RuntimeError: If chapter has no chunks or contains unexpected statuses.
        ValueError: If next_stage is invalid.
    """
    if next_stage not in VALID_STAGES:
        raise ValueError(f"Invalid stage: {next_stage!r}. Must be one of {sorted(VALID_STAGES)}")

    with connection(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT status, COUNT(*) AS count
            FROM chunks
            WHERE chapter_name = ?
            GROUP BY status
            ''',
            (chapter_name,),
        ).fetchall()

        if not rows:
            raise RuntimeError(f"Cannot promote chapter {chapter_name!r}: no chunks found")

        status_counts = {str(r['status']): int(r['count']) for r in rows}
        unexpected = {
            status: count
            for status, count in status_counts.items()
            if status not in expected_statuses
        }
        if unexpected:
            raise RuntimeError(
                f"Cannot promote chapter {chapter_name!r} to {next_stage!r}: "
                f"unexpected chunk statuses: {unexpected}"
            )

        for from_status, to_status in (status_mapping or {}).items():
            conn.execute(
                '''
                UPDATE chunks
                SET status = ?, updated_at = datetime('now')
                WHERE chapter_name = ? AND status = ?
                ''',
                (to_status, chapter_name, from_status),
            )

        conn.execute(
            '''
            INSERT INTO chapter_state (chapter_name, pipeline_stage, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(chapter_name) DO UPDATE
            SET pipeline_stage = excluded.pipeline_stage,
                updated_at = excluded.updated_at
            ''',
            (chapter_name, next_stage),
        )
        conn.commit()
