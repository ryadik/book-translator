import asyncio
import json
from argparse import Namespace
from pathlib import Path

from textual.widgets import Button, DataTable, ProgressBar, Select, Static

from book_translator.commands.init_cmd import run_init
from book_translator.logger import TUILogHandler
from book_translator.log_viewer import (
    build_worker_status_rows,
    create_run_artifacts,
    load_run_records,
    update_run_manifest,
)
from book_translator.textual_app.app import BookTranslatorApp
from book_translator.textual_app.messages import (
    ProgressAdvanced,
    ProgressStarted,
    TUILogRecord,
    TranslationFinished,
)
from book_translator.textual_app.screens.translation import TranslationScreen


def _run(coro):
    return asyncio.run(coro)


def _create_series(tmp_path: Path, name: str = "Series") -> Path:
    old_cwd = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        run_init(Namespace(name=name, source_lang="ja", target_lang="ru"))
    finally:
        os.chdir(old_cwd)
    return tmp_path / name


async def _press(app: BookTranslatorApp, *keys: str) -> None:
    async with app.run_test() as pilot:
        for key in keys:
            await pilot.press(key)
        await pilot.pause()


def test_dashboard_hotkey_opens_logs_screen(tmp_path):
    series_root = _create_series(tmp_path)
    app = BookTranslatorApp(series_root=series_root)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("l")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "LogScreen"

    _run(scenario())


def test_dashboard_init_hotkey_is_blocked_for_initialized_series(tmp_path):
    series_root = _create_series(tmp_path)
    app = BookTranslatorApp(series_root=series_root)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("i")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "DashboardScreen"

    _run(scenario())


def test_theme_choice_persists_between_sessions(tmp_path, monkeypatch):
    config_path = tmp_path / "tui.json"
    monkeypatch.setattr("book_translator.textual_app.app._UI_CONFIG", config_path)

    app = BookTranslatorApp(series_root=tmp_path)

    async def toggle_theme():
        async with app.run_test() as pilot:
            before = app.theme
            await pilot.press("ctrl+d")
            await pilot.pause()
            assert app.theme != before
            await pilot.press("ctrl+q")

    _run(toggle_theme())
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["theme"] in {"textual-dark", "textual-light"}

    app2 = BookTranslatorApp(series_root=tmp_path)

    async def verify_theme():
        async with app2.run_test() as pilot:
            await pilot.pause()
            assert app2.theme == saved["theme"]

    _run(verify_theme())


