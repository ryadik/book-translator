"""Config screen — view and edit book-translator.toml."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, TextArea
from textual.containers import Horizontal


class ConfigScreen(Screen):
    """Editor for book-translator.toml."""

    BINDINGS = [
        Binding("escape", "go_back", "Назад", priority=True),
        Binding("ctrl+s", "save", "Сохранить", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("📄 book-translator.toml", id="config-title")
        yield TextArea(id="config-editor", language="toml")
        yield Label("", id="status-msg")
        with Horizontal():
            yield Button("💾 Сохранить", id="btn-save", variant="primary")
            yield Button("Назад", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self._load_config()
        self.query_one("#config-editor", TextArea).focus()

    def _config_path(self) -> Path:
        from book_translator.discovery import MARKER_FILE
        return self.app.series_root / MARKER_FILE  # type: ignore[attr-defined]

    def _load_config(self) -> None:
        path = self._config_path()
        try:
            content = path.read_text(encoding="utf-8")
            self.query_one("#config-editor", TextArea).load_text(content)
        except FileNotFoundError:
            self.query_one("#config-editor", TextArea).load_text(
                "# Файл конфигурации не найден"
            )

    def action_save(self) -> None:
        content = self.query_one("#config-editor", TextArea).text
        try:
            import tomllib
            tomllib.loads(content)  # validate TOML syntax
        except Exception as e:
            self.query_one("#status-msg", Label).update(f"[red]Ошибка TOML: {e}[/red]")
            return
        try:
            self._config_path().write_text(content, encoding="utf-8")
            self.query_one("#status-msg", Label).update("[green]✅ Сохранено[/green]")
        except Exception as e:
            self.query_one("#status-msg", Label).update(f"[red]Ошибка записи: {e}[/red]")

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self.action_save()
        elif event.button.id == "btn-back":
            self.action_go_back()
