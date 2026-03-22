# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install in editable mode (development)
pip install -e .
pip install -e ".[dev]"   # with test dependencies

# Run tests
pytest
pytest tests/test_db.py                                      # single file
pytest tests/test_db.py::TestGlossaryInit                   # single class
pytest tests/test_db.py::TestGlossaryInit::test_creates_glossary_table  # single test
pytest -v                                                    # verbose
pytest --cov=src/book_translator                             # with coverage

# CLI
book-translator --help
book-translator init "Series Name" --source-lang ja --target-lang ru
book-translator translate volume-01/source/chapter1.txt
book-translator translate-all [--force | --resume] [--dry-run] [--stage {discovery,translation,proofreading,global_proofreading}]
book-translator glossary export --output terms.tsv
book-translator status
```

## Architecture

The project is a Python 3.11+ CLI that automates book translation using `gemini-cli` as the LLM subprocess. The source layout is `src/book_translator/` with an entry point at `book_translator.cli:main`.

### Directory hierarchy at runtime

```
<series-root>/          # contains book-translator.toml, glossary.db, prompts/
  volume-01/
    source/             # input .txt files
    output/             # translated .txt/.docx/.epub files
    .state/
      chunks.db         # per-volume chunk/chapter state
      .lock             # prevents concurrent runs
      logs/             # system/input/output logs
```

`discovery.py` walks upward from CWD to find `book-translator.toml` and load config with defaults.

### Two SQLite databases

- **`glossary.db`** (series-wide): stores translation terms `(term_source, term_target, source_lang, target_lang, comment)`. Schema v1.
- **`chunks.db`** (per-volume): stores chunk statuses and chapter pipeline stages. Schema v2 with migrations. Both use WAL mode and foreign keys ON. Always use the `connection()` context manager from `db.py`.

### Translation pipeline (orchestrator.py)

Four sequential stages per chapter, tracked in `chapter_state` table:

1. **Discovery** — splits chapter into chunks (`chapter_splitter.py`), runs parallel `gemini-cli` calls to discover new terminology, prompts user to confirm terms via TSV, writes to glossary.
2. **Translation** — translates all chunks in parallel, passing glossary context and the previous chunk for narrative continuity.
3. **Proofreading** — per-chunk quality pass.
4. **Global proofreading** — single LLM call on the assembled document; returns JSON diffs applied only on exact single matches.

Chunks have statuses: `discovery_pending → discovery_done → translation_done → reading_done`. `--resume` resets `*_in_progress`/`*_failed` to their prior state. `--force` clears all state. `--stage` restarts from a specific pipeline stage.

`ThreadPoolExecutor` (default 50 workers) parallelizes within each stage. `rate_limiter.py` enforces 2 RPS across all threads.

### Key modules

| Module | Responsibility |
|---|---|
| `orchestrator.py` | Main pipeline controller |
| `cli.py` / `commands/` | Argument parsing and subcommands |
| `db.py` | All SQLite operations |
| `discovery.py` | Config loading, series root resolution |
| `path_resolver.py` | Volume/chapter path resolution |
| `chapter_splitter.py` | Semantic chunking (~600 chars target) |
| `term_collector.py` | Parse LLM JSON, filter known terms, TSV workflow |
| `proofreader.py` | Apply JSON diff patches |
| `rate_limiter.py` | Thread-safe 2 RPS limiter |
| `tui.py` | Rich-based progress/status UI |
| `logger.py` | Three loggers: system, input, output |

## Code conventions

- **Python 3.11+**: use `str | None` not `Optional[str]`, `match`/`case` where appropriate
- **Imports**: stdlib → third-party → local; use absolute imports (`from book_translator.db import ...`), no relative imports
- **Types**: all function parameters and return types annotated; `Path` for filesystem paths; `dict`/`list` not `Dict`/`List`
- **Logging**: `system_logger` for orchestration, `input_logger`/`output_logger` for LLM I/O; user-facing log messages in Russian, technical comments in English
- **Tests**: class-based with `pytest`, use `tmp_path` fixture for filesystem tests
