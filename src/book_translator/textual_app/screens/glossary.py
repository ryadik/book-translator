"""Glossary screen — full CRUD for translation terms."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
)
from textual.containers import Horizontal, Vertical

from book_translator import db, discovery
from book_translator import glossary_manager


class _TermModal(ModalScreen):
    """Reusable modal for both adding and editing a term."""

    def __init__(
        self,
        title: str,
        source: str = "",
        target: str = "",
        comment: str = "",
        source_readonly: bool = False,
    ) -> None:
        super().__init__()
        self._title = title
        self._source = source
        self._target = target
        self._comment = comment
        self._source_readonly = source_readonly

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Label(self._title, id="modal-title")
            yield Input(
                placeholder="Оригинал (source)",
                id="input-source",
                value=self._source,
                disabled=self._source_readonly,
            )
            yield Input(placeholder="Перевод (target)", id="input-target", value=self._target)
            yield Input(placeholder="Комментарий (опционально)", id="input-comment", value=self._comment)
            with Horizontal():
                yield Button("Сохранить", id="btn-ok", variant="primary")
                yield Button("Отмена", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-ok":
            source = self.query_one("#input-source", Input).value.strip()
            target = self.query_one("#input-target", Input).value.strip()
            comment = self.query_one("#input-comment", Input).value.strip()
            if source and target:
                self.dismiss({"source": source, "target": target, "comment": comment})
            else:
                self.query_one("#modal-title", Label).update(
                    "[red]Заполните оригинал и перевод[/red]"
                )
        elif event.button.id == "btn-cancel":
            self.dismiss(None)


class GlossaryScreen(Screen):
    """View and manage all glossary terms."""

    BINDINGS = [
        Binding("escape", "go_back", "Назад", priority=True),
        Binding("a", "add_term", "Добавить", priority=True),
        Binding("enter", "edit_selected", "Изменить", priority=True),
        Binding("d", "delete_selected", "Удалить", priority=True),
        Binding("e", "export_tsv", "Экспорт", priority=True),
        Binding("r", "refresh", "Обновить", priority=True),
        Binding("f", "focus_search", "Поиск", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="controls-bar"):
            yield Input(placeholder="Поиск...", id="search-input")
            yield Button("+ Добавить", id="btn-add", variant="primary")
            yield Button("✏️ Изменить", id="btn-edit")
            yield Button("🗑 Удалить", id="btn-delete", variant="error")
            yield Button("Экспорт TSV", id="btn-export")
        yield Static("", id="status-bar")
        yield DataTable(id="term-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_table()
        self._load_terms()
        self.query_one("#term-table", DataTable).focus()

    def _series_root(self) -> Path:
        return self.app.series_root  # type: ignore[attr-defined]

    def _config(self):
        return discovery.load_series_config(self._series_root())

    def _setup_table(self) -> None:
        table = self.query_one("#term-table", DataTable)
        table.add_columns("Оригинал", "Перевод", "Комментарий")

    def _load_terms(self, filter_text: str = "") -> None:
        config = self._config()
        glossary_db = self._series_root() / "glossary.db"
        src = config["series"]["source_lang"]
        tgt = config["series"]["target_lang"]

        db.init_glossary_db(glossary_db)
        terms = db.get_terms(glossary_db, src, tgt)

        if filter_text:
            ft = filter_text.lower()
            terms = [
                t for t in terms
                if ft in t["term_source"].lower() or ft in t["term_target"].lower()
            ]

        table = self.query_one("#term-table", DataTable)
        table.clear()
        for t in terms:
            table.add_row(
                t["term_source"],
                t["term_target"],
                t.get("comment") or "",
            )
        self.query_one("#status-bar", Static).update(
            f"[dim]{len(terms)} терминов  •  Enter — изменить  •  a — добавить  •  d — удалить[/dim]"
        )

    def _get_selected_row(self) -> tuple[str, str, str] | None:
        """Return (source, target, comment) for the cursor row, or None."""
        table = self.query_one("#term-table", DataTable)
        if table.cursor_row < 0:
            return None
        try:
            row = table.get_row_at(table.cursor_row)
            return str(row[0]), str(row[1]), str(row[2])
        except Exception:
            return None

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._load_terms(self.query_one("#search-input", Input).value)

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_add_term(self) -> None:
        def _on_result(result):
            if result is None:
                return
            config = self._config()
            glossary_db = self._series_root() / "glossary.db"
            db.add_term(
                glossary_db,
                result["source"],
                result["target"],
                config["series"]["source_lang"],
                config["series"]["target_lang"],
                result.get("comment", ""),
            )
            self._load_terms()

        self.app.push_screen(_TermModal("Добавить термин"), _on_result)

    def action_edit_selected(self) -> None:
        row = self._get_selected_row()
        if row is None:
            self.notify("Выберите термин для редактирования", severity="warning")
            return
        source, target, comment = row

        def _on_result(result):
            if result is None:
                return
            config = self._config()
            glossary_db = self._series_root() / "glossary.db"
            # Delete old entry (by original source key), then insert updated
            with db.connection(glossary_db) as conn:
                conn.execute(
                    "DELETE FROM glossary WHERE term_source = ? AND source_lang = ?",
                    (source, config["series"]["source_lang"]),
                )
            db.add_term(
                glossary_db,
                result["source"],
                result["target"],
                config["series"]["source_lang"],
                config["series"]["target_lang"],
                result.get("comment", ""),
            )
            self._load_terms()
            self.notify(f"Обновлён: {result['source']}")

        self.app.push_screen(
            _TermModal(
                "Редактировать термин",
                source=source,
                target=target,
                comment=comment,
                source_readonly=False,
            ),
            _on_result,
        )

    def action_delete_selected(self) -> None:
        row = self._get_selected_row()
        if row is None:
            return
        source = row[0]

        config = self._config()
        glossary_db = self._series_root() / "glossary.db"
        with db.connection(glossary_db) as conn:
            conn.execute(
                "DELETE FROM glossary WHERE term_source = ? AND source_lang = ?",
                (source, config["series"]["source_lang"]),
            )
        self._load_terms()
        self.notify(f"Удалён: {source}", severity="warning")

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a row → edit it."""
        self.action_edit_selected()

    def action_export_tsv(self) -> None:
        config = self._config()
        glossary_db = self._series_root() / "glossary.db"
        output_path = self._series_root() / "glossary_export.tsv"
        with open(output_path, "w", encoding="utf-8") as f:
            count = glossary_manager.export_tsv(
                glossary_db, f,
                config["series"]["source_lang"],
                config["series"]["target_lang"],
            )
        self.notify(f"Экспортировано {count} терминов → {output_path.name}")

    # ── Event handlers ────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._load_terms(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-add":
            self.action_add_term()
        elif event.button.id == "btn-edit":
            self.action_edit_selected()
        elif event.button.id == "btn-delete":
            self.action_delete_selected()
        elif event.button.id == "btn-export":
            self.action_export_tsv()
