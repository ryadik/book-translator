# Book Translator — Project Context

## Project Overview

**Book Translator** is a CLI application for translating light novels, web novels, and other texts from any language to Russian using LLMs. It features a four-stage translation pipeline with support for multiple backends.

### Key Features
- **Dual LLM Backends**: Cloud (Gemini, Qwen) and local (Ollama) with runtime switching via TUI
- **Four-Stage Pipeline**: Discovery → Translation → Proofreading → Global Proofreading
- **Text-based UI**: Full-featured TUI built with Textual for managing translations
- **Glossary Management**: SQLite-backed terminology database with import/export
- **Batch Processing**: ThreadPoolExecutor with configurable workers and rate limiting
- **Resume Support**: Persistent state allows resuming interrupted translations

### Tech Stack
- **Python 3.11+** with modern type hints (`str | None`, `dict`, `list`)
- **Textual** for TUI, **Rich** for console output
- **SQLite** (WAL mode) for state persistence
- **Tenacity** for retry logic
- **ThreadPoolExecutor** for concurrent processing (default: 50 workers, 2 RPS)

---

## Project Structure

```
book-translator/
├── src/book_translator/          # Main package
│   ├── cli.py                    # Entry point (TUI launcher)
│   ├── orchestrator.py           # Pipeline orchestration
│   ├── llm_runner.py             # LLM backend wrappers
│   ├── db.py                     # SQLite operations
│   ├── discovery.py              # Configuration loading
│   ├── path_resolver.py          # Path resolution utilities
│   ├── chapter_splitter.py       # Text chunking logic
│   ├── term_collector.py         # Term extraction
│   ├── proofreader.py            # Diff application
│   ├── glossary_manager.py       # Glossary CRUD operations
│   ├── rate_limiter.py           # Rate limiting
│   ├── logger.py                 # Logging setup (3 loggers)
│   ├── log_viewer.py             # Log file management
│   ├── exceptions.py             # Custom exceptions
│   ├── languages.py              # Language utilities
│   ├── utils.py                  # JSON parsing helpers
│   ├── default_prompts.py        # Prompt templates
│   ├── convert_to_docx.py        # DOCX export
│   ├── convert_to_epub.py        # EPUB export
│   ├── textual_app/              # TUI application
│   │   ├── app.py                # Main Textual app
│   │   ├── app.tcss              # Styles
│   │   ├── messages.py           # Custom events
│   │   ├── screens/              # Screen components
│   │   └── widgets/              # Reusable widgets
│   └── data/
│       ├── prompts/              # Bundled prompt templates
│       └── style_guides/         # Language-pair style guides
├── tests/                        # Pytest test suite
├── docs/                         # Documentation
├── pyproject.toml                # Build configuration
└── README.md                     # User documentation
```

---

## Building and Running

### Installation

```bash
# Development install
pip install -e ".[dev]"

# Production install
pipx install .
```

### Running the Application

```bash
# Launch TUI (main interface)
book-translator

# CLI commands (from AGENTS.md)
book-translator init "Series Name" --source-lang ja --target-lang ru
book-translator translate volume-01/source/chapter1.txt
book-translator translate-all [--force | --resume] [--dry-run]
book-translator glossary export --output terms.tsv
book-translator status
```

### Running Tests

```bash
pytest                              # Run all tests
pytest -v                           # Verbose output
pytest tests/test_db.py             # Single file
pytest --cov=src/book_translator    # With coverage
```

---

## Development Conventions

### Python Style
- **Type hints required** on all function parameters and return values
- **Modern syntax**: `str | None` (not `Optional`), `dict`/`list` (not `Dict`/`List`)
- **Absolute imports only**: `from book_translator.db import connection`
- **Import order**: stdlib → third-party → local (blank line between groups)
- **Naming**: `snake_case` functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants

### Example Import Block
```python
import sqlite3
from pathlib import Path
from contextlib import contextmanager

from rich.console import Console

from book_translator.logger import system_logger
from book_translator.exceptions import TranslationLockedError
```

### Error Handling
- Custom exceptions in `exceptions.py` (`TranslationLockedError`, `CancellationError`)
- Use specific exception types; avoid bare `except:`
- Database operations use `connection()` context manager from `db.py`

### Logging
Three loggers from `logger.py`:
- `system_logger`: Orchestration, user-facing messages (**Russian**)
- `input_logger`: LLM input logging
- `output_logger`: LLM output logging

**User-facing messages in Russian**, technical comments in English.

