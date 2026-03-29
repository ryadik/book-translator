"""Custom Textual Message classes for inter-widget communication."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from textual.message import Message


class UIMessage(Message):
    """A text message posted by TextualBridge (info / error / success)."""

    def __init__(self, text: str, level: str = "info") -> None:
        super().__init__()
        self.text = text
        self.level = level  # "info", "error", "success"


class ProgressStarted(Message):
    """Notifies that a progress bar should start."""

    def __init__(self, label: str, total: int) -> None:
        super().__init__()
        self.label = label
        self.total = total


class ProgressAdvanced(Message):
    """Notifies progress advancement."""

    def __init__(self, label: str, completed: int, total: int) -> None:
        super().__init__()
        self.label = label
        self.completed = completed
        self.total = total


class ProgressFinished(Message):
    """Notifies that a progress bar is done."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label


class ConfirmRequest(Message):
    """Requests a yes/no confirmation from the user."""

    def __init__(
        self,
        prompt: str,
        default: bool,
        callback: Callable[[bool], None],
    ) -> None:
        super().__init__()
        self.prompt = prompt
        self.default = default
        self.callback = callback


class WaitForUserRequest(Message):
    """Requests the user to signal readiness (blocks caller thread)."""

    import threading

    def __init__(self, message: str, event: "threading.Event") -> None:  # type: ignore[name-defined]
        super().__init__()
        self.message = message
        self.event = event


class TermApprovalRequest(Message):
    """Requests term-approval UI to appear."""

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
        self.terms = terms
        self.tsv_path = tsv_path
        self.glossary_db_path = glossary_db_path
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.callback = callback


class TranslationFinished(Message):
    """Notifies that a translation run completed (success or failure)."""

    def __init__(self, chapter_name: str, success: bool) -> None:
        super().__init__()
        self.chapter_name = chapter_name
        self.success = success


class DashboardRefreshRequested(Message):
    """Requests the dashboard to reload data from the database."""


class TUILogRecord(Message):
    """A log record forwarded from the logging system to the TUI."""

    def __init__(
        self,
        text: str,
        level: str,
        logger_name: str | None = None,
        worker_id: str | None = None,
    ) -> None:
        super().__init__()
        self.text = text
        self.level = level
        self.logger_name = logger_name or ""
        self.worker_id = worker_id
