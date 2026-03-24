"""Dashboard screen — main view showing all volumes and chapters."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, Static
from textual.binding import Binding

from book_translator import db, discovery
from book_translator.textual_app.messages import DashboardRefreshRequested


# Map chapter stage → display label
_STAGE_LABELS: dict[str, str] = {
    "complete":            "✅ Готово",
    "global_proofreading": "🔍 Глоб. вычитка",
    "proofreading":        "✍️  Вычитка",
    "translation":         "🌐 Перевод",
    "discovery":           "🔎 Поиск",
    "pending":             "⏳ Ожидание",
}


class DashboardScreen(Screen):
    """Read-only overview of all volumes and chapters in the series."""

    BINDINGS = [
        Binding("r", "refresh", "Обновить", priority=True),
        Binding("enter", "translate_selected", "Перевести", priority=True),
        Binding("t", "translate_selected", "Перевести", show=False, priority=True),
        Binding("i", "init_series", "Новая серия", show=False, priority=True),
        Binding("g", "switch_to_glossary", "Глоссарий", priority=True),
        Binding("p", "switch_to_prompts", "Промпты", priority=True),
        Binding("c", "switch_to_config", "Конфиг", priority=True),
        Binding("l", "switch_to_logs", "Логи", priority=True),
        Binding("q", "quit", "Выход", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="series-info")
        yield DataTable(id="chapter-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self._row_chapters: list[tuple[str, str]] = []
        self._setup_table()
        self._load_data()
        # Give keyboard focus to the table immediately
        self.query_one("#chapter-table", DataTable).focus()

    def _has_series_config(self) -> bool:
        try:
            discovery.load_series_config(self.app.series_root)  # type: ignore[attr-defined]
            return True
        except Exception:
            return False

    def _setup_table(self) -> None:
        table = self.query_one("#chapter-table", DataTable)
        table.add_columns(
            "Том", "Глава", "Этап", "Done", "Total", "Ошибки"
        )

    def _load_data(self) -> None:
        """Read series state from DB and populate the table."""
        self._row_chapters = []
        app = self.app
        series_root: Path = app.series_root  # type: ignore[attr-defined]

        # Series info header
        try:
            config = discovery.load_series_config(series_root)
            name = config["series"]["name"]
            src = config["series"]["source_lang"]
            tgt = config["series"]["target_lang"]
            model = config.get("gemini_cli", {}).get("model", "?")
            glossary_db = series_root / "glossary.db"
            db.init_glossary_db(glossary_db)
            term_count = len(db.get_terms(glossary_db, src, tgt))
            info_text = (
                f"📚 [bold]{name}[/bold]  |  {src} → {tgt}  |  "
                f"Модель: {model}  |  Терминов: {term_count}"
            )
            self.query_one("#series-info", Static).update(info_text)
        except Exception:
            self.query_one("#series-info", Static).update(
                "[red]⚠ Серия не найдена. Нажмите [bold]i[/bold] для инициализации[/red]"
            )
            return

        # Chapter table
        table = self.query_one("#chapter-table", DataTable)
        table.clear()

        volume_dirs = sorted(
            d for d in series_root.iterdir()
            if d.is_dir() and (d / "source").is_dir()
        )

        if not volume_dirs:
            table.add_row("—", "Нет томов — создайте volume-XX/source/", "—", "—", "—", "—")
            self._row_chapters.append(("", ""))
            return

        for vol_dir in volume_dirs:
            source_dir = vol_dir / "source"
            chunks_db = vol_dir / ".state" / "chunks.db"

            # Scan source files
            source_files = sorted(source_dir.glob("*.txt"))

            if not source_files:
                table.add_row(vol_dir.name, "—", "⏳ Нет .txt файлов", "0", "0", "—")
                self._row_chapters.append((vol_dir.name, ""))
                continue

            # Load DB state if available
            db_data: dict[str, dict] = {}
            if chunks_db.exists():
                try:
                    db.init_chunks_db(chunks_db)
                    for chapter_name in db.get_all_chapters(chunks_db):
                        stage = db.get_chapter_stage(chunks_db, chapter_name) or "pending"
                        counts = db.get_chunk_status_counts(chunks_db, chapter_name)
                        done = counts.get("reading_done", 0)
                        total = sum(counts.values())
                        errors = sum(v for k, v in counts.items() if "_failed" in k)
                        db_data[chapter_name] = {
                            "stage": stage,
                            "done": done,
                            "total": total,
                            "errors": errors,
                        }
                except Exception:
                    pass

            for src_file in source_files:
                chapter_name = src_file.stem
                if chapter_name in db_data:
                    info = db_data[chapter_name]
                    stage_label = _STAGE_LABELS.get(info["stage"], info["stage"])
                    errors = info["errors"]
                    table.add_row(
                        vol_dir.name,
                        chapter_name,
                        stage_label,
                        str(info["done"]),
                        str(info["total"]),
                        str(errors) if errors else "[dim]—[/dim]",
                    )
                else:
                    table.add_row(
                        vol_dir.name,
                        chapter_name,
                        "⏳ Ожидание",
                        "0",
                        "0",
                        "[dim]—[/dim]",
                    )
                self._row_chapters.append((vol_dir.name, chapter_name))

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        table = self.query_one("#chapter-table", DataTable)
        table.clear()
        self._load_data()

    def action_translate_selected(self) -> None:
        """Show options modal then push TranslationScreen."""
        table = self.query_one("#chapter-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row < 0 or cursor_row >= len(self._row_chapters):
            return

        vol_name, chapter_name = self._row_chapters[cursor_row]
        if not chapter_name:
            self.notify("Выберите главу для перевода", severity="warning")
            return

        from book_translator.textual_app.screens.translation import TranslationScreen
        from book_translator.textual_app.screens.translation_options import TranslationOptionsModal
        series_root: Path = self.app.series_root  # type: ignore[attr-defined]
        chapter_path = series_root / vol_name / "source" / f"{chapter_name}.txt"
        if not chapter_path.exists():
            self.notify(f"Файл не найден: {chapter_path}", severity="error")
            return

        def _on_options(options: dict | None) -> None:
            if options is None:
                return  # user cancelled
            self.app.push_screen(TranslationScreen(series_root, chapter_path, options))

        self.app.push_screen(TranslationOptionsModal(), _on_options)

    def action_init_series(self) -> None:
        if self._has_series_config():
            self.notify(
                "Серия уже инициализирована в этой папке. "
                "Перейдите в другую директорию для создания новой серии.",
                severity="warning",
                timeout=5,
            )
            return
        from book_translator.textual_app.screens.init_screen import InitScreen
        self.app.push_screen(InitScreen())

    def action_switch_to_glossary(self) -> None:
        from book_translator.textual_app.screens.glossary import GlossaryScreen
        self.app.push_screen(GlossaryScreen())

    def action_switch_to_prompts(self) -> None:
        from book_translator.textual_app.screens.prompts import PromptsScreen
        self.app.push_screen(PromptsScreen())

    def action_switch_to_config(self) -> None:
        from book_translator.textual_app.screens.config import ConfigScreen
        self.app.push_screen(ConfigScreen())

    def action_switch_to_logs(self) -> None:
        from book_translator.textual_app.screens.logs import LogScreen
        table = self.query_one("#chapter-table", DataTable)
        cursor_row = table.cursor_row
        volume_name = None
        chapter_name = None
        if 0 <= cursor_row < len(self._row_chapters):
            volume_name, chapter_name = self._row_chapters[cursor_row]
            if not chapter_name:
                chapter_name = None
        self.app.push_screen(LogScreen(volume_name=volume_name, chapter_name=chapter_name))

    def action_quit(self) -> None:
        self.app.exit()

    # ── Event handlers ────────────────────────────────────────────────────────

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a row → translate that chapter."""
        self.action_translate_selected()

    def on_dashboard_refresh_requested(
        self, _: DashboardRefreshRequested
    ) -> None:
        self.action_refresh()

    def on_key(self, event) -> None:
        key_actions = {
            "r": self.action_refresh,
            "i": self.action_init_series,
            "g": self.action_switch_to_glossary,
            "p": self.action_switch_to_prompts,
            "c": self.action_switch_to_config,
            "l": self.action_switch_to_logs,
            "q": self.action_quit,
        }
        action = key_actions.get(event.key)
        if action is not None:
            event.stop()
            action()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "init_series":
            return not self._has_series_config()
        return None
