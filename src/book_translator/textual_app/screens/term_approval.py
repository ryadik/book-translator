"""Term approval screen — shown when new terms are discovered during translation."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Static
from textual.containers import Horizontal, Vertical

from book_translator import db, glossary_manager


class _EditTermModal(ModalScreen):
    """Small modal for editing a single term's translation."""

    def __init__(self, source: str, target: str, comment: str) -> None:
        super().__init__()
        self._source = source
        self._target = target
        self._comment = comment

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Label(f"Редактировать: {self._source}", id="modal-title")
            yield Input(placeholder="Перевод (target)", id="input-target", value=self._target)
            yield Input(placeholder="Комментарий", id="input-comment", value=self._comment)
            with Horizontal():
                yield Button("Сохранить", id="btn-ok", variant="primary")
                yield Button("Отмена", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-ok":
            self.dismiss({
                "target": self.query_one("#input-target", Input).value.strip(),
                "comment": self.query_one("#input-comment", Input).value.strip(),
            })
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "enter":
            self.dismiss({
                "target": self.query_one("#input-target", Input).value.strip(),
                "comment": self.query_one("#input-comment", Input).value.strip(),
            })


class TermApprovalScreen(ModalScreen):
    """Modal that presents discovered terms for user approval/editing.

    Blocks the orchestrator thread (via threading.Event callback) until the
    user confirms or cancels.
    """

    BINDINGS = [
        Binding("e", "edit_selected", "Изменить", priority=True),
        Binding("d", "delete_selected", "Удалить", priority=True),
        Binding("enter", "confirm", "Подтвердить", priority=True),
        Binding("escape", "skip", "Пропустить", priority=True),
    ]

    def __init__(
        self,
        terms: list[dict],
        tsv_path: Path,
        glossary_db_path: Path,
        source_lang: str,
        target_lang: str,
        callback: Callable[[int], None],
    ) -> None:
        super().__init__()
        self._terms: list[dict] = list(terms)  # mutable copy
        self._tsv_path = tsv_path
        self._glossary_db_path = glossary_db_path
        self._source_lang = source_lang
        self._target_lang = target_lang
        self._callback = callback

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-box"):
            yield Label(
                f"📝 Найдено [bold]{len(self._terms)}[/bold] новых терминов. "
                "Проверьте и подтвердите.",
                id="approval-title",
            )
            yield DataTable(id="terms-table", cursor_type="row")
            yield Static(
                "[dim]e — изменить  •  d — удалить  •  Enter — подтвердить  •  Esc — пропустить[/dim]"
            )
            with Horizontal(id="approval-buttons"):
                yield Button("✅ Подтвердить", id="btn-confirm", variant="primary")
                yield Button("⏭ Пропустить", id="btn-skip", variant="default")

    def on_mount(self) -> None:
        table = self.query_one("#terms-table", DataTable)
        table.add_columns("Оригинал", "Перевод", "Комментарий")
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#terms-table", DataTable)
        cursor = table.cursor_row
        table.clear()
        for i, t in enumerate(self._terms):
            table.add_row(
                t.get("source", ""),
                t.get("target", ""),
                t.get("comment", ""),
                key=str(i),
            )
        # Restore cursor position
        if self._terms:
            table.move_cursor(row=min(cursor, len(self._terms) - 1))

    def _get_cursor_index(self) -> int | None:
        """Return the index into self._terms for the current cursor row."""
        table = self.query_one("#terms-table", DataTable)
        if table.cursor_row < 0 or table.cursor_row >= len(self._terms):
            return None
        return table.cursor_row

    def action_edit_selected(self) -> None:
        idx = self._get_cursor_index()
        if idx is None:
            return
        term = self._terms[idx]

        def _on_result(result) -> None:
            if result is None:
                return
            self._terms[idx] = {
                "source": term["source"],
                "target": result["target"],
                "comment": result["comment"],
            }
            self._refresh_table()

        self.app.push_screen(
            _EditTermModal(
                source=term.get("source", ""),
                target=term.get("target", ""),
                comment=term.get("comment", ""),
            ),
            _on_result,
        )

    def action_delete_selected(self) -> None:
        idx = self._get_cursor_index()
        if idx is None:
            return
        del self._terms[idx]
        self._refresh_table()

    def action_confirm(self) -> None:
        self._import_and_dismiss(self._terms)

    def action_skip(self) -> None:
        self._callback(0)
        self.dismiss()

    def _import_and_dismiss(self, terms: list[dict]) -> None:
        term_list = [
            {
                "term_source": t.get("source", ""),
                "term_target": t.get("target", ""),
                "comment": t.get("comment", ""),
            }
            for t in terms
            if t.get("source") and t.get("target")
        ]
        if term_list:
            glossary_manager.generate_approval_tsv(term_list, self._tsv_path)
            count = glossary_manager.import_tsv(
                self._glossary_db_path,
                self._tsv_path,
                self._source_lang,
                self._target_lang,
            )
        else:
            count = 0
        self._callback(count)
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            self.action_confirm()
        elif event.button.id == "btn-skip":
            self.action_skip()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a row → edit it."""
        self.action_edit_selected()
