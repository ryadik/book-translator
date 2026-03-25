# AGENTS.md

Guidelines for AI agents working in the book-translator repository.

## Commands

```bash
# Install (development)
pip install -e .
pip install -e ".[dev]"   # with test dependencies

# Run tests
pytest
pytest tests/test_db.py                                      # single file
pytest tests/test_db.py::TestGlossaryInit                   # single class
pytest tests/test_db.py::TestGlossaryInit::test_creates_glossary_table  # single test
pytest -v                                                    # verbose
pytest --cov=src/book_translator                             # with coverage

# CLI usage
book-translator --help
book-translator init "Series Name" --source-lang ja --target-lang ru
book-translator translate volume-01/source/chapter1.txt
book-translator translate-all [--force | --resume] [--dry-run]
book-translator glossary export --output terms.tsv
book-translator status
```

## Code Style

### Python Version
- **Python 3.11+** required
- Use modern syntax: `str | None` (not `Optional[str]`), `dict`/`list` (not `Dict`/`List`)
- Use `match`/`case` where it improves clarity

### Imports
- **Absolute only**: `from book_translator.db import connection` (no relative imports)
- Order: stdlib → third-party → local (each group separated by blank line)
- Example:
  ```python
  import sqlite3
  from pathlib import Path
  from contextlib import contextmanager

  from rich.console import Console

  from book_translator.logger import system_logger
  from book_translator.exceptions import TranslationLockedError
  ```

### Types
- All function parameters and return types must be annotated
- Use `Path` for filesystem paths
- Use `Any` sparingly; prefer specific types

### Naming
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private helpers: `_leading_underscore`

### Error Handling
- Custom exceptions in `exceptions.py`
- Use specific exceptions; avoid bare `except:`
- Database operations use `connection()` context manager

### Logging
- Three loggers from `logger.py`:
  - `system_logger`: orchestration, user-facing messages
  - `input_logger`: LLM input logging
  - `output_logger`: LLM output logging
- **User-facing messages in Russian**, technical comments in English

### Database
- Two SQLite databases: `glossary.db` (series-wide), `chunks.db` (per-volume)
- Always use `connection()` context manager from `db.py`
- WAL mode enabled, foreign keys ON
- Schema versions tracked via `PRAGMA user_version`

### Testing
- Class-based tests with `pytest`
- Use `tmp_path` fixture for filesystem operations
- Test files named `test_*.py` in `tests/` directory

## Architecture Notes

- Source layout: `src/book_translator/`
- Entry point: `book_translator.cli:main`
- Pipeline stages: discovery → translation → proofreading → global_proofreading
- ThreadPoolExecutor (50 workers) with RateLimiter (2 RPS)
