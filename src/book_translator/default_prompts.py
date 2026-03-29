"""
Bundled default prompt templates for book-translator.

These are the fallback prompts used when no series-level override exists in
{series_root}/prompts/.

Users can override any prompt by placing a file in {series_root}/prompts/

Two sets of bundled prompts are provided:
  PROMPTS       — full-detail prompts optimised for cloud models (Gemini)
  LOCAL_PROMPTS — simplified prompts optimised for local models (Ollama)
"""

from importlib import resources


def _load(name: str) -> str:
    return (
        resources.files("book_translator") / "data" / "prompts" / f"{name}.txt"
    ).read_text(encoding="utf-8")


def _load_local(name: str) -> str:
    return (
        resources.files("book_translator") / "data" / "prompts" / "local" / f"{name}.txt"
    ).read_text(encoding="utf-8")


PROMPTS: dict[str, str] = {
    "translation": _load("translation"),
    "term_discovery": _load("term_discovery"),
    "proofreading": _load("proofreading"),
    "global_proofreading": _load("global_proofreading"),
}

LOCAL_PROMPTS: dict[str, str] = {
    "translation": _load_local("translation"),
    "term_discovery": _load_local("term_discovery"),
    "proofreading": _load_local("proofreading"),
    "global_proofreading": _load_local("global_proofreading"),
}
