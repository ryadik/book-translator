import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from book_translator.log_viewer import (
    create_run_artifacts,
    extract_worker_id_from_message,
)

_TUI_PREVIEW_LIMIT = 240


def _extract_worker_id(record: logging.LogRecord) -> str | None:
    worker_id = getattr(record, "worker_id", None)
    if isinstance(worker_id, str) and worker_id:
        return worker_id
    return extract_worker_id_from_message(record.getMessage())


def _summarize_multiline_log(logger_name: str, message: str, worker_id: str | None) -> str:
    if logger_name not in {"worker_input", "worker_output"}:
        return message

    lines = message.strip().splitlines()
    header = lines[0] if lines else message.strip()
    body = "\n".join(lines[1:]).strip()
    if not body:
        return message

    preview = body[:_TUI_PREVIEW_LIMIT].replace("\n", " ")
    if len(body) > _TUI_PREVIEW_LIMIT:
        preview += "…"
    worker_label = f"[{worker_id}] " if worker_id else ""
    size_part = f"{len(body)} chars"
    return f"{worker_label}{header} | {size_part} | {preview}"


class TUILogHandler(logging.Handler):
    """Forward log records to the Textual app."""

    def __init__(self, app) -> None:
        super().__init__()
        self._app = app

    def emit(self, record: logging.LogRecord) -> None:
        try:
            from book_translator.textual_app.messages import TUILogRecord

            worker_id = _extract_worker_id(record)
            raw_message = record.getMessage()
            display_message = _summarize_multiline_log(record.name, raw_message, worker_id)
            timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            text = f"{timestamp} [{record.name}] {display_message}"
            self._app.post_message(
                TUILogRecord(
                    text=text,
                    level=record.levelname,
                    logger_name=record.name,
                    worker_id=worker_id,
                )
            )
        except Exception:
            self.handleError(record)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for non-Textual CLI logging."""

    def format(self, record):
        message = record.getMessage()
        if record.levelno >= logging.ERROR:
            return f"[{record.levelname}] {message}"
        if record.levelno >= logging.WARNING:
            return f"[WARNING] {message}"
        return message


system_logger = logging.getLogger("system")
input_logger = logging.getLogger("worker_input")
output_logger = logging.getLogger("worker_output")

default_formatter = JsonFormatter()
default_handler = logging.StreamHandler(sys.stdout)
default_handler.setFormatter(default_formatter)
system_logger.addHandler(default_handler)
system_logger.setLevel(logging.INFO)
system_logger.propagate = False

for logger_instance in [input_logger, output_logger]:
    logger_instance.addHandler(logging.NullHandler())
    logger_instance.propagate = False


def setup_loggers(
    log_dir: str,
    debug_mode: bool,
    console_handler: logging.Handler | None = None,
    *,
    volume_name: str = "unknown-volume",
    chapter_name: str = "unknown-chapter",
) -> dict[str, str]:
    for logger_instance in [system_logger, input_logger, output_logger]:
        if logger_instance.hasHandlers():
            logger_instance.handlers.clear()
        # Temporary NullHandler prevents "No handlers could be found" warnings
        # during the window between clearing old handlers and adding new ones.
        logger_instance.addHandler(logging.NullHandler())

    system_logger.setLevel(logging.DEBUG)
    input_logger.setLevel(logging.DEBUG)
    output_logger.setLevel(logging.DEBUG)

    if console_handler is None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ConsoleFormatter())
    console_handler.setLevel(logging.INFO)
    system_logger.addHandler(console_handler)
    if debug_mode:
        input_logger.addHandler(console_handler)
        output_logger.addHandler(console_handler)

    log_artifacts = create_run_artifacts(
        Path(log_dir),
        volume_name=volume_name,
        chapter_name=chapter_name,
        debug_mode=debug_mode,
    )
    json_formatter = JsonFormatter()

    system_file_handler = logging.FileHandler(log_artifacts["system_log_path"], mode="w", encoding="utf-8")
    system_file_handler.setLevel(logging.DEBUG)
    system_file_handler.setFormatter(json_formatter)
    system_logger.addHandler(system_file_handler)

    if not debug_mode:
        input_logger.addHandler(logging.NullHandler())
        output_logger.addHandler(logging.NullHandler())
        return log_artifacts

    input_file_handler = logging.FileHandler(log_artifacts["input_log_path"], mode="w", encoding="utf-8")
    input_file_handler.setLevel(logging.DEBUG)
    input_file_handler.setFormatter(json_formatter)
    input_logger.addHandler(input_file_handler)

    output_file_handler = logging.FileHandler(log_artifacts["output_log_path"], mode="w", encoding="utf-8")
    output_file_handler.setLevel(logging.DEBUG)
    output_file_handler.setFormatter(json_formatter)
    output_logger.addHandler(output_file_handler)

    system_logger.debug("Логгеры успешно настроены в debug-режиме.")
    return log_artifacts
