"""CLI entry point — launches TUI only."""
from __future__ import annotations

import sys

# (module_name, pip_package_name)
_REQUIRED_PACKAGES: list[tuple[str, str]] = [
    ("textual",     "textual>=1.0.0"),
    ("rich",        "rich>=13.0.0"),
    ("tenacity",    "tenacity>=8.0.0"),
    ("requests",    "requests>=2.28.0"),
    ("json_repair", "json-repair>=0.25.0"),
]


def _check_dependencies() -> None:
    """Verify all required Python packages are importable.

    Prints a helpful message and exits with code 1 if any are missing.
    """
    missing = []
    for module_name, package_spec in _REQUIRED_PACKAGES:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_spec)

    if missing:
        print("Ошибка: не установлены необходимые библиотеки:", file=sys.stderr)
        for pkg in missing:
            print(f"  {pkg}", file=sys.stderr)
        print("\nУстановите зависимости командой:", file=sys.stderr)
        print("  pip install -e .", file=sys.stderr)
        raise SystemExit(1)


def main():
    """Launch the Textual TUI application."""
    _check_dependencies()
    try:
        from book_translator.textual_app import BookTranslatorApp
        app = BookTranslatorApp()
        app.run()
    except ImportError as e:
        print(f"Error: Failed to load TUI application: {e}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(0)


if __name__ == "__main__":
    main()
