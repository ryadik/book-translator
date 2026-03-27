"""Translation options modal — configure parameters before starting translation."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Label, Select
from textual.containers import Horizontal, Vertical


_STAGE_OPTIONS = [
    ("— не менять —", "none"),
    ("Discovery (поиск терминов)", "discovery"),
    ("Translation (перевод)", "translation"),
    ("Proofreading (вычитка)", "proofreading"),
    ("Global proofreading (глоб. вычитка)", "global_proofreading"),
]


class TranslationOptionsModal(ModalScreen):
    """Configure translation parameters before launching."""

    BINDINGS = [
        Binding("escape", "cancel", "Отмена", priority=True),
        Binding("ctrl+enter", "start", "Начать", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="options-box"):
            yield Label("⚙️  Параметры перевода", id="options-title")
            yield Checkbox("Режим отладки (--debug)", id="check-debug")
            yield Checkbox("Принудительный перезапуск (--force)", id="check-force")
            yield Checkbox("Возобновить прерванный (--resume)", id="check-resume")
            yield Checkbox("Конвертировать в .docx", id="check-docx")
            yield Checkbox("Конвертировать в .epub", id="check-epub")
            yield Label("Перезапустить с этапа:", classes="field-label")
            yield Select(
                [(label, val) for label, val in _STAGE_OPTIONS],
                id="select-stage",
                value="none",
                allow_blank=False,
            )
            with Horizontal(id="options-buttons"):
                yield Button("▶ Начать перевод", id="btn-start", variant="primary")
                yield Button("📦 Только конвертировать", id="btn-convert", variant="default")
                yield Button("Отмена", id="btn-cancel")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_mount(self) -> None:
        self.query_one("#check-debug", Checkbox).focus()

    def action_start(self) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            self._submit(convert_only=False)
        elif event.button.id == "btn-convert":
            self._submit(convert_only=True)
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def _submit(self, convert_only: bool = False) -> None:
        stage_val = self.query_one("#select-stage", Select).value
        restart_stage = None if (not stage_val or stage_val == "none") else str(stage_val)
        self.dismiss({
            "convert_only":  convert_only,
            "debug":         self.query_one("#check-debug",  Checkbox).value,
            "force":         self.query_one("#check-force",  Checkbox).value,
            "resume":        self.query_one("#check-resume", Checkbox).value,
            "auto_docx":     True if self.query_one("#check-docx", Checkbox).value else None,
            "auto_epub":     True if self.query_one("#check-epub", Checkbox).value else None,
            "restart_stage": restart_stage,
        })
