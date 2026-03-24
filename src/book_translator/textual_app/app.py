"""BookTranslatorApp — main Textual application."""
from __future__ import annotations

import json
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from book_translator.textual_app.screens.dashboard import DashboardScreen
from book_translator.textual_app.messages import (
    ConfirmRequest,
    TermApprovalRequest,
    TUILogRecord,
    WaitForUserRequest,
)

_UI_CONFIG = Path.home() / ".config" / "book-translator" / "tui.json"


def _load_ui_config() -> dict:
    try:
        return json.loads(_UI_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_ui_config(data: dict) -> None:
    try:
        _UI_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        _UI_CONFIG.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


class BookTranslatorApp(App):
    """The book-translator TUI application."""

    CSS_PATH = Path(__file__).parent / "app.tcss"
    TITLE = "book-translator"
    BINDINGS = [
        Binding("ctrl+d", "toggle_dark", "Тема", key_display="Ctrl+D", priority=True),
        Binding("ctrl+q", "quit", "Выход", show=False, priority=True),
    ]

    def __init__(self, series_root: Path | None = None) -> None:
        super().__init__()
        if series_root is None:
            try:
                from book_translator.discovery import find_series_root
                series_root = find_series_root()
            except FileNotFoundError:
                series_root = Path.cwd()
        self.series_root: Path = series_root
        self._ui_config = _load_ui_config()
        self._preferred_theme = None
        if "theme" in self._ui_config:
            self._preferred_theme = str(self._ui_config["theme"])
        elif "dark" in self._ui_config:
            self._preferred_theme = "textual-dark" if bool(self._ui_config["dark"]) else "textual-light"
        # Circular buffer of log records for LogScreen historical view
        self._log_buffer: list[dict[str, str | None]] = []

    def on_mount(self) -> None:
        if self._preferred_theme:
            self.theme = self._preferred_theme
            self._persist_theme()
        self.push_screen(DashboardScreen())

    def _persist_theme(self) -> None:
        self._ui_config["theme"] = self.theme
        self._ui_config["dark"] = self.theme == "textual-dark"
        _save_ui_config(self._ui_config)

    def action_toggle_dark(self) -> None:
        """Toggle dark/light mode and persist the choice."""
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"
        self._persist_theme()

    def action_quit(self) -> None:
        self._persist_theme()
        self.exit()

    # ── Log record routing ────────────────────────────────────────────────────

    def on_tuilog_record(self, event: TUILogRecord) -> None:
        """Buffer the record and forward to whichever screen is currently active."""
        self._log_buffer.append(
            {
                "text": event.text,
                "level": event.level,
                "logger_name": event.logger_name,
                "worker_id": event.worker_id,
            }
        )
        if len(self._log_buffer) > 2000:
            del self._log_buffer[:500]  # drop oldest 500 when full

        # Forward directly to the active screen; reposting through Textual's
        # message queue would bubble the same log record back to the App and
        # create an infinite loop.
        try:
            handler = getattr(self.screen, "on_tuilog_record", None)
            if callable(handler):
                handler(
                    TUILogRecord(
                        event.text,
                        event.level,
                        logger_name=event.logger_name,
                        worker_id=event.worker_id,
                    )
                )
            elif hasattr(self.screen, "_log_records"):
                self.screen.post_message(
                    TUILogRecord(
                        event.text,
                        event.level,
                        logger_name=event.logger_name,
                        worker_id=event.worker_id,
                    )
                )
        except Exception:
            pass

    # ── Global message handlers ───────────────────────────────────────────────

    def on_confirm_request(self, event: ConfirmRequest) -> None:
        """Handle yes/no confirmation from TextualBridge.confirm()."""
        from textual.widgets import Button, Label
        from textual.screen import ModalScreen
        from textual.app import ComposeResult
        from textual.containers import Vertical, Horizontal

        class ConfirmModal(ModalScreen):
            def __init__(self, prompt: str, default: bool, cb) -> None:
                super().__init__()
                self._prompt = prompt
                self._cb = cb
                self._default = default

            def compose(self) -> ComposeResult:
                with Vertical(id="confirm-box"):
                    yield Label(self._prompt, id="confirm-label")
                    with Horizontal():
                        yield Button("Да  (y)", id="btn-yes", variant="primary")
                        yield Button("Нет (n)", id="btn-no")

            def on_button_pressed(self, ev: Button.Pressed) -> None:
                self._cb(ev.button.id == "btn-yes")
                self.dismiss()

            def on_key(self, event) -> None:
                if event.key == "y":
                    self._cb(True); self.dismiss()
                elif event.key in ("n", "escape"):
                    self._cb(self._default); self.dismiss()

        self.push_screen(ConfirmModal(event.prompt, event.default, event.callback))

    def on_wait_for_user_request(self, event: WaitForUserRequest) -> None:
        """Handle blocking wait from TextualBridge.wait_for_user()."""
        from textual.widgets import Button, Label
        from textual.screen import ModalScreen
        from textual.app import ComposeResult
        from textual.containers import Vertical

        class WaitModal(ModalScreen):
            def __init__(self, message: str, ev) -> None:
                super().__init__()
                self._message = message
                self._event = ev

            def compose(self) -> ComposeResult:
                with Vertical(id="wait-box"):
                    yield Label(self._message, id="wait-label")
                    yield Button("Продолжить  (Enter)", id="btn-continue", variant="primary")

            def on_button_pressed(self, ev: Button.Pressed) -> None:
                if ev.button.id == "btn-continue":
                    self._event.set(); self.dismiss()

            def on_key(self, event) -> None:
                if event.key in ("enter", "space"):
                    self._event.set(); self.dismiss()

        self.push_screen(WaitModal(event.message, event.event))

    def on_term_approval_request(self, event: TermApprovalRequest) -> None:
        """Handle term-approval request from TextualBridge.approve_terms()."""
        from book_translator.textual_app.screens.term_approval import TermApprovalScreen
        self.push_screen(
            TermApprovalScreen(
                terms=event.terms,
                tsv_path=event.tsv_path,
                glossary_db_path=event.glossary_db_path,
                source_lang=event.source_lang,
                target_lang=event.target_lang,
                callback=event.callback,
            )
        )
