"""TextualBridge — потокобезопасная интеграция оркестратора с Textual TUI.

Все методы потокобезопасны: они вызываются из worker-потока оркестратора.
`post_message()` в Textual уже является thread-safe — при вызове из стороннего
потока оно использует `call_soon_threadsafe` внутри. Поэтому мы вызываем его
напрямую, без лишней обёртки call_from_thread.

Блокирующие операции (confirm, wait_for_user, approve_terms) используют
threading.Event для синхронизации между worker-потоком и TUI.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from book_translator.textual_app.app import BookTranslatorApp

from book_translator import llm_runner as _llm_runner
from book_translator.textual_app.messages import (
    ConfirmRequest,
    ProgressAdvanced,
    ProgressFinished,
    ProgressStarted,
    TermApprovalRequest,
    UIMessage,
    WaitForUserRequest,
)


class CancellationError(Exception):
    """Raised when the user cancels a running translation."""


class TextualProgressHandle:
    """Прогресс-хэндл, постящий события в экран перевода через post_message."""

    def __init__(
        self,
        screen,
        label: str,
        total: int,
        cancelled: threading.Event,
    ) -> None:
        self._screen = screen
        self._label = label
        self._total = total
        self._completed = 0
        self._cancelled = cancelled

    def advance(self, amount: int = 1) -> None:
        if self._cancelled.is_set():
            raise CancellationError("Translation cancelled")
        self._completed += amount
        # post_message is thread-safe in Textual (uses call_soon_threadsafe internally)
        self._screen.post_message(
            ProgressAdvanced(self._label, self._completed, self._total)
        )


class TextualBridge:
    """Потокобезопасная Textual-интеграция для `run_translation_process()`."""

    def __init__(self, screen) -> None:
        self._screen = screen
        self._cancelled = threading.Event()
        self._running = True

    @property
    def is_running(self) -> bool:
        return self._running and not self._cancelled.is_set()

    def cancel(self) -> None:
        """Сигнализирует об отмене. Убивает активные LLM-вызовы и разблокирует ожидающие операции."""
        self._cancelled.set()
        self._running = False
        _llm_runner.cancel_all()

    def mark_done(self) -> None:
        """Отмечает завершение перевода (без отмены)."""
        self._running = False

    def _check_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise CancellationError("Translation cancelled by user")

    # ── Текстовые сообщения ──────────────────────────────────────────────────

    def info(self, message: str) -> None:
        self._check_cancelled()
        self._screen.post_message(UIMessage(message, level="info"))

    def error(self, message: str) -> None:
        # Ошибки постим даже при отмене
        self._screen.post_message(UIMessage(message, level="error"))

    def success(self, message: str) -> None:
        self._screen.post_message(UIMessage(message, level="success"))

    # ── Интерактивные промпты ────────────────────────────────────────────────

    def confirm(self, prompt: str, default: bool = False) -> bool:
        """Запрашивает подтверждение через TUI-диалог. Блокирует поток."""
        self._check_cancelled()

        result: list[bool] = []
        response_event = threading.Event()

        def _callback(value: bool) -> None:
            result.append(value)
            response_event.set()

        # post_message на app (там зарегистрирован on_confirm_request)
        self._screen.app.post_message(ConfirmRequest(prompt, default, _callback))

        # Ждём ответа с таймаутом, периодически проверяя отмену
        while not response_event.wait(timeout=1.0):
            if self._cancelled.is_set():
                return default

        self._check_cancelled()
        return result[0] if result else default

    def wait_for_user(self, message: str) -> None:
        """Ждёт пока пользователь нажмёт «Продолжить» в диалоге."""
        self._check_cancelled()

        ready_event = threading.Event()
        self._screen.app.post_message(WaitForUserRequest(message, ready_event))

        # Ждём с таймаутом, периодически проверяя отмену
        while not ready_event.wait(timeout=1.0):
            if self._cancelled.is_set():
                return

    # ── Прогресс ─────────────────────────────────────────────────────────────

    @contextmanager
    def progress(self, label: str, total: int):
        self._check_cancelled()
        handle = TextualProgressHandle(self._screen, label, total, self._cancelled)

        self._screen.post_message(ProgressStarted(label, total))
        try:
            yield handle
        finally:
            self._screen.post_message(ProgressFinished(label))
            # Не сбрасываем _running — оркестратор может запустить следующий этап.
            # _running = False устанавливается только через cancel() или mark_done().

    # ── Подтверждение терминов ───────────────────────────────────────────────

    def approve_terms(
        self,
        terms: list[dict],
        tsv_path: Path,
        glossary_db_path: Path,
        source_lang: str,
        target_lang: str,
    ) -> int:
        """Показывает TermApprovalScreen и ждёт подтверждения."""
        self._check_cancelled()

        result: list[int] = []
        done_event = threading.Event()

        def _callback(count: int) -> None:
            result.append(count)
            done_event.set()

        self._screen.app.post_message(
            TermApprovalRequest(
                terms=terms,
                tsv_path=tsv_path,
                glossary_db_path=glossary_db_path,
                source_lang=source_lang,
                target_lang=target_lang,
                callback=_callback,
            ),
        )

        # Ждём с таймаутом, периодически проверяя отмену
        while not done_event.wait(timeout=1.0):
            if self._cancelled.is_set():
                return 0

        return result[0] if result else 0
