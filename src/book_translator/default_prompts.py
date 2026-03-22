"""
Bundled default prompt templates for book-translator.

These are the fallback prompts used when no series-level override exists in
{series_root}/prompts/.

Users can override any prompt by placing a file in {series_root}/prompts/
"""

from importlib import resources


def _load(name: str) -> str:
    return (
        resources.files("book_translator") / "data" / "prompts" / f"{name}.txt"
    ).read_text(encoding="utf-8")


PROMPTS: dict[str, str] = {
    "translation": _load("translation"),
    "term_discovery": _load("term_discovery"),
    "proofreading": _load("proofreading"),
    "global_proofreading": _load("global_proofreading"),
}
