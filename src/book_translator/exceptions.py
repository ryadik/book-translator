"""
Custom exceptions for book-translator.
"""
from __future__ import annotations


class TranslationLockedError(RuntimeError):
    """Raised when a translation lock file is found and --resume is not set."""
