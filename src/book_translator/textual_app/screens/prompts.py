"""Prompts screen — edit translation prompts, world info, and style guide."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Select, TextArea
from textual.containers import Horizontal

from book_translator import discovery


# Cloud (Gemini) prompt options
_CLOUD_PROMPT_OPTIONS = [
    ("── Промпты (Cloud/Gemini) ────────────", "sep"),
    ("Перевод (translation)",                 "translation"),
    ("Поиск терминов (term_discovery)",       "term_discovery"),
    ("Вычитка (proofreading)",                "proofreading"),
    ("Глобальная вычитка (global_proofreading)", "global_proofreading"),
]

# Local (Ollama) prompt options
_LOCAL_PROMPT_OPTIONS = [
    ("── Промпты (Local/Ollama) ────────────", "sep"),
    ("Перевод (translation)",                 "translation"),
    ("Поиск терминов (term_discovery)",       "term_discovery"),
    ("Вычитка (proofreading)",                "proofreading"),
    ("Глобальная вычитка (global_proofreading)", "global_proofreading"),
]

# Series files options (common for both backends)
_SERIES_FILE_OPTIONS = [
    ("── Серийные файлы ───────────────────", "sep2"),
    ("Информация о мире (world_info.md)",     "world_info"),
    ("Стилевой гайд (style_guide.md)",        "style_guide"),
]

# Keys that are prompt .txt files
_PROMPT_KEYS = {"translation", "term_discovery", "proofreading", "global_proofreading"}
# Keys that are .md docs
_DOC_KEYS = {"world_info", "style_guide"}
# Separator pseudo-options (not selectable)
_SEP_KEYS = {"sep", "sep2"}

# Default templates for series files
_WORLD_INFO_TEMPLATE = '''# Информация о мире

## Сеттинг
(Опишите сеттинг произведения)

## Главные персонажи
(Перечислите главных персонажей с краткими описаниями)
'''

_STYLE_GUIDE_TEMPLATE = '''## Стайлгайд перевода

### 1. Пунктуация
- **Тире в диалогах:** Использовать оператор звука (`─`, U+2500).
- **Мысли и названия:** Кавычки-«ёлочки» (`«...»`).

### 2. Общие правила
- Литературный перевод, не дословный.
- Обязательно использовать букву «ё».
'''


class PromptsScreen(Screen):
    """Editor for translation prompts and series markdown files."""

    BINDINGS = [
        Binding("escape", "go_back", "Назад", priority=True),
        Binding("ctrl+s", "save", "Сохранить", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._backend = "gemini"
        self._current_key = "translation"
        self._prompt_options: list[tuple[str, str]] = []

    def _detect_backend(self) -> str:
        """Detect the LLM backend from series config."""
        try:
            config = discovery.load_series_config(self._series_root())
            return config.get("llm", {}).get("backend", "gemini")
        except Exception:
            return "gemini"

    def _build_prompt_options(self) -> list[tuple[str, str]]:
        """Build the prompt options list based on backend."""
        if self._backend == "ollama":
            return _LOCAL_PROMPT_OPTIONS + _SERIES_FILE_OPTIONS
        return _CLOUD_PROMPT_OPTIONS + _SERIES_FILE_OPTIONS

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("📝 Промпты и файлы серии", id="prompts-title")
        with Horizontal(id="prompt-selector-bar"):
            yield Select(
                [],  # Will be populated in on_mount
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
        self._backend = self._detect_backend()
        self._prompt_options = self._build_prompt_options()

        # Update select options
        select = self.query_one("#prompt-select", Select)
        select.set_options([
            (label, name) for label, name in self._prompt_options
            if name not in _SEP_KEYS
        ])

        # Set initial value
        self._current_key = "translation"
        select.value = self._current_key

        self._load_content(self._current_key)
        select.focus()

    def _series_root(self) -> Path:
        return self.app.series_root  # type: ignore[attr-defined]

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load_content(self, key: str) -> None:
        if key in _PROMPT_KEYS:
            self._load_prompt(key)
        elif key in _DOC_KEYS:
            self._load_doc(key)

    def _load_prompt(self, name: str) -> None:
        """Load prompt - check series override first, then bundled defaults."""
        series_root = self._series_root()
        override_path = series_root / "prompts" / f"{name}.txt"
        status_label = self.query_one("#prompt-status", Label)

        if override_path.is_file():
            content = override_path.read_text(encoding="utf-8")
            status_label.update(f"[dim]Источник: кастомный файл (prompts/{name}.txt)[/dim]")
        else:
            from book_translator.default_prompts import PROMPTS, LOCAL_PROMPTS
            # Use backend-specific bundled prompts
            if self._backend == "ollama":
                content = LOCAL_PROMPTS.get(name, f"# Промпт '{name}' не найден")
            else:
                content = PROMPTS.get(name, f"# Промпт '{name}' не найден")
            status_label.update("[dim]Источник: встроенный дефолт[/dim]")

        self.query_one("#prompt-editor", TextArea).load_text(content)

    def _load_doc(self, key: str) -> None:
        """Load world_info.md or style_guide.md from series prompts folder or root."""
        series_root = self._series_root()
        # First check prompts folder, then root
        prompts_path = series_root / "prompts" / f"{key}.md"
        root_path = series_root / f"{key}.md"
        status_label = self.query_one("#prompt-status", Label)

        if prompts_path.is_file():
            content = prompts_path.read_text(encoding="utf-8")
            status_label.update(f"[dim]Файл: prompts/{key}.md[/dim]")
        elif root_path.is_file():
            content = root_path.read_text(encoding="utf-8")
            status_label.update(f"[dim]Файл: {key}.md (в корне серии)[/dim]")
        else:
            content = self._doc_default(key)
            status_label.update(f"[yellow]Файл {key}.md не найден. Будет создан при сохранении.[/yellow]")

        self.query_one("#prompt-editor", TextArea).load_text(content)

    @staticmethod
    def _doc_default(key: str) -> str:
        return _WORLD_INFO_TEMPLATE if key == "world_info" else _STYLE_GUIDE_TEMPLATE

    # ── Saving ────────────────────────────────────────────────────────────────

    def action_save(self) -> None:
        """Save content to series prompts folder (never modify bundled defaults)."""
        key = self._current_key
        content = self.query_one("#prompt-editor", TextArea).text
        status_label = self.query_one("#prompt-status", Label)
        series_root = self._series_root()

        try:
            if key in _PROMPT_KEYS:
                # Always save to series prompts folder
                path = series_root / "prompts" / f"{key}.txt"
                path.parent.mkdir(exist_ok=True)
                path.write_text(content, encoding="utf-8")
                status_label.update(f"[green]✅ Сохранено в prompts/{key}.txt[/green]")
            elif key in _DOC_KEYS:
                # Save to prompts folder (new location)
                path = series_root / "prompts" / f"{key}.md"
                path.parent.mkdir(exist_ok=True)
                path.write_text(content, encoding="utf-8")
                status_label.update(f"[green]✅ Сохранено в prompts/{key}.md[/green]")
        except Exception as e:
            status_label.update(f"[red]Ошибка: {e}[/red]")

    def action_reset(self) -> None:
        """Reset editor to default content (does not save)."""
        key = self._current_key
        if key in _PROMPT_KEYS:
            from book_translator.default_prompts import PROMPTS, LOCAL_PROMPTS
            # Use backend-specific bundled prompts
            if self._backend == "ollama":
                content = LOCAL_PROMPTS.get(key, "")
            else:
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
