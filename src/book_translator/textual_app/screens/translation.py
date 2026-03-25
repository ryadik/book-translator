"""Translation screen — live monitor for an active translation run."""
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
    Select,
    Static,
)
from textual.containers import Horizontal
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


class TranslationScreen(Screen):
    """Live-progress view while a chapter is being translated."""

    ALL_LOGS = "__all__"
    SYSTEM_LOGS = "__system__"

    BINDINGS = [
        Binding("escape", "go_back", "Назад", priority=True),
        Binding("c", "cancel_translation", "Отменить", priority=True),
        Binding("p", "pause_translation", "Пауза", priority=True),
        Binding("f", "focus_worker_filter", "Фильтр", show=False, priority=True),
    ]

    def __init__(
        self,
        series_root: Path,
        chapter_path: Path,
        options: dict | None = None,
    ) -> None:
        super().__init__()
        self._series_root = series_root
        self._chapter_path = chapter_path
        self._options: dict = options or {}
        self._bridge: TextualBridge | None = None
        self._worker: Worker | None = None
        self._start_time: float = 0.0
        self._total_chunks: int = 100  # default; updated by ProgressStarted
        self._completed_chunks: int = 0
        self._log_records: list[dict[str, str | None]] = []
        self._worker_ids: set[str] = set()
        self._active_log_filter = self.ALL_LOGS
        self._current_stage = "startup"
        self._worker_rows: dict[tuple[str, str], dict[str, str]] = {}
        self._latest_error_text: str | None = None
        self._is_paused: bool = False
        self._is_cancelled: bool = False

    def compose(self) -> ComposeResult:
        flags = []
        if self._options.get("debug"):          flags.append("debug")
        if self._options.get("force"):          flags.append("force")
        if self._options.get("resume"):         flags.append("resume")
        if self._options.get("restart_stage"):  flags.append(f"stage={self._options['restart_stage']}")
        flag_str = f"  [dim]{', '.join(flags)}[/dim]" if flags else ""
        yield Header()
        yield Static(
            f"📖 Перевод: [bold]{self._chapter_path.name}[/bold]{flag_str}",
            id="chapter-info",
        )
        yield Static("Инициализация...", id="stage-label")
        yield Static("Ожидание запуска пайплайна...", id="run-status")
        yield ProgressBar(id="chunk-progress", total=100, show_eta=False)
        yield Static("0 / 0  •  Время работы: 00:00", id="progress-row")
        if self._options.get("debug"):
            yield Label("Статусы воркеров", id="worker-status-label")
            yield DataTable(id="worker-status-table", cursor_type="row")
        yield Label("Логи", id="translation-log-label")
        yield Select(
            options=[("Все логи", self.ALL_LOGS), ("Только системные", self.SYSTEM_LOGS)],
            value=self.ALL_LOGS,
            allow_blank=False,
            prompt="Фильтр логов",
            id="worker-filter",
        )
        yield RichLog(id="log-panel", highlight=True, markup=False, wrap=True)
        with Horizontal(id="action-buttons"):
            yield Button("⏸ Пауза", id="pause-btn", variant="warning")
            yield Button("🛑 Отменить", id="cancel-btn", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        self._start_time = monotonic()
        self.set_interval(1.0, self._tick_elapsed)
        if self._options.get("debug"):
            table = self.query_one("#worker-status-table", DataTable)
            table.add_columns("Этап", "Воркер", "Chunk", "Статус", "Обновлено")
        self.query_one("#log-panel", RichLog).write(Text("Ожидание событий пайплайна...", style="dim"))
        self._start_translation()
        self.query_one("#worker-filter", Select).focus()

    def _tick_elapsed(self) -> None:
        """Update the elapsed timer every second."""
        elapsed = int(monotonic() - self._start_time)
        m, s = divmod(elapsed, 60)
        self.query_one("#progress-row", Static).update(
            f"{self._completed_chunks} / {self._total_chunks}  •  Время работы: {m:02d}:{s:02d}"
        )

    def _start_translation(self) -> None:
        from book_translator.ui_textual import TextualBridge
        from book_translator.logger import TUILogHandler
        self._bridge = TextualBridge(self)
        self._log_handler = TUILogHandler(self.app)
        self._worker = self.run_worker(
            self._run_orchestrator,
            thread=True,
            exclusive=True,
        )

    def _run_orchestrator(self) -> None:
        """Runs in a worker thread. Calls orchestrator synchronously."""
        opt = self._options
        try:
            success = orchestrator.run_translation_process(
                series_root=self._series_root,
                chapter_path=self._chapter_path,
                debug=opt.get("debug", False),
                force=opt.get("force", False),
                resume=opt.get("resume", False),
                auto_docx=opt.get("auto_docx", None),
                auto_epub=opt.get("auto_epub", None),
                restart_stage=opt.get("restart_stage"),
                ui=self._bridge,
                log_handler=self._log_handler,
            )
            if self._bridge:
                self._bridge.mark_done()
            self.post_message(
                TranslationFinished(self._chapter_path.stem, success=success is not False)
            )
        except Exception as e:
            if self._bridge:
                self._bridge.mark_done()
            tb = traceback.format_exc()
            self.post_message(
                TranslationFinished(self._chapter_path.stem, success=False)
            )
            self.post_message(UIMessage(f"[bold]Ошибка:[/bold] {e}", level="error"))
            self.post_message(UIMessage(tb, level="error"))

    # ── Message handlers ──────────────────────────────────────────────────────

    def on_progress_started(self, event: ProgressStarted) -> None:
        self._total_chunks = event.total
        self._completed_chunks = 0
        self._current_stage = event.label
        self.query_one("#stage-label", Static).update(
            f"⚙️  Этап: [bold]{event.label}[/bold]"
        )
        self.query_one("#run-status", Static).update("Пайплайн выполняется.")
        bar = self.query_one("#chunk-progress", ProgressBar)
        bar.update(total=event.total, progress=0)
        self.query_one("#progress-row", Static).update(
            f"0 / {event.total}  •  Время работы: 00:00"
        )

    def on_progress_advanced(self, event: ProgressAdvanced) -> None:
        self._completed_chunks = event.completed
        self._total_chunks = event.total
        bar = self.query_one("#chunk-progress", ProgressBar)
        bar.update(progress=event.completed)
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
            self._refresh_worker_filter_options()
        if self._matches_filter(record):
            self.query_one("#log-panel", RichLog).write(self._record_to_text(record))

    def on_translation_finished(self, event: TranslationFinished) -> None:
        bar = self.query_one("#chunk-progress", ProgressBar)
        if event.success:
            bar.update(progress=bar.total or 100)
            self._completed_chunks = self._total_chunks
            self._tick_elapsed()
            self.query_one("#run-status", Static).update("Все этапы завершены успешно.")
        else:
            self.query_one("#run-status", Static).update(
                self._latest_error_text or "Перевод остановлен из-за ошибки. Подробности смотрите в логах."
            )

        # Update buttons
        pause_btn = self.query_one("#pause-btn", Button)
        cancel_btn = self.query_one("#cancel-btn", Button)
        pause_btn.disabled = True
        cancel_btn.label = "← Назад"
        cancel_btn.variant = "success" if event.success else "error"

        msg = (
            f"✅ Перевод завершён: {event.chapter_name}"
            if event.success
            else f"❌ Ошибка при переводе: {event.chapter_name}"
        )
        self.query_one("#stage-label", Static).update(msg)

        # Refresh dashboard data
        try:
            self.app.query_one("DashboardScreen").post_message(DashboardRefreshRequested())
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pause-btn":
            if self._is_paused:
                self.action_resume_translation()
            else:
                self.action_pause_translation()
        elif event.button.id == "cancel-btn":
            if self._bridge and self._bridge.is_running and not self._is_paused:
                self.action_cancel_translation()
            else:
                self.action_go_back()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_pause_translation(self) -> None:
        """Pause the translation process."""
        if not self._bridge or not self._bridge.is_running or self._is_paused:
            return
        self._is_paused = True
        self._bridge.pause()
        self.query_one("#stage-label", Static).update("⏸️ Пауза...")
        self.query_one("#run-status", Static).update("Перевод приостановлен. Нажмите 'Продолжить' для возобновления.")
        pause_btn = self.query_one("#pause-btn", Button)
        pause_btn.label = "▶ Продолжить"
        pause_btn.variant = "success"

    def action_resume_translation(self) -> None:
        """Resume the translation process after pause."""
        if not self._bridge or not self._is_paused:
            return
        self._is_paused = False
        self._bridge.resume()
        self.query_one("#stage-label", Static).update("⚙️  Возобновление...")
        self.query_one("#run-status", Static).update("Пайплайн выполняется.")
        pause_btn = self.query_one("#pause-btn", Button)
        pause_btn.label = "⏸ Пауза"
        pause_btn.variant = "warning"
        # Restart the worker with resume flag
        self._options["resume"] = True
        self._start_translation()

    def action_cancel_translation(self) -> None:
        """Cancel the translation process completely."""
        self._is_cancelled = True
        if self._bridge:
            self._bridge.cancel()
        if self._worker:
            self._worker.cancel()
        self.query_one("#stage-label", Static).update("🛑 Отмена...")
        self.query_one("#run-status", Static).update("Перевод отменён.")
        pause_btn = self.query_one("#pause-btn", Button)
        cancel_btn = self.query_one("#cancel-btn", Button)
        pause_btn.disabled = True
        cancel_btn.label = "← Назад"
        cancel_btn.variant = "primary"

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_focus_worker_filter(self) -> None:
        self.query_one("#worker-filter", Select).focus()

    def on_unmount(self) -> None:
        """Ensure translation is cancelled if screen is removed."""
        if self._bridge and self._bridge.is_running:
            self._bridge.cancel()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "worker-filter":
            return
        self._active_log_filter = str(event.value)
        self._rerender_log_panel()

    def _refresh_worker_filter_options(self) -> None:
        options = [
            ("Все логи", self.ALL_LOGS),
            ("Только системные", self.SYSTEM_LOGS),
        ]
        for worker_id in sorted(self._worker_ids):
            options.append((f"Воркер {worker_id}", worker_id))
        select = self.query_one("#worker-filter", Select)
        current_value = self._active_log_filter if self._active_log_filter in {value for _, value in options} else self.ALL_LOGS
        select.set_options(options)
        select.value = current_value
        self._active_log_filter = current_value

    def _matches_filter(self, record: dict[str, str | None]) -> bool:
        worker_id = record.get("worker_id")
        if self._active_log_filter == self.ALL_LOGS:
            return True
        if self._active_log_filter == self.SYSTEM_LOGS:
            return not worker_id
        return worker_id == self._active_log_filter

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

    def _rerender_log_panel(self) -> None:
        log = self.query_one("#log-panel", RichLog)
        log.clear()
        matched = False
        for record in self._log_records:
            if self._matches_filter(record):
                log.write(self._record_to_text(record))
                matched = True
        if not matched:
            log.write(Text("Для выбранного фильтра логов пока ничего нет.", style="dim"))

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
        table = self.query_one("#worker-status-table", DataTable)
        table.clear()
        for item_key in sorted(self._worker_rows):
            item = self._worker_rows[item_key]
            table.add_row(
                item["stage"],
                item["worker_id"],
                item["chunk_label"],
                item["status"],
                item["updated_at"],
                key=f"{item['stage']}::{item['worker_id']}",
            )