### Database Patterns
- Two SQLite databases: `glossary.db` (series-wide), `chunks.db` (per-volume)
- WAL mode enabled, foreign keys ON
- Schema versioning via `PRAGMA user_version`
- Always use `connection()` context manager

### Testing
- Class-based tests with `pytest`
- Use `tmp_path` fixture for filesystem operations
- Test files: `test_*.py` in `tests/`

---

## Architecture

### Pipeline Stages
1. **Discovery**: Extract terms from source text, collect for glossary approval
2. **Translation**: Translate chunks with glossary and context
3. **Proofreading**: Per-chunk review and correction
4. **Global Proofreading**: Whole-chapter consistency pass with structured diffs

### Concurrency Model
- `ThreadPoolExecutor` with configurable workers (default: 50)
- `RateLimiter` for API rate limiting (default: 2 RPS)
- Chapter-level locking to prevent concurrent modification
- Atomic stage transitions via `promote_chapter_stage()`

### LLM Backends
- **Gemini**: Cloud via `gemini-cli` subprocess
- **Qwen**: Cloud via `qwen-code` CLI subprocess  
- **Ollama**: Local via HTTP to `localhost:11434`

Backend selection in `book-translator.toml`:
```toml
[llm]
backend = "ollama"  # or "gemini" or "qwen"
```

### Configuration File (`book-translator.toml`)
```toml
[series]
name = "My Series"
source_lang = "ja"
target_lang = "ru"

[llm]
backend = "ollama"
ollama_url = "http://localhost:11434"

[llm.models]
discovery = "qwen3:8b"
translation = "qwen3:30b-a3b"
proofreading = "qwen3:30b-a3b"
global_proofreading = "qwen3:14b"

[workers]
max_concurrent = 50
max_rps = 2.0

[splitter]
target_chunk_size = 600
max_part_chars = 800
min_chunk_size = 300
```

---

## Series Directory Structure

```
MySeries/
├── book-translator.toml      # Configuration
├── glossary.db               # Series-wide glossary
├── world_info.md             # World-building context
├── style_guide.md            # Translation style guide
├── prompts/                  # Custom prompts (override defaults)
└── volume-01/
    ├── source/               # Source .txt files
    ├── output/               # Translated output
    └── .state/
        ├── chunks.db         # Per-volume translation state
        └── logs/             # Run logs
```

---

## Key Modules

### `orchestrator.py`
Core pipeline orchestration:
- `run_translation_process()`: Main entry point
- `_run_workers_pooled()`: Parallel chunk processing
- `_run_global_proofreading()`: Final consistency pass
- Stage management via `chapter_state` table

### `db.py`
Database operations with schema versioning:
- Glossary: `add_term()`, `get_terms()`
- Chunks: `add_chunk()`, `get_chunks()`, `update_chunk_status()`
- Chapter state: `set_chapter_stage()`, `get_chapter_stage()`, `promote_chapter_stage()`

### `llm_runner.py`
LLM backend wrappers with retry logic:
- `run_gemini()`, `run_qwen()`, `run_ollama()`
- `run_llm()`: Backend dispatcher
- `cancel_all()`, `reset_cancellation()`: Cancellation handling
- Pre-flight checks: `check_ollama_connection()`, `check_gemini_binary()`

### `textual_app/`
TUI components:
- `app.py`: Main Textual application
- `screens/dashboard.py`: Series overview
- `screens/glossary.py`: Term management
- `screens/translation.py`: Translation progress
- `messages.py`: Custom events (`TUILogRecord`, `ConfirmRequest`)

---

## Common Tasks

### Adding a New Prompt Template
1. Add template file to `src/book_translator/data/prompts/`
2. Reference in `default_prompts.py`
3. Use `path_resolver.resolve_prompt()` to load (supports user overrides)

### Adding a New LLM Backend
1. Implement backend wrapper in `llm_runner.py`
2. Add backend selection logic in `orchestrator.py`
3. Add pre-flight check function
4. Update `discovery.py` for configuration

### Database Schema Migration
1. Increment `CHUNKS_SCHEMA_VERSION` or `GLOSSARY_SCHEMA_VERSION`
2. Add migration logic in `init_chunks_db()` or `init_glossary_db()`
3. Use `PRAGMA user_version` to detect current version

### Testing Guidelines
- Use `tmp_path` for filesystem isolation
- Test database operations with in-memory or temp files
- Mock LLM calls in unit tests
- Class-based test structure for organization

---

## References

- **AGENTS.md**: Development guidelines and conventions
- **README.md**: User documentation and setup instructions
- **CHANGELOG.md**: Version history and changes
- **docs/**: Architecture deep-dives and API documentation
