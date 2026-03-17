# Agent Guidelines for book-translator

## Build / Test / Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Install in editable mode (for development)
pip install -e .

# Run all tests
pytest

# Run a single test file
pytest tests/test_db.py

# Run a single test class
pytest tests/test_db.py::TestGlossaryInit

# Run a single test method
pytest tests/test_db.py::TestGlossaryInit::test_creates_glossary_table

# Run with verbose output
pytest -v

# Run with coverage (if pytest-cov installed)
pytest --cov=src/book_translator

# Run the CLI
book-translator --help

# Run specific CLI command
book-translator init "Test Series" --source-lang ja --target-lang ru
```

## Code Style Guidelines

### Python Version
- **Python 3.11+** required
- Use modern syntax: `str | None` instead of `Optional[str]`
- Use `match`/`case` where appropriate

### Imports
- Group imports: stdlib → third-party → local
- Use absolute imports for local modules: `from book_translator.db import connection`
- Avoid relative imports (`from .db import`)
- Lazy imports allowed in CLI commands (see `cli.py`)

### Type Hints
- All function parameters and return types must be annotated
- Use `from __future__ import annotations` for forward references
- Use `Path` from `pathlib` for file paths
- Use `dict`, `list` instead of `Dict`, `List` (Python 3.9+)

### Naming Conventions
- `snake_case` for functions, variables, methods
- `PascalCase` for classes
- `UPPER_CASE` for constants
- Private functions prefix with underscore: `_run_single_worker`
- Module names: lowercase with underscores

### Error Handling
- Use exceptions, not error codes
- Use `try/except` with specific exceptions
- Log errors with `logger.exception()` or `logger.error()`
- Use `tenacity` for retry logic on external calls
- Always clean up resources in `finally` blocks

### Database (SQLite)
- Use WAL mode: `PRAGMA journal_mode = WAL`
- Enable foreign keys: `PRAGMA foreign_keys = ON`
- Use `connection()` context manager from `db.py`
- Schema versioning via `PRAGMA user_version`

### Concurrency
- Use `ThreadPoolExecutor` for parallel processing
- Use `RateLimiter` class for API rate limiting
- Thread-safe code required for shared state

### Logging
- Use module-level loggers from `logger.py`
- `system_logger` for orchestration messages
- `input_logger` / `output_logger` for LLM I/O
- Log in Russian for user-facing messages

### Testing
- Use `pytest` with class-based test organization
- Use `tmp_path` fixture for filesystem tests
- Use fixtures for common setup (see `test_db.py`)
- Test both success and error cases

### Project Structure
```
src/book_translator/     # Source code
  commands/              # CLI subcommands
  *.py                   # Core modules
tests/                   # Test files
  test_*.py              # One test file per module
```

### Configuration
- Series config in `book-translator.toml`
- Prompts in `prompts/` directory
- State in `.state/` (per-volume)
- Glossary in `glossary.db` (per-series)

### Documentation
- Docstrings for public functions (Google style)
- Comments in Russian for business logic
- Comments in English for technical details
