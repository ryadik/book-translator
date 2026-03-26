"""Init screen — wizard to initialize a new book series."""
from __future__ import annotations

import logging
import shutil
import types
from importlib import resources
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RadioButton, RadioSet
from textual.containers import Horizontal, Vertical

from book_translator.discovery import MARKER_FILE
from book_translator.db import init_glossary_db

_logger = logging.getLogger(__name__)

TOML_TEMPLATE_GEMINI = '''[series]
name = "{name}"
source_lang = "{source_lang}"
target_lang = "{target_lang}"

# LLM backend: "gemini" (cloud) or "ollama" (local)
[llm]
backend = "gemini"

# Gemini model configuration
[gemini_cli]
model = "gemini-2.5-pro"
worker_timeout_seconds = 120
proofreading_timeout_seconds = 300

[retry]
max_attempts = 3
wait_min_seconds = 4
wait_max_seconds = 10

[splitter]
target_chunk_size = 600
max_part_chars = 800
min_chunk_size = 300

[workers]
max_concurrent = 50
max_rps = 2.0
'''

TOML_TEMPLATE_OLLAMA = '''[series]
name = "{name}"
source_lang = "{source_lang}"
target_lang = "{target_lang}"

# LLM backend: "ollama" (local inference via Ollama server)
[llm]
backend = "ollama"
ollama_url = "http://localhost:11434"

# Model for each pipeline stage — swap for other Ollama models as needed
[llm.models]
discovery = "qwen3:8b"             # fast model for term extraction
translation = "qwen3:30b-a3b"     # quality model for literary translation
proofreading = "qwen3:30b-a3b"    # quality model for per-chunk polish
global_proofreading = "qwen3:14b" # model for chapter-wide consistency pass

# Generation options (applied to all stages unless overridden below)
[llm.options]
temperature = 0.3
num_ctx = 8192  # context window; increase if prompts + glossary + text exceed this
think = false   # Qwen3 extended thinking; false = faster, no hidden reasoning tokens

# Per-stage temperature overrides
[llm.options.stage_temperature]
discovery = 0.1          # low temp for deterministic JSON extraction
translation = 0.4        # higher temp for creative literary output
proofreading = 0.3       # moderate temp for stylistic refinement
global_proofreading = 0.1 # low temp for consistent JSON diffs

[retry]
max_attempts = 3
wait_min_seconds = 4
wait_max_seconds = 10

[splitter]
target_chunk_size = 600
max_part_chars = 800
min_chunk_size = 300

# Ollama: low concurrency (local hardware), no external API rate limit
[workers]
max_concurrent = 3
max_rps = 100.0
'''

WORLD_INFO_TEMPLATE = '''# Информация о мире

## Сеттинг
(Опишите сеттинг произведения)

## Главные персонажи
(Перечислите главных персонажей с краткими описаниями)
'''

STYLE_GUIDE_TEMPLATE = '''## Стайлгайд перевода

### 1. Пунктуация
- **Тире в диалогах:** Использовать оператор звука (`─`, U+2500).
- **Мысли и названия:** Кавычки-«ёлочки» (`«...»`).

### 2. Общие правила
- Литературный перевод, не дословный.
- Обязательно использовать букву «ё».
'''


def _find_bundled_style_guide(source_lang: str, target_lang: str) -> Path | None:
    """Find bundled style guide for the given language pair."""
    style_guides_ref = resources.files('book_translator') / 'data' / 'style_guides'
    for name in (f'{source_lang}_{target_lang}.md', 'default.md'):
        candidate = style_guides_ref / name
        try:
            path = Path(str(candidate))
            if path.is_file():
                return path
        except (TypeError, FileNotFoundError) as e:
            _logger.debug("Could not resolve bundled style guide '%s': %s", name, e)
    return None


