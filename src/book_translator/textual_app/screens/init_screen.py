"""Init screen — wizard to initialize a new book series."""
from __future__ import annotations

import types
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label
from textual.containers import Horizontal, Vertical


class InitScreen(Screen):
    """Setup wizard to create a new series in the current directory."""

    BINDINGS = [
        Binding("escape", "go_back", "Назад", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="init-box"):
            yield Label("🆕 Инициализация новой серии", id="init-title")
            yield Label("Название серии:", classes="field-label")
            yield Input(placeholder="Название серии", id="input-name")
            yield Label("Исходный язык (ISO 639-1):", classes="field-label")
            yield Input(placeholder="ja", id="input-source-lang", value="ja")
            yield Label("Целевой язык (ISO 639-1):", classes="field-label")
            yield Input(placeholder="ru", id="input-target-lang", value="ru")
            yield Label("", id="init-status")
            with Horizontal(id="init-buttons"):
                yield Button("✅ Создать", id="btn-create", variant="primary")
                yield Button("Назад", id="btn-back")
        yield Footer()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_mount(self) -> None:
        self.query_one("#input-name", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-create":
            self._create_series()
        elif event.button.id == "btn-back":
            self.action_go_back()

    def on_key(self, event) -> None:
        if event.key == "enter":
            self._create_series()

    def _create_series(self) -> None:
        name = self.query_one("#input-name", Input).value.strip()
        source_lang = self.query_one("#input-source-lang", Input).value.strip() or "ja"
        target_lang = self.query_one("#input-target-lang", Input).value.strip() or "ru"
        status_label = self.query_one("#init-status", Label)

        if not name:
            status_label.update("[red]Введите название серии[/red]")
            return

        # Fake args for run_init
        args = types.SimpleNamespace(
            name=name,
            source_lang=source_lang,
            target_lang=target_lang,
        )

        error_holder: list[str] = []

        def _capture_error(msg: str) -> None:
            error_holder.append(msg)
            raise SystemExit(1)

        try:
            from book_translator.commands.init_cmd import run_init
            run_init(
                args,
                info_callback=lambda _msg: None,
                success_callback=lambda _msg: None,
                error_callback=_capture_error,
            )
        except SystemExit:
            msg = error_holder[0] if error_holder else "Неизвестная ошибка"
            status_label.update(f"[red]{msg}[/red]")
            return
        except Exception as e:
            status_label.update(f"[red]Ошибка: {e}[/red]")
            return

        # Update app.series_root to the newly created series
        new_root = Path.cwd() / name
        self.app.series_root = new_root  # type: ignore[attr-defined]

        status_label.update(f"[green]✅ Серия '{name}' создана в {new_root}[/green]")

        # Refresh dashboard and return to it
        from book_translator.textual_app.messages import DashboardRefreshRequested
        self.app.pop_screen()
        self.app.post_message(DashboardRefreshRequested())
