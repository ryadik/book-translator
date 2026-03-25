"""CLI entry point — launches TUI only."""
from __future__ import annotations

import sys


def main():
    """Launch the Textual TUI application."""
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
