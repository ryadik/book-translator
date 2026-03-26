"""Batch translation screen — translate multiple chapters sequentially."""
from __future__ import annotations

import traceback
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    ProgressBar,
    RichLog,
    Static,
)
from textual.worker import Worker

from book_translator import orchestrator
from book_translator.log_viewer import detect_stage, parse_worker_event
from book_translator.textual_app.messages import (
    DashboardRefreshRequested,
    ProgressAdvanced,
    ProgressFinished,
    ProgressStarted,
    TUILogRecord,
    TranslationFinished,
    UIMessage,
)

if TYPE_CHECKING:
    from book_translator.ui_textual import TextualBridge


class BatchTranslationScreen(Screen):
    """Live-progress view for batch translation of multiple chapters."""

    ALL_LOGS = "__all__"
    SYSTEM_LOGS = "__system__"

    BINDINGS = [
        Binding("escape", "go_back", "Назад", priority=True),
        Binding("c", "cancel_translation", "Отменить", priority=True),
    ]

    def __init__(
        self,
        chapters: list[tuple[Path, Path]],  # (chapter_path, series_root)
        options: dict | None = None,
    ) -> None:
        super().__init__()
        self._chapters = chapters
        self._options: dict = options or {}
        self._bridge: TextualBridge | None = None
        self._worker: Worker | None = None
        self._start_time: float = 0.0
        self._total_chapters = len(chapters)
        self._completed_chapters = 0
        self._current_chapter_idx = 0
        self._log_records: list[dict[str, str | None]] = []
        self._worker_ids: set[str] = set()
        self._active_log_filter = self.ALL_LOGS
        self._current_stage = "startup"
        self._worker_rows: dict[tuple[str, str], dict[str, str]] = {}
        self._latest_error_text: str | None = None
        self._cancelled = False

    def compose(self) -> ComposeResult:
        flags = []
        if self._options.get("debug"):          flags.append("debug")
        if self._options.get("force"):          flags.append("force")
        if self._options.get("resume"):         flags.append("resume")
        if self._options.get("restart_stage"):  flags.append(f"stage={self._options['restart_stage']}")
        flag_str = f"  [dim]{', '.join(flags)}[/dim]" if flags else ""
        yield Header()
        yield Static(
            f"📚 Пакетный перевод: [bold]{self._total_chapters} глав[/bold]{flag_str}",
            id="batch-info",
        )
        yield Static("Инициализация...", id="stage-label")
        yield Static("Ожидание запуска...", id="run-status")
        yield ProgressBar(id="chapter-progress", total=self._total_chapters, show_eta=False)
        yield Static(f"0 / {self._total_chapters} глав  •  Время работы: 00:00", id="progress-row")
        yield Label("Прогресс по главам", id="chapter-list-label")
        yield DataTable(id="chapter-status-table", cursor_type="row")
        yield Label("Логи", id="translation-log-label")
        yield RichLog(id="log-panel", highlight=True, markup=False, wrap=True)
        yield Button("Отменить", id="cancel-btn", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        self._start_time = monotonic()
        self.set_interval(1.0, self._tick_elapsed)
        table = self.query_one("#chapter-status-table", DataTable)
        table.add_columns("Глава", "Статус", "Этап")
        for chapter_path, _ in self._chapters:
            table.add_row(chapter_path.name, "⏳ Ожидание", "—")
        self.query_one("#log-panel", RichLog).write(Text("Ожидание запуска...", style="dim"))
        self._start_translation()

    def _tick_elapsed(self) -> None:
        """Update the elapsed timer every second."""
        elapsed = int(monotonic() - self._start_time)
        m, s = divmod(elapsed, 60)
        self.query_one("#progress-row", Static).update(
            f"{self._completed_chapters} / {self._total_chapters} глав  •  Время работы: {m:02d}:{s:02d}"
        )

    def _start_translation(self) -> None:
        from book_translator.ui_textual import TextualBridge
        from book_translator.logger import TUILogHandler
        self._bridge = TextualBridge(self)
        self._log_handler = TUILogHandler(self.app)
        self._worker = self.run_worker(
            self._run_batch_orchestrator,
            thread=True,
            exclusive=True,
        )

    def _run_batch_orchestrator(self) -> None:
        """Runs in a worker thread. Processes chapters sequentially."""
        opt = self._options

        for idx, (chapter_path, series_root) in enumerate(self._chapters):
            if self._cancelled:
                break

            self._current_chapter_idx = idx
            self.post_message(UIMessage(f"[bold]Начало перевода:[/bold] {chapter_path.name}", level="info"))

            try:
                success = orchestrator.run_translation_process(
                    series_root=series_root,
                    chapter_path=chapter_path,
                    debug=opt.get("debug", False),
                    force=opt.get("force", False),
                    resume=opt.get("resume", False),
                    auto_docx=opt.get("auto_docx", None),
                    auto_epub=opt.get("auto_epub", None),
                    restart_stage=opt.get("restart_stage"),
                    ui=self._bridge,
                    log_handler=self._log_handler,
                )

                if success is not False:
                    self._completed_chapters += 1
                    self.post_message(TranslationFinished(chapter_path.stem, success=True))
                else:
                    self.post_message(TranslationFinished(chapter_path.stem, success=False))
                    # Continue with next chapter even if this one failed

            except Exception as e:
                tb = traceback.format_exc()
                self.post_message(TranslationFinished(chapter_path.stem, success=False))
                self.post_message(UIMessage(f"[bold]Ошибка в {chapter_path.name}:[/bold] {e}", level="error"))
                self.post_message(UIMessage(tb, level="error"))
                # Continue with next chapter

        if self._bridge:
            self._bridge.mark_done()

    # ── Message handlers ──────────────────────────────────────────────────────

    def on_progress_started(self, event: ProgressStarted) -> None:
        self._current_stage = event.label
        self.query_one("#stage-label", Static).update(
            f"⚙️  Этап: [bold]{event.label}[/bold]"
        )
        self.query_one("#run-status", Static).update(
            f"Перевод: {self._chapters[self._current_chapter_idx][0].name}"
        )

    def on_progress_advanced(self, event: ProgressAdvanced) -> None:
        # Update chapter progress bar based on overall progress
        progress = self._completed_chapters + (event.completed / max(event.total, 1))
        bar = self.query_one("#chapter-progress", ProgressBar)
        bar.update(progress=progress)
        self._tick_elapsed()

    def on_progress_finished(self, event: ProgressFinished) -> None:
        self.query_one("#stage-label", Static).update(
            f"✅ Этап завершён: [bold]{event.label}[/bold]"
        )

    def on_uimessage(self, event: UIMessage) -> None:
        if event.level == "error":
            self._latest_error_text = event.text
            rendered = Text.from_markup(event.text, style="red")
        elif event.level == "success":
            rendered = Text.from_markup(event.text, style="green")
        else:
            rendered = Text.from_markup(event.text)
        self.query_one("#log-panel", RichLog).write(rendered)

    def on_tuilog_record(self, event: TUILogRecord) -> None:
        record = {
            "text": event.text,
            "level": event.level,
            "logger_name": event.logger_name,
            "worker_id": event.worker_id,
        }
        self._log_records.append(record)
        if event.level in ("ERROR", "CRITICAL"):
            self._latest_error_text = event.text
        self._current_stage = detect_stage(event.text, self._current_stage) or self._current_stage
        self._update_worker_status(event)
        if event.worker_id and event.worker_id not in self._worker_ids:
            self._worker_ids.add(event.worker_id)
        self.query_one("#log-panel", RichLog).write(self._record_to_text(record))

    def on_translation_finished(self, event: TranslationFinished) -> None:
        # Update chapter status table
        table = self.query_one("#chapter-status-table", DataTable)
        for row_idx, (chapter_path, _) in enumerate(self._chapters):
            if chapter_path.stem == event.chapter_name:
                status = "✅ Готово" if event.success else "❌ Ошибка"
                # Update row - clear and re-add all rows
                table.clear()
                for i, (cp, _) in enumerate(self._chapters):
                    if i < self._completed_chapters:
                        s = "✅ Готово"
                        st = "complete"
                    elif i == self._current_chapter_idx:
                        s = "🔄 В работе" if not event.success else "✅ Готово"
                        st = self._current_stage
                    else:
                        s = "⏳ Ожидание"
                        st = "—"
                    table.add_row(cp.name, s, st)
                break

        # Check if all chapters are done
        if self._completed_chapters >= self._total_chapters:
            bar = self.query_one("#chapter-progress", ProgressBar)
            bar.update(progress=bar.total)
            self.query_one("#run-status", Static).update("Все главы обработаны.")
            cancel_btn = self.query_one("#cancel-btn", Button)
            cancel_btn.label = "← Назад"
            cancel_btn.variant = "success"
            self.query_one("#stage-label", Static).update("✅ Пакетный перевод завершён")

        # Refresh dashboard data
        try:
            self.app.query_one("DashboardScreen").post_message(DashboardRefreshRequested())
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            if self._bridge and self._bridge.is_running:
                self.action_cancel_translation()
            else:
                self.action_go_back()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_cancel_translation(self) -> None:
        self._cancelled = True
        if self._bridge:
            self._bridge.cancel()
        if self._worker:
            self._worker.cancel()
        self.query_one("#stage-label", Static).update("🛑 Отмена...")

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_unmount(self) -> None:
        """Ensure translation is cancelled if screen is removed."""
        self._cancelled = True
        if self._bridge and self._bridge.is_running:
            self._bridge.cancel()

    def _record_to_text(self, record: dict[str, str | None]) -> Text:
        text = str(record.get("text") or "")
        level = str(record.get("level") or "INFO")
        if level in ("ERROR", "CRITICAL"):
            return Text(text, style="red")
        if level == "WARNING":
            return Text(text, style="yellow")
        if record.get("logger_name") in {"worker_input", "worker_output"}:
            return Text(text, style="cyan")
        return Text(text)

    def _update_worker_status(self, event: TUILogRecord) -> None:
        if not self._options.get("debug"):
            return
        worker_event = parse_worker_event(event.text, self._current_stage)
        if worker_event is None:
            return
        updated_at = event.text[:8]
        row = {
            "stage": worker_event["stage"],
            "worker_id": worker_event["worker_id"],
            "chunk_label": worker_event["chunk_label"],
            "status": worker_event["status"],
            "updated_at": updated_at,
        }
        self._worker_rows[(worker_event["stage"], worker_event["worker_id"])] = row
