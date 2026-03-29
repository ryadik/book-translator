"""Log screen — persisted run viewer with parsed worker states."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Select, Static, TextArea

from book_translator.log_viewer import (
    build_worker_status_rows,
    discover_run_manifests,
    format_record_line,
    load_run_records,
)


class LogScreen(Screen):
    """Full-screen log viewer for persisted run history."""

    STREAM_ALL = "__all__"
    STREAM_SYSTEM = "system"
    STREAM_INPUT = "worker_input"
    STREAM_OUTPUT = "worker_output"
    STAGE_ALL = "__all__"

    BINDINGS = [
        Binding("escape", "go_back", "Назад", priority=True),
        Binding("r", "reload", "Обновить", priority=True),
    ]

    def __init__(self, volume_name: str | None = None, chapter_name: str | None = None) -> None:
        super().__init__()
        self._volume_name = volume_name
        self._chapter_name = chapter_name
        self._manifests: list[dict] = []
        self._records: list[dict] = []
        self._active_stream = self.STREAM_ALL
        self._active_stage = self.STAGE_ALL

    def compose(self) -> ComposeResult:
        title = "История запусков"
        if self._chapter_name:
            title = f"Логи: {self._chapter_name}"
        yield Header()
        yield Static(title, id="log-title")
        yield Select(
            options=[("Загрузка...", "__loading__")],
            value="__loading__",
            prompt="Запуск",
            allow_blank=False,
            id="run-select",
        )
        yield Static("", id="run-summary")
        yield Select(
            options=[
                ("Все потоки", self.STREAM_ALL),
                ("System", self.STREAM_SYSTEM),
                ("Worker input", self.STREAM_INPUT),
                ("Worker output", self.STREAM_OUTPUT),
            ],
            value=self.STREAM_ALL,
            allow_blank=False,
            prompt="Поток",
            id="log-filter",
        )
        yield Select(
            options=[("Все этапы", self.STAGE_ALL)],
            value=self.STAGE_ALL,
            allow_blank=False,
            prompt="Этап",
            id="stage-filter",
        )
        yield Static("Статусы воркеров", id="worker-status-label")
        yield DataTable(id="worker-status-table", cursor_type="row")
        yield TextArea("", id="log-view", read_only=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#worker-status-table", DataTable)
        table.add_columns("Этап", "Воркер", "Chunk", "Статус", "Обновлено")
        self.action_reload()
        self.query_one("#run-select", Select).focus()

    def action_reload(self) -> None:
        self._manifests = discover_run_manifests(
            self.app.series_root,  # type: ignore[attr-defined]
            volume_name=self._volume_name,
            chapter_name=self._chapter_name,
        )
        if not self._manifests and (self._volume_name or self._chapter_name):
            self._manifests = discover_run_manifests(self.app.series_root)  # type: ignore[attr-defined]
            self.query_one("#log-title", Static).update("История запусков")
        self._refresh_run_select()
        if not self._manifests:
            self._records = []
            self._render_worker_table([])
            self.query_one("#run-summary", Static).update("Запусков пока нет.")
            self.query_one("#log-view", TextArea).load_text("Для выбранной главы пока нет сохранённых запусков.")
            return
        self._load_selected_run()

    def _refresh_run_select(self) -> None:
        select = self.query_one("#run-select", Select)
        options = []
        for manifest in self._manifests:
            started_at = str(manifest.get("started_at", ""))[11:19]
            label = (
                f"{started_at}  {manifest.get('chapter_name', '?')}  "
                f"[{manifest.get('status', 'unknown')}]"
            )
            options.append((label, str(manifest["run_dir"])))
        if not options:
            select.set_options([("Нет запусков", "__none__")])
            select.value = "__none__"
            return
        current_value = select.value if select.value not in (Select.BLANK, None) else None
        select.set_options(options)
        allowed = {value for _, value in options}
        select.value = current_value if current_value in allowed else options[0][1]

    def _load_selected_run(self) -> None:
        select = self.query_one("#run-select", Select)
        if select.value in (Select.BLANK, None, "__none__"):
            return
        self._records = load_run_records(str(select.value))
        self._refresh_stage_filter()
        self._render_worker_table(self._filtered_records())
        self._update_run_summary(str(select.value))
        self._render_log()

    def _update_run_summary(self, run_dir: str) -> None:
        summary = self.query_one("#run-summary", Static)
        manifest = next((item for item in self._manifests if str(item.get("run_dir")) == run_dir), None)
        if manifest is None:
            summary.update("")
            return
        started_at = str(manifest.get("started_at", ""))
        finished_at = str(manifest.get("finished_at", ""))
        status = str(manifest.get("status", "unknown"))
        stage = str(manifest.get("current_stage", "unknown"))
        error = str(manifest.get("error", "")).strip()
        line = (
            f"Статус: {status}  |  Этап: {stage}  |  "
            f"Старт: {started_at or '—'}  |  Финиш: {finished_at or '—'}"
        )
        if error and error != "None":
            line += f"\nОшибка: {error}"
        summary.update(line)

    def _refresh_stage_filter(self) -> None:
        stage_values = [self.STAGE_ALL]
        for record in self._records:
            stage = str(record.get("stage") or "")
            if stage and stage not in stage_values:
                stage_values.append(stage)
        select = self.query_one("#stage-filter", Select)
        options = [("Все этапы", self.STAGE_ALL)]
        options.extend((stage, stage) for stage in stage_values if stage != self.STAGE_ALL)
        current_value = self._active_stage if self._active_stage in {value for _, value in options} else self.STAGE_ALL
        select.set_options(options)
        select.value = current_value
        self._active_stage = current_value

    def _filtered_records(self) -> list[dict]:
        return [record for record in self._records if self._record_matches_filters(record)]

    def _render_worker_table(self, records: list[dict]) -> None:
        table = self.query_one("#worker-status-table", DataTable)
        table.clear()
        for row in build_worker_status_rows(records):
            timestamp = row["timestamp"][11:19] if len(row["timestamp"]) >= 19 else row["timestamp"]
            table.add_row(
                row["stage"],
                row["worker_id"],
                row["chunk_label"],
                row["status"],
                timestamp,
            )

    def _record_matches_filters(self, record: dict) -> bool:
        if self._active_stream != self.STREAM_ALL and str(record.get("stream")) != self._active_stream:
            return False
        if self._active_stage != self.STAGE_ALL and str(record.get("stage")) != self._active_stage:
            return False
        return True

    def _render_log(self) -> None:
        matched = False
        lines = []
        filtered_records = self._filtered_records()
        self._render_worker_table(filtered_records)
        for record in filtered_records:
            if self._record_matches_filters(record):
                lines.append(format_record_line(record))
                matched = True
        text = "\n".join(lines) if matched else "Для выбранного фильтра нет записей."
        self.query_one("#log-view", TextArea).load_text(text)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "run-select":
            self._load_selected_run()
        elif event.select.id == "log-filter":
            self._active_stream = str(event.value)
            self._render_log()
        elif event.select.id == "stage-filter":
            self._active_stage = str(event.value)
            self._render_log()

    def action_go_back(self) -> None:
        self.app.pop_screen()