def test_log_screen_falls_back_to_global_history_when_selected_chapter_has_no_runs(tmp_path):
    series_root = _create_series(tmp_path)
    volume_logs_dir = series_root / "volume-01" / ".state" / "logs"
    artifacts = create_run_artifacts(
        volume_logs_dir,
        volume_name="volume-01",
        chapter_name="other-chapter",
        debug_mode=True,
    )
    update_run_manifest(
        artifacts["manifest_path"],
        current_stage="translation",
        status="failed",
        error="boom",
    )
    Path(artifacts["system_log_path"]).write_text(
        json.dumps(
            {
                "timestamp": "2026-03-24T12:00:00+08:00",
                "level": "ERROR",
                "name": "system",
                "message": "[Orchestrator] ЭТАП 2: Перевод чанков",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    app = BookTranslatorApp(series_root=series_root)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("l")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "LogScreen"
            summary_widget = app.screen.query_one("#run-summary", Static)
            summary_text = str(summary_widget.render())
            assert "failed" in summary_text
            assert "boom" in summary_text

    _run(scenario())


def test_persisted_logs_build_worker_rows_for_each_stage(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "system_output.log").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-24T10:00:00+08:00",
                        "level": "INFO",
                        "name": "system",
                        "message": "--- ЭТАП 1: Поиск новых терминов ---",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-24T10:00:01+08:00",
                        "level": "INFO",
                        "name": "system",
                        "message": "Запущен воркер [id: aaa111] для: chunk_0",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-24T10:00:02+08:00",
                        "level": "INFO",
                        "name": "system",
                        "message": "Воркер [id: aaa111] для chunk_0 успешно завершен",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-24T10:01:00+08:00",
                        "level": "INFO",
                        "name": "system",
                        "message": "--- ЭТАП 2: Перевод чанков ---",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-24T10:01:01+08:00",
                        "level": "ERROR",
                        "name": "system",
                        "message": "Воркер [id: bbb222] для chunk_1 завершился с ошибкой",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = load_run_records(run_dir)
    rows = build_worker_status_rows(records)

    assert len(rows) == 2
    assert rows[0]["stage"] == "discovery"
    assert rows[0]["status"] == "success"
    assert rows[1]["stage"] == "translation"
    assert rows[1]["status"] == "failed"


def test_translation_screen_marks_complete_progress_on_success(tmp_path, monkeypatch):
    series_root = _create_series(tmp_path)
    chapter_path = series_root / "volume-01" / "source" / "chapter-01.txt"
    chapter_path.write_text("text", encoding="utf-8")
    monkeypatch.setattr(TranslationScreen, "_start_translation", lambda self: None)
    app = BookTranslatorApp(series_root=series_root)

    async def scenario():
        async with app.run_test() as pilot:
            screen = TranslationScreen(series_root, chapter_path, {"debug": True})
            app.push_screen(screen)
            await pilot.pause()

            screen.post_message(ProgressStarted("translation", 10))
            screen.post_message(ProgressAdvanced("translation", 9, 10))
            screen.post_message(TranslationFinished("chapter-01", True))
            await pilot.pause()

            progress = screen.query_one("#chunk-progress", ProgressBar)
            status = str(screen.query_one("#run-status", Static).render())
            row = str(screen.query_one("#progress-row", Static).render())
            button = screen.query_one("#cancel-btn", Button)

            assert progress.progress == 10
            assert "10 / 10" in row
            assert "Время работы:" in row
            assert "успешно" in status
            assert str(button.label) == "← Назад"

    _run(scenario())


def test_translation_screen_surfaces_failure_without_fake_100_percent(tmp_path, monkeypatch):
    series_root = _create_series(tmp_path)
    chapter_path = series_root / "volume-01" / "source" / "chapter-01.txt"
    chapter_path.write_text("text", encoding="utf-8")
    monkeypatch.setattr(TranslationScreen, "_start_translation", lambda self: None)
    app = BookTranslatorApp(series_root=series_root)

    async def scenario():
        async with app.run_test() as pilot:
            screen = TranslationScreen(series_root, chapter_path, {"debug": True})
            app.push_screen(screen)
            await pilot.pause()

            screen.on_progress_started(ProgressStarted("translation", 12))
            screen.on_progress_advanced(ProgressAdvanced("translation", 11, 12))
            screen.on_tuilog_record(
                TUILogRecord(
                    "12:00:00 [system] КРИТИЧЕСКАЯ ОШИБКА: chunk_11 timeout",
                    "ERROR",
                    logger_name="system",
                )
            )
            screen.on_translation_finished(TranslationFinished("chapter-01", False))
            await pilot.pause()

            progress = screen.query_one("#chunk-progress", ProgressBar)
            status = str(screen.query_one("#run-status", Static).render())
            row = str(screen.query_one("#progress-row", Static).render())
            stage = str(screen.query_one("#stage-label", Static).render())

            assert progress.progress == 11
            assert "11 / 12" in row
            assert "timeout" in status
            assert "Ошибка" in stage

    _run(scenario())


def test_translation_screen_debug_table_tracks_worker_states(tmp_path, monkeypatch):
    series_root = _create_series(tmp_path)
    chapter_path = series_root / "volume-01" / "source" / "chapter-01.txt"
    chapter_path.write_text("text", encoding="utf-8")
    monkeypatch.setattr(TranslationScreen, "_start_translation", lambda self: None)
    app = BookTranslatorApp(series_root=series_root)

    async def scenario():
        async with app.run_test() as pilot:
            screen = TranslationScreen(series_root, chapter_path, {"debug": True})
            app.push_screen(screen)
            await pilot.pause()

            screen.on_tuilog_record(
                TUILogRecord(
                    "12:00:00 [system] --- ЭТАП 2: Перевод чанков ---",
                    "INFO",
                    logger_name="system",
                )
            )
            screen.on_tuilog_record(
                TUILogRecord(
                    "12:00:01 [system] Запущен воркер [id: aaa111] для: chunk_3",
                    "INFO",
                    logger_name="system",
                    worker_id="aaa111",
                )
            )
            screen.on_tuilog_record(
                TUILogRecord(
                    "12:00:02 [system] Воркер [id: aaa111] для chunk_3 успешно завершен",
                    "INFO",
                    logger_name="system",
                    worker_id="aaa111",
                )
            )
            await pilot.pause()

            table = screen.query_one("#worker-status-table", DataTable)
            worker_filter = screen.query_one("#worker-filter", Select)

            assert table.row_count == 1
            row = table.get_row_at(0)
            assert row[0] == "translation"
            assert row[1] == "aaa111"
            assert row[2] == "chunk_3"
            assert row[3] == "success"
            assert worker_filter.value == TranslationScreen.ALL_LOGS

    _run(scenario())


def test_log_screen_stage_filter_hides_other_stage_records(tmp_path):
    series_root = _create_series(tmp_path)
    volume_logs_dir = series_root / "volume-01" / ".state" / "logs"
    artifacts = create_run_artifacts(
        volume_logs_dir,
        volume_name="volume-01",
        chapter_name="chapter-01",
        debug_mode=True,
    )
    Path(artifacts["system_log_path"]).write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-24T10:00:00+08:00",
                        "level": "INFO",
                        "name": "system",
                        "message": "--- ЭТАП 1: Поиск новых терминов ---",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-24T10:00:01+08:00",
                        "level": "INFO",
                        "name": "system",
                        "message": "Воркер [id: aaa111] для chunk_0 успешно завершен",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-24T10:01:00+08:00",
                        "level": "INFO",
                        "name": "system",
                        "message": "--- ЭТАП 2: Перевод чанков ---",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-24T10:01:01+08:00",
                        "level": "ERROR",
                        "name": "system",
                        "message": "Воркер [id: bbb222] для chunk_1 завершился с ошибкой",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = BookTranslatorApp(series_root=series_root)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("l")
            await pilot.pause()

            screen = app.screen
            stage_filter = screen.query_one("#stage-filter", Select)
            stage_filter.value = "translation"
            await pilot.pause()

            table = screen.query_one("#worker-status-table", DataTable)
            assert table.row_count == 1
            row = table.get_row_at(0)
            assert row[0] == "translation"
            assert row[1] == "bbb222"
            assert row[3] == "failed"

    _run(scenario())


def test_live_log_record_flows_from_handler_through_app_to_translation_screen(tmp_path, monkeypatch):
    import logging

    series_root = _create_series(tmp_path)
    chapter_path = series_root / "volume-01" / "source" / "chapter-01.txt"
    chapter_path.write_text("text", encoding="utf-8")
    monkeypatch.setattr(TranslationScreen, "_start_translation", lambda self: None)
    app = BookTranslatorApp(series_root=series_root)

    async def scenario():
        async with app.run_test() as pilot:
            screen = TranslationScreen(series_root, chapter_path, {"debug": True})
            app.push_screen(screen)
            await pilot.pause()

            handler = TUILogHandler(app)
            record = logging.LogRecord("system", logging.INFO, __file__, 1, "hello-live-log", (), None)
            handler.emit(record)
            await pilot.pause()

            assert len(app._log_buffer) == 1
            assert len(screen._log_records) == 1
            assert "hello-live-log" in str(screen.query_one("#log-panel").lines[-1])

    _run(scenario())
