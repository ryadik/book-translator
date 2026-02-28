"""
Configuration loader.
Wraps discovery.load_series_config() for backward compatibility.
"""
from pathlib import Path
from typing import Optional
from book_translator.discovery import find_series_root, load_series_config as _load_series_config

def load_config(series_root: Optional[Path] = None) -> dict:
    """Load series configuration.
    
    If series_root is not provided, discovers it via walk-up from CWD.
    
    Returns:
        dict: Configuration with all defaults applied
    Raises:
        FileNotFoundError: if book-translator.toml not found
        ValueError: if config is invalid
    """
    if series_root is None:
        series_root = find_series_root()
    return _load_series_config(series_root)
