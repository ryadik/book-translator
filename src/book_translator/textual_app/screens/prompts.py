"""Prompts screen — edit translation prompts, world info, and style guide."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Select, TextArea
from textual.containers import Horizontal


_PROMPT_OPTIONS = [
    ("── Промпты ──────────────────────────", "sep"),
    ("Перевод (translation)",                 "translation"),
    ("Поиск терминов (term_discovery)",       "term_discovery"),
    ("Вычитка (proofreading)",                "proofreading"),
    ("Глобальная вычитка (global_proofreading)", "global_proofreading"),
    ("── Серийные файлы ───────────────────", "sep2"),
    ("Информация о мире (world_info.md)",     "world_info"),
    ("Стилевой гайд (style_guide.md)",        "style_guide"),
]

# Keys that are prompt .txt files
_PROMPT_KEYS = {"translation", "term_discovery", "proofreading", "global_proofreading"}
# Keys that are .md docs at series root
_DOC_KEYS = {"world_info", "style_guide"}
# Separator pseudo-options (not selectable)
_SEP_KEYS = {"sep", "sep2"}


class PromptsScreen(Screen):
    """Editor for translation prompts and series markdown files."""

    BINDINGS = [
        Binding("escape", "go_back", "Назад", priority=True),
        Binding("ctrl+s", "save", "Сохранить", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("📝 Промпты и файлы серии", id="prompts-title")
        with Horizontal(id="prompt-selector-bar"):
            yield Select(
                [(label, name) for label, name in _PROMPT_OPTIONS
                 if name not in _SEP_KEYS],
                id="prompt-select",
                allow_blank=False,
                value="translation",
            )
        yield TextArea(id="prompt-editor")
        yield Label("", id="prompt-status")
        with Horizontal(id="prompt-buttons"):
            yield Button("💾 Сохранить", id="btn-save", variant="primary")
            yield Button("↩ Сбросить к умолчанию", id="btn-reset")
            yield Button("Назад", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self._current_key = "translation"
        self._load_content("translation")
        self.query_one("#prompt-select", Select).focus()

    def _series_root(self) -> Path:
        return self.app.series_root  # type: ignore[attr-defined]

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load_content(self, key: str) -> None:
        if key in _PROMPT_KEYS:
            self._load_prompt(key)
        elif key in _DOC_KEYS:
            self._load_doc(key)

    def _load_prompt(self, name: str) -> None:
        series_root = self._series_root()
        override_path = series_root / "prompts" / f"{name}.txt"
        status_label = self.query_one("#prompt-status", Label)

        if override_path.is_file():
            content = override_path.read_text(encoding="utf-8")
            status_label.update("[dim]Источник: кастомный файл (prompts/{}.txt)[/dim]".format(name))
        else:
            from book_translator.default_prompts import PROMPTS
            content = PROMPTS.get(name, f"# Промпт '{name}' не найден")
            status_label.update("[dim]Источник: встроенный дефолт[/dim]")

        self.query_one("#prompt-editor", TextArea).load_text(content)

    def _load_doc(self, key: str) -> None:
        """Load world_info.md or style_guide.md from series root."""
        path = self._series_root() / f"{key}.md"
        status_label = self.query_one("#prompt-status", Label)

        if path.is_file():
            content = path.read_text(encoding="utf-8")
            status_label.update(f"[dim]Файл: {key}.md[/dim]")
        else:
            content = self._doc_default(key)
            status_label.update(f"[yellow]Файл {key}.md не найден. Будет создан при сохранении.[/yellow]")

        self.query_one("#prompt-editor", TextArea).load_text(content)

    @staticmethod
    def _doc_default(key: str) -> str:
        from book_translator.commands.init_cmd import WORLD_INFO_TEMPLATE, STYLE_GUIDE_TEMPLATE
        return WORLD_INFO_TEMPLATE if key == "world_info" else STYLE_GUIDE_TEMPLATE

    # ── Saving ────────────────────────────────────────────────────────────────

    def action_save(self) -> None:
        key = self._current_key
        content = self.query_one("#prompt-editor", TextArea).text
        status_label = self.query_one("#prompt-status", Label)
        try:
            if key in _PROMPT_KEYS:
                path = self._series_root() / "prompts" / f"{key}.txt"
                path.parent.mkdir(exist_ok=True)
                path.write_text(content, encoding="utf-8")
            elif key in _DOC_KEYS:
                path = self._series_root() / f"{key}.md"
                path.write_text(content, encoding="utf-8")
            status_label.update("[green]✅ Сохранено[/green]")
        except Exception as e:
            status_label.update(f"[red]Ошибка: {e}[/red]")

    def action_reset(self) -> None:
        """Reset editor to default content (does not save)."""
        key = self._current_key
        if key in _PROMPT_KEYS:
            from book_translator.default_prompts import PROMPTS
            content = PROMPTS.get(key, "")
        else:
            content = self._doc_default(key)
        self.query_one("#prompt-editor", TextArea).load_text(content)
        self.query_one("#prompt-status", Label).update(
            "[yellow]Сброшено к дефолту (не сохранено)[/yellow]"
        )

    def action_go_back(self) -> None:
        self.app.pop_screen()

    # ── Events ────────────────────────────────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "prompt-select" and event.value is not Select.BLANK:
            key = str(event.value)
            if key in _SEP_KEYS:
                return  # ignore separators (shouldn't happen with filtered list)
            self._current_key = key
            self._load_content(key)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self.action_save()
        elif event.button.id == "btn-reset":
            self.action_reset()
        elif event.button.id == "btn-back":
            self.action_go_back()
