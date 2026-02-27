import sqlite3
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

def get_connection(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if db_path != ":memory:":
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.OperationalError:
            pass
    return conn

@contextmanager
def connection_context(db_path: str, conn: Optional[sqlite3.Connection] = None):
    if conn:
        yield conn
    else:
        c = get_connection(db_path)
        try:
            yield c
        finally:
            c.close()

def init_db(db_path: str, conn: Optional[sqlite3.Connection] = None):
    """Initializes the database with glossary and chunks tables."""
    with connection_context(db_path, conn) as c:
        with c:
            # Glossary table
            c.execute("""
                CREATE TABLE IF NOT EXISTS glossary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT,
                    term_jp TEXT,
                    term_ru TEXT,
                    UNIQUE(project_id, term_jp)
                )
            """)
            
            # Chunks table
            c.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT,
                    chunk_index INTEGER,
                    content_jp TEXT,
                    content_ru TEXT,
                    status TEXT,
                    UNIQUE(project_id, chunk_index)
                )
            """)

def add_term(db_path: str, project_id: str, term_jp: str, term_ru: str, conn: Optional[sqlite3.Connection] = None):
    """Inserts or replaces a term in the glossary."""
    with connection_context(db_path, conn) as c:
        with c:
            c.execute("""
                INSERT OR REPLACE INTO glossary (project_id, term_jp, term_ru)
                VALUES (?, ?, ?)
            """, (project_id, term_jp, term_ru))

def get_terms(db_path: str, project_id: str, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, str]]:
    """Returns all terms for a project as a list of dictionaries."""
    with connection_context(db_path, conn) as c:
        cursor = c.execute("""
            SELECT term_jp, term_ru FROM glossary WHERE project_id = ?
        """, (project_id,))
        return [dict(row) for row in cursor.fetchall()]

def add_chunk(db_path: str, project_id: str, chunk_index: int, content_jp: str, content_ru: Optional[str] = None, status: str = "pending", conn: Optional[sqlite3.Connection] = None):
    """Inserts or replaces a chunk."""
    with connection_context(db_path, conn) as c:
        with c:
            c.execute("""
                INSERT OR REPLACE INTO chunks (project_id, chunk_index, content_jp, content_ru, status)
                VALUES (?, ?, ?, ?, ?)
            """, (project_id, chunk_index, content_jp, content_ru, status))

def get_chunks(db_path: str, project_id: str, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    """Returns all chunks for a project."""
    with connection_context(db_path, conn) as c:
        cursor = c.execute("""
            SELECT chunk_index, content_jp, content_ru, status FROM chunks WHERE project_id = ? ORDER BY chunk_index
        """, (project_id,))
        return [dict(row) for row in cursor.fetchall()]
