"""
Series discovery module.
Implements walk-up algorithm to find book-translator.toml from CWD.
"""
from pathlib import Path

import tomllib

MARKER_FILE = "book-translator.toml"


def find_series_root(start_dir: Path | None = None) -> Path:
    """Walk up from start_dir (default: CWD) looking for book-translator.toml.

    Returns the directory containing the marker file.
    Raises FileNotFoundError if not found anywhere up to filesystem root.
    """
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
    
    # Capture user-specified gemini_cli timeouts BEFORE applying defaults,
    # so we can propagate explicit values to the unified [llm] timeout fields below.
    _raw_gemini_worker_timeout = config.get('gemini_cli', {}).get('worker_timeout_seconds')
    _raw_gemini_proofread_timeout = config.get('gemini_cli', {}).get('proofreading_timeout_seconds')

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
    config['workers'].setdefault('max_rps', 2.0)

    if 'llm' not in config:
        config['llm'] = {}
    config['llm'].setdefault('backend', 'gemini')
    config['llm'].setdefault('ollama_url', 'http://localhost:11434')

    # Unified timeouts — configurable in [llm] section, backend-aware defaults.
    # Ollama needs much longer timeouts because local inference is slow.
    # Explicit [gemini_cli] values from old configs are respected as fallback.
    _backend = config['llm']['backend']
    _default_worker_timeout = 600 if _backend == 'ollama' else 120
    _default_proofread_timeout = 900 if _backend == 'ollama' else 300
    config['llm'].setdefault(
        'worker_timeout_seconds',
        _raw_gemini_worker_timeout if _raw_gemini_worker_timeout is not None else _default_worker_timeout,
    )
    config['llm'].setdefault(
        'proofreading_timeout_seconds',
        _raw_gemini_proofread_timeout if _raw_gemini_proofread_timeout is not None else _default_proofread_timeout,
    )

    if 'models' not in config['llm']:
        config['llm']['models'] = {}
    config['llm']['models'].setdefault('discovery', 'qwen3:8b')
    config['llm']['models'].setdefault('translation', 'qwen3:30b-a3b')
    config['llm']['models'].setdefault('proofreading', 'qwen3:30b-a3b')
    config['llm']['models'].setdefault('global_proofreading', 'qwen3:14b')

    if 'options' not in config['llm']:
        config['llm']['options'] = {}
    config['llm']['options'].setdefault('temperature', 0.3)
    config['llm']['options'].setdefault('num_ctx', 8192)
    # Disable Qwen3 thinking mode by default — speeds up generation and avoids
    # think-tokens leaking into translated text or JSON responses.
    config['llm']['options'].setdefault('think', False)

    if 'stage_temperature' not in config['llm']['options']:
        config['llm']['options']['stage_temperature'] = {}
    config['llm']['options']['stage_temperature'].setdefault('discovery', 0.1)
    config['llm']['options']['stage_temperature'].setdefault('translation', 0.4)
    config['llm']['options']['stage_temperature'].setdefault('proofreading', 0.3)
    config['llm']['options']['stage_temperature'].setdefault('global_proofreading', 0.1)

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

    # Validate workers.max_rps (0.1..100)
    max_rps = config['workers'].get('max_rps')
    if not isinstance(max_rps, (int, float)) or not (0.1 <= max_rps <= 100):
        raise ValueError(
            f"Invalid 'workers.max_rps': {max_rps!r}. Must be a number between 0.1 and 100."
        )

    # Validate retry parameters
    max_attempts = config['retry'].get('max_attempts')
    if not isinstance(max_attempts, int) or not (1 <= max_attempts <= 10):
        raise ValueError(
            f"Invalid 'retry.max_attempts': {max_attempts!r}. Must be an integer between 1 and 10."
        )

    # Validate [gemini_cli] timeouts (backward compat)
    for key in ('worker_timeout_seconds', 'proofreading_timeout_seconds'):
        val = config['gemini_cli'].get(key)
        if not isinstance(val, (int, float)) or val <= 0:
            raise ValueError(
                f"Invalid 'gemini_cli.{key}': {val!r}. Must be a positive number."
            )

    # Validate unified [llm] timeouts
    for key in ('worker_timeout_seconds', 'proofreading_timeout_seconds'):
        val = config['llm'].get(key)
        if not isinstance(val, (int, float)) or val <= 0:
            raise ValueError(
                f"Invalid 'llm.{key}': {val!r}. Must be a positive number."
            )

    # Validate llm backend
    backend = config['llm'].get('backend')
    if backend not in ('gemini', 'ollama'):
        raise ValueError(
            f"Invalid 'llm.backend': {backend!r}. Must be 'gemini' or 'ollama'."
        )

    # Validate ollama model names (non-empty strings)
    for stage in ('discovery', 'translation', 'proofreading', 'global_proofreading'):
        val = config['llm']['models'].get(stage)
        if not isinstance(val, str) or not val.strip():
            raise ValueError(
                f"Invalid 'llm.models.{stage}': {val!r}. Must be a non-empty string."
            )
