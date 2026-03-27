"""Dashboard screen — main view showing all volumes and chapters."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static, Tree
from textual.binding import Binding
from textual.containers import Vertical

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
        Binding("/", "focus_search", "Поиск", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="series-info")
        with Vertical(id="dashboard-content"):
            yield Input(placeholder="🔍 Поиск тома или главы...", id="search-input")
            yield Tree("Серия", id="chapter-tree")
        yield Footer()

    def on_mount(self) -> None:
        self._chapter_map: dict[str, tuple[str, str]] = {}  # tree node key -> (volume, chapter)
        self._setup_tree()
        self._load_data()
        self.query_one("#chapter-tree", Tree).focus()

    def _has_series_config(self) -> bool:
        try:
            discovery.load_series_config(self.app.series_root)  # type: ignore[attr-defined]
            return True
        except Exception:
            return False

    def _setup_tree(self) -> None:
        tree = self.query_one("#chapter-tree", Tree)
        tree.show_root = False
        tree.guide_depth = 2

    def _load_data(self) -> None:
        """Read series state from DB and populate the tree."""
        self._chapter_map = {}
        app = self.app
        series_root: Path = app.series_root  # type: ignore[attr-defined]

        tree = self.query_one("#chapter-tree", Tree)
        tree.clear()

        # Series info header
        try:
            config = discovery.load_series_config(series_root)
            name = config["series"]["name"]
            src = config["series"]["source_lang"]
            tgt = config["series"]["target_lang"]
            backend = config.get("llm", {}).get("backend", "gemini")
            stage_models = config.get("llm", {}).get("models", {})
            if backend == 'ollama':
                model = stage_models.get("translation", "qwen3:30b-a3b")
            elif backend == 'qwen':
                model = config.get('qwen_cli', {}).get('model', 'qwen-plus')
            else:
                model = config.get('gemini_cli', {}).get('model', 'gemini-2.5-pro')
            glossary_db = series_root / "glossary.db"
            db.init_glossary_db(glossary_db)
            term_count = len(db.get_terms(glossary_db, src, tgt))
            info_text = (
                f"📚 [bold]{name}[/bold]  |  {src} → {tgt}  |  "
                f"Бэкенд: {backend}  |  Модель: {model}  |  Терминов: {term_count}"
            )
            self.query_one("#series-info", Static).update(info_text)
        except Exception:
            self.query_one("#series-info", Static).update(
                "[red]⚠ Серия не найдена. Нажмите [bold]i[/bold] для инициализации[/red]"
            )
            return

        volume_dirs = sorted(
            d for d in series_root.iterdir()
            if d.is_dir() and (d / "source").is_dir()
        )

        if not volume_dirs:
            tree.root.add("Нет томов — создайте volume-XX/source/")
            return

        for vol_dir in volume_dirs:
            source_dir = vol_dir / "source"
            chunks_db = vol_dir / ".state" / "chunks.db"

            # Scan source files
            source_files = sorted(source_dir.glob("*.txt"))

            if not source_files:
                vol_node = tree.root.add(f"📁 {vol_dir.name}")
                vol_node.add("⏳ Нет .txt файлов")
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

            # Add volume node
            vol_node = tree.root.add(f"📁 {vol_dir.name}")

            for src_file in source_files:
                chapter_name = src_file.stem

                if chapter_name in db_data:
                    info = db_data[chapter_name]
                    stage_label = _STAGE_LABELS.get(info["stage"], info["stage"])
                    errors_str = f" ❌{info['errors']}" if info["errors"] else ""
                    label = f"  📄 {chapter_name} — {stage_label} ({info['done']}/{info['total']}){errors_str}"
                else:
                    label = f"  📄 {chapter_name} — ⏳ Ожидание"

                chapter_node = vol_node.add(label)
                self._chapter_map[str(chapter_node.id)] = (vol_dir.name, chapter_name)

        # Apply search filter if any
        self._apply_search()

    def _apply_search(self) -> None:
        """Filter tree based on search input."""
        search_input = self.query_one("#search-input", Input)
        query = search_input.value.strip().lower()

        tree = self.query_one("#chapter-tree", Tree)

        def filter_node(node, parent_matches: bool = False) -> bool:
            """Recursively filter nodes. Returns True if node or any child matches."""
            node_text = str(node.label).lower()
            matches = query in node_text if query else True
            matches = matches or parent_matches

            # Check children
            child_matches = False
            for child in node.children:
                if filter_node(child, matches):
                    child_matches = True

            # Show/hide based on match
            should_show = matches or child_matches
            # Note: Tree widget doesn't have direct hide/show, we use expand/collapse
            if should_show and query and matches:
                node.expand()
            elif not query:
                node.collapse()

            return should_show

        # Start filtering from root children
        for child in tree.root.children:
            filter_node(child)

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._load_data()

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._apply_search()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-input":
            self._apply_search()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle selection of a chapter node."""
        node_id = str(event.node.id)
        if node_id in self._chapter_map:
            self._selected_volume, self._selected_chapter = self._chapter_map[node_id]
            self.action_translate_selected()

    def action_translate_selected(self) -> None:
        """Show options modal then push TranslationScreen."""
        # Get selected node from tree
        tree = self.query_one("#chapter-tree", Tree)
        if not tree.cursor_node:
            self.notify("Выберите главу для перевода", severity="warning")
            return

        node_id = str(tree.cursor_node.id)
        if node_id not in self._chapter_map:
            self.notify("Выберите главу (а не том)", severity="warning")
            return

        vol_name, chapter_name = self._chapter_map[node_id]
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
        tree = self.query_one("#chapter-tree", Tree)
        volume_name = None
        chapter_name = None
        if tree.cursor_node:
            node_id = str(tree.cursor_node.id)
            if node_id in self._chapter_map:
                volume_name, chapter_name = self._chapter_map[node_id]
        self.app.push_screen(LogScreen(volume_name=volume_name, chapter_name=chapter_name))

    def action_quit(self) -> None:
        self.app.exit()

    # ── Event handlers ────────────────────────────────────────────────────────

    def on_dashboard_refresh_requested(
        self, _: DashboardRefreshRequested
    ) -> None:
        self.action_refresh()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "init_series":
            return not self._has_series_config()
        return True