def run_init(args) -> None:
    """Initialize a new book series with directory structure and config files.

    Raises:
        ValueError: if initialization cannot proceed (directory exists, already initialized, etc.)
    """
    # Determine target directory based on mode
    if getattr(args, 'use_current_dir', False):
        series_dir = Path.cwd()
    else:
        series_dir = Path.cwd() / args.name

    if series_dir.exists() and not getattr(args, 'use_current_dir', False):
        raise ValueError(f"Директория '{args.name}' уже существует.")

    # Create directory structure (only if not using current dir)
    if not getattr(args, 'use_current_dir', False):
        series_dir.mkdir()

    # Check if already initialized when using current dir
    if getattr(args, 'use_current_dir', False) and (series_dir / MARKER_FILE).exists():
        raise ValueError(f"В текущей директории уже есть '{MARKER_FILE}'.")

    # Write marker file (book-translator.toml)
    backend = getattr(args, 'backend', 'gemini')
    template = TOML_TEMPLATE_OLLAMA if backend == 'ollama' else TOML_TEMPLATE_GEMINI
    toml_content = template.format(
        name=args.name,
        source_lang=args.source_lang,
        target_lang=args.target_lang
    )
    (series_dir / MARKER_FILE).write_text(toml_content, encoding='utf-8')

    # Create prompts directory and write template files there
    prompts_dir = series_dir / 'prompts'
    prompts_dir.mkdir(exist_ok=True)
    (prompts_dir / 'world_info.md').write_text(WORLD_INFO_TEMPLATE, encoding='utf-8')
    bundled_guide = _find_bundled_style_guide(args.source_lang, args.target_lang)
    if bundled_guide:
        shutil.copy2(bundled_guide, prompts_dir / 'style_guide.md')
    else:
        (prompts_dir / 'style_guide.md').write_text(STYLE_GUIDE_TEMPLATE, encoding='utf-8')

    # Initialize glossary database
    init_glossary_db(series_dir / 'glossary.db')

    # Create volume-01 scaffold
    vol1 = series_dir / 'volume-01'
    (vol1 / 'source').mkdir(parents=True, exist_ok=True)
    (vol1 / 'output').mkdir(exist_ok=True)


class InitScreen(Screen):
    """Setup wizard to create a new series in the current directory."""

    BINDINGS = [
        Binding("escape", "go_back", "Назад", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="init-box"):
            yield Label("🆕 Инициализация новой серии", id="init-title")

            yield Label("Расположение:", classes="field-label")
            with RadioSet(id="location-mode"):
                yield RadioButton("Создать подпапку", value=True, id="radio-subfolder")
                yield RadioButton("Использовать текущую папку", id="radio-current")

            yield Label("Название серии:", classes="field-label")
            yield Input(placeholder="Название серии", id="input-name")

            yield Label("Исходный язык (ISO 639-1):", classes="field-label")
            yield Input(placeholder="ja", id="input-source-lang", value="ja")

            yield Label("Целевой язык (ISO 639-1):", classes="field-label")
            yield Input(placeholder="ru", id="input-target-lang", value="ru")

            yield Label("LLM-бэкенд:", classes="field-label")
            with RadioSet(id="backend-select"):
                yield RadioButton("Gemini (облачный)", value=True, id="radio-gemini")
                yield RadioButton("Ollama (локальный)", id="radio-ollama")

            yield Label("", id="init-status")
            with Horizontal(id="init-buttons"):
                yield Button("✅ Создать", id="btn-create", variant="primary")
                yield Button("Назад", id="btn-back")
        yield Footer()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_mount(self) -> None:
        self.query_one("#input-name", Input).focus()
        self._update_name_input_state()

    def _update_name_input_state(self) -> None:
        """Enable/disable name input based on location mode."""
        use_current = self.query_one("#radio-current", RadioButton).value
        name_input = self.query_one("#input-name", Input)
        if use_current:
            name_input.disabled = True
            name_input.placeholder = "(используется имя текущей папки)"
        else:
            name_input.disabled = False
            name_input.placeholder = "Название серии"

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio set changes."""
        if event.radio_set.id == "location-mode":
            self._update_name_input_state()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-create":
            self._create_series()
        elif event.button.id == "btn-back":
            self.action_go_back()

    def on_key(self, event) -> None:
        if event.key == "enter":
            self._create_series()

    def _create_series(self) -> None:
        use_current_dir = self.query_one("#radio-current", RadioButton).value
        name = self.query_one("#input-name", Input).value.strip()
        source_lang = self.query_one("#input-source-lang", Input).value.strip() or "ja"
        target_lang = self.query_one("#input-target-lang", Input).value.strip() or "ru"
        backend = "ollama" if self.query_one("#radio-ollama", RadioButton).value else "gemini"
        status_label = self.query_one("#init-status", Label)

        # Determine series name
        if use_current_dir:
            name = Path.cwd().name
        elif not name:
            status_label.update("[red]Введите название серии[/red]")
            return

        # Fake args for run_init
        args = types.SimpleNamespace(
            name=name,
            source_lang=source_lang,
            target_lang=target_lang,
            backend=backend,
            use_current_dir=use_current_dir,
        )

        try:
            run_init(args)
        except ValueError as e:
            status_label.update(f"[red]{e}[/red]")
            return
        except Exception as e:
            status_label.update(f"[red]Ошибка: {e}[/red]")
            return

        # Update app.series_root to the newly created series
        new_root = Path.cwd() if use_current_dir else Path.cwd() / name
        self.app.series_root = new_root  # type: ignore[attr-defined]

        status_label.update(f"[green]✅ Серия '{name}' создана в {new_root}[/green]")

        # Refresh dashboard and return to it
        from book_translator.textual_app.messages import DashboardRefreshRequested
        self.app.pop_screen()
        self.app.post_message(DashboardRefreshRequested())
