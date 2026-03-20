"""
Series discovery module.
Implements walk-up algorithm to find book-translator.toml from CWD.
"""
from pathlib import Path
from typing import Optional

MARKER_FILE = "book-translator.toml"

# tomllib is stdlib in Python 3.11+, tomli for older versions
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


def find_series_root(start_dir: Optional[Path] = None) -> Path:
    """Walk up from start_dir (default: CWD) looking for book-translator.toml.
    
    Returns the directory containing the marker file.
    Raises FileNotFoundError if not found anywhere up to filesystem root.
    """
    if tomllib is None:
        raise ImportError(
            "tomllib/tomli not available. Install tomli: pip install tomli"
        )
    current = (start_dir or Path.cwd()).resolve()
    while current != current.parent:
        if (current / MARKER_FILE).is_file():
            return current
        current = current.parent
    raise FileNotFoundError(
        f"{MARKER_FILE} not found. Run `book-translator init` to create a series."
    )


def load_series_config(series_root: Path) -> dict:
    """Load and parse book-translator.toml with defaults applied.
    
    Args:
        series_root: Path to the directory containing book-translator.toml
    Returns:
        dict with merged config (file values + defaults)
    Raises:
        FileNotFoundError: if book-translator.toml doesn't exist
        ValueError: if required fields are missing
    """
    if tomllib is None:
        raise ImportError(
            "tomllib/tomli not available. Install tomli: pip install tomli"
        )
    toml_path = series_root / MARKER_FILE
    if not toml_path.is_file():
        raise FileNotFoundError(f"{MARKER_FILE} not found at {series_root}")
    
    with open(toml_path, 'rb') as f:
        config = tomllib.load(f)
    
    # Validate required fields
    if 'series' not in config:
        raise ValueError("Missing required [series] section in book-translator.toml")
    if 'name' not in config['series']:
        raise ValueError("Missing required 'name' field in [series] section")
    
    # Apply defaults
    config['series'].setdefault('source_lang', 'ja')
    config['series'].setdefault('target_lang', 'ru')
    
    if 'gemini_cli' not in config:
        config['gemini_cli'] = {}
    config['gemini_cli'].setdefault('model', 'gemini-2.5-pro')
    config['gemini_cli'].setdefault('worker_timeout_seconds', 120)
    config['gemini_cli'].setdefault('proofreading_timeout_seconds', 300)

    if 'retry' not in config:
        config['retry'] = {}
    config['retry'].setdefault('max_attempts', 3)
    config['retry'].setdefault('wait_min_seconds', 4)
    config['retry'].setdefault('wait_max_seconds', 10)

    if 'splitter' not in config:
        config['splitter'] = {}
    config['splitter'].setdefault('target_chunk_size', 600)
    config['splitter'].setdefault('max_part_chars', 800)
    config['splitter'].setdefault('min_chunk_size', 300)

    if 'workers' not in config:
        config['workers'] = {}
    config['workers'].setdefault('max_concurrent', 50)

    # Validate configuration values
    _validate_config(config)

    return config


def _validate_config(config: dict) -> None:
    """Validate configuration values after defaults have been applied.

    Raises:
        ValueError: if any configuration value is invalid.
    """
    import re as _re

    # Validate language codes (2-letter ISO 639-1)
    lang_pattern = _re.compile(r'^[a-z]{2}$')
    for field in ('source_lang', 'target_lang'):
        val = config['series'].get(field, '')
        if not lang_pattern.match(val):
            raise ValueError(
                f"Invalid '{field}' in [series]: '{val}'. "
                "Must be a 2-letter ISO 639-1 code (e.g. 'ja', 'ru')."
            )

    # Validate splitter integers (> 0)
    for key in ('target_chunk_size', 'max_part_chars', 'min_chunk_size'):
        val = config['splitter'].get(key)
        if not isinstance(val, int) or val <= 0:
            raise ValueError(
                f"Invalid 'splitter.{key}': {val!r}. Must be a positive integer."
            )

    # Validate workers.max_concurrent (1..200)
    workers_max = config['workers'].get('max_concurrent')
    if not isinstance(workers_max, int) or not (1 <= workers_max <= 200):
        raise ValueError(
            f"Invalid 'workers.max_concurrent': {workers_max!r}. Must be an integer between 1 and 200."
        )

    # Validate retry parameters
    max_attempts = config['retry'].get('max_attempts')
    if not isinstance(max_attempts, int) or not (1 <= max_attempts <= 10):
        raise ValueError(
            f"Invalid 'retry.max_attempts': {max_attempts!r}. Must be an integer between 1 and 10."
        )

    # Validate timeouts (> 0)
    for key in ('worker_timeout_seconds', 'proofreading_timeout_seconds'):
        val = config['gemini_cli'].get(key)
        if not isinstance(val, (int, float)) or val <= 0:
            raise ValueError(
                f"Invalid 'gemini_cli.{key}': {val!r}. Must be a positive number."
            )
