"""
LLM runner — thin wrappers around LLM backends.

Provides:
  run_gemini() — subprocess call to gemini-cli (cloud backend)
  run_qwen()   — subprocess call to qwen-code CLI (cloud backend)
  run_ollama() — HTTP call to local Ollama server (local backend)
  run_llm()    — dispatcher that routes to the correct backend
  check_qwen_binary()      — pre-flight check for qwen-code availability
  check_ollama_connection() — pre-flight check for Ollama availability
  cancel_all() — abort all active LLM calls (called from UI cancel handler)
  reset_cancellation() — clear cancellation state before a new translation run
"""
import json as _json
import re as _re
import shutil
import subprocess
import threading as _threading
from functools import lru_cache
from pathlib import Path

import requests as _requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from book_translator.logger import system_logger, input_logger, output_logger
from book_translator.rate_limiter import RateLimiter
from book_translator.utils import find_tool_versions_dir


class _LLMCancelledError(Exception):
    """Raised internally to abort a cancelled LLM call without retrying."""


# ── Module-level cancellation state ──────────────────────────────────────────
# Shared across all threads; cancel_all() sets _cancelled and kills active calls.
_cancelled = _threading.Event()
_registry_lock = _threading.Lock()
_active_processes: list[subprocess.Popen] = []   # active gemini-cli / qwen-code subprocesses


def cancel_all() -> None:
    """Abort all active LLM calls. Thread-safe; called from the UI cancel handler.

    Gemini subprocesses are killed immediately (SIGKILL).
    Ollama HTTP requests: cancel_all() sets _cancelled so any retry loop stops
    immediately before starting the next attempt. In-flight HTTP requests are not
    interrupted mid-flight (standard requests library limitation), but no new
    requests will start after cancellation.
    """
    _cancelled.set()
    with _registry_lock:
        for proc in list(_active_processes):
            try:
                proc.kill()
            except Exception:
                pass
        _active_processes.clear()


def reset_cancellation() -> None:
    """Clear cancellation state before starting a new translation run."""
    _cancelled.clear()


@lru_cache(maxsize=1)
def _get_subprocess_cwd() -> Path | None:
    return find_tool_versions_dir()


def run_gemini(
    prompt: str,
    model_name: str,
    output_format: str,
    rate_limiter: RateLimiter,
    timeout: int,
    retry_attempts: int,
    retry_wait_min: int,
    retry_wait_max: int,
    worker_id: str,
    label: str,
) -> str:
    """Run gemini-cli with the given prompt and return stdout.

    Args:
        prompt: The full prompt string to send.
        model_name: Gemini model identifier.
        output_format: 'text' or 'json'.
        rate_limiter: Shared rate limiter instance.
        timeout: Subprocess timeout in seconds.
        retry_attempts: Max retry attempts on CalledProcessError/TimeoutExpired.
        retry_wait_min: Min wait between retries (seconds).
        retry_wait_max: Max wait between retries (seconds).
        worker_id: Short ID for logging.
        label: Human-readable label for log messages (e.g. 'chunk_3').

    Returns:
        stdout string from gemini-cli.

    Raises:
        subprocess.CalledProcessError: After exhausting retries.
        subprocess.TimeoutExpired: After exhausting retries.
    """
    # Pass prompt via stdin to avoid ARG_MAX limits and prevent prompt leakage in `ps aux`.
    # Use `-p " "` (single space) to trigger non-interactive (headless) mode;
    # gemini-cli concatenates stdin + -p value, so the space is harmless.
    command = ['gemini', '-m', model_name, '-p', ' ', '--output-format', output_format]
    input_logger.info(f"[{worker_id}] --- PROMPT FOR: {label} ---\n{prompt}\n")

    @retry(
        stop=stop_after_attempt(retry_attempts),
        wait=wait_exponential(multiplier=1, min=retry_wait_min, max=retry_wait_max),
        retry=retry_if_exception_type((subprocess.CalledProcessError, subprocess.TimeoutExpired)),
        reraise=True,
    )
    def _execute() -> str:
        # Check cancellation before starting — _LLMCancelledError is NOT in the
        # retry list so tenacity lets it propagate immediately.
        if _cancelled.is_set():
            raise _LLMCancelledError("LLM call cancelled")
        system_logger.info(f"[LLMRunner] Запущен воркер [id: {worker_id}] для: {label}")
        try:
            with rate_limiter:
                # Повторная проверка отмены после ожидания ограничителя скорости,
                # чтобы устранить гонку между созданием процесса и его регистрацией.
                if _cancelled.is_set():
                    raise _LLMCancelledError("LLM call cancelled")
                with _registry_lock:
                    if _cancelled.is_set():
                        raise _LLMCancelledError("LLM call cancelled")
                    proc = subprocess.Popen(
                        command,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding='utf-8',
                        cwd=_get_subprocess_cwd(),
                    )
                    _active_processes.append(proc)
            try:
                try:
                    stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                    system_logger.error(f"[LLMRunner] Воркер [id: {worker_id}] превысил лимит времени ({timeout}с). Принудительное завершение.")
                    raise
                if proc.returncode != 0:
                    exc = subprocess.CalledProcessError(proc.returncode, command, stdout, stderr)
                    system_logger.error(f"[LLMRunner] Воркер [id: {worker_id}] для {label} завершился с ошибкой (код: {proc.returncode}).")
                    output_logger.error(f"[{worker_id}] --- FAILED OUTPUT FROM: {label} ---\n{stderr.strip()}\n")
                    raise exc
                return stdout
            finally:
                with _registry_lock:
                    try:
                        _active_processes.remove(proc)
                    except ValueError:
                        pass
        except subprocess.CalledProcessError:
            raise
        except subprocess.TimeoutExpired:
            raise

    stdout = _execute()
    output_logger.info(f"[{worker_id}] --- SUCCESSFUL OUTPUT FROM: {label} ---\n{stdout}\n")
    return stdout


def _extract_qwen_response(raw: str) -> tuple[str, bool]:
    """Extract the LLM response text from qwen-code's --output-format json output.

    qwen-code returns a JSON array of message objects. The actual LLM response
    is in the final {"type": "result", "result": "..."} entry.

    Returns:
        (response_text, is_error) — response_text is the LLM's answer;
        is_error is True when qwen-code signals an error condition.
    """
    try:
        messages = _json.loads(raw)
        if isinstance(messages, list):
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("type") == "result":
                    return str(msg.get("result", "")), bool(msg.get("is_error", False))
    except (_json.JSONDecodeError, TypeError, ValueError):
        pass
    # Fallback: raw output could not be parsed — return as-is
    return raw, False


def run_qwen(
    prompt: str,
    model_name: str,
    output_format: str,
    rate_limiter: RateLimiter,
    timeout: int,
    retry_attempts: int,
    retry_wait_min: int,
    retry_wait_max: int,
    worker_id: str,
    label: str,
) -> str:
    """Run qwen-code CLI with the given prompt and return the LLM response text.

    qwen-code uses the same stdin + -p ' ' headless pattern as gemini-cli.
    Key difference: --output-format json returns a JSON array of message objects,
    not a {"response": "..."} wrapper. We extract the result from the final
    {"type": "result", "result": "..."} entry.

    Args:
        prompt: The full prompt string to send via stdin.
        model_name: Qwen model identifier (e.g. 'qwen-plus').
        output_format: 'text' or 'json' (used by caller to decide how to parse;
            the CLI always uses --output-format json for structured extraction).
        rate_limiter: Shared rate limiter instance.
        timeout: Subprocess timeout in seconds.
        retry_attempts: Max retry attempts on CalledProcessError/TimeoutExpired.
        retry_wait_min: Min wait between retries (seconds).
        retry_wait_max: Max wait between retries (seconds).
        worker_id: Short ID for logging.
        label: Human-readable label for log messages (e.g. 'chunk_3').

    Returns:
        LLM response text extracted from qwen-code output.

    Raises:
        subprocess.CalledProcessError: After exhausting retries or on qwen error.
        subprocess.TimeoutExpired: After exhausting retries.
    """
    # -p ' ' triggers headless (non-interactive) mode and makes qwen read stdin,
    # identical to how gemini-cli works. --output-format json gives a parseable
    # JSON array from which we extract the actual LLM response text.
    command = ['qwen', '-m', model_name, '-p', ' ', '--output-format', 'json', '--approval-mode', 'yolo']
    input_logger.info(f"[{worker_id}] --- PROMPT FOR: {label} ---\n{prompt}\n")

    @retry(
        stop=stop_after_attempt(retry_attempts),
        wait=wait_exponential(multiplier=1, min=retry_wait_min, max=retry_wait_max),
        retry=retry_if_exception_type((subprocess.CalledProcessError, subprocess.TimeoutExpired)),
        reraise=True,
    )
    def _execute() -> str:
        if _cancelled.is_set():
            raise _LLMCancelledError("LLM call cancelled")
        system_logger.info(f"[LLMRunner] Запущен воркер [id: {worker_id}] для: {label}")
        try:
            with rate_limiter:
                if _cancelled.is_set():
                    raise _LLMCancelledError("LLM call cancelled")
                with _registry_lock:
                    if _cancelled.is_set():
                        raise _LLMCancelledError("LLM call cancelled")
                    proc = subprocess.Popen(
                        command,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding='utf-8',
                        cwd=_get_subprocess_cwd(),
                    )
                    _active_processes.append(proc)
            try:
                try:
                    stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                    system_logger.error(f"[LLMRunner] Воркер [id: {worker_id}] превысил лимит времени ({timeout}с). Принудительное завершение.")
                    raise
                if proc.returncode != 0:
                    exc = subprocess.CalledProcessError(proc.returncode, command, stdout, stderr)
                    system_logger.error(f"[LLMRunner] Воркер [id: {worker_id}] для {label} завершился с ошибкой (код: {proc.returncode}).")
                    output_logger.error(f"[{worker_id}] --- FAILED OUTPUT FROM: {label} ---\n{stderr.strip()}\n")
                    raise exc
                return stdout
            finally:
                with _registry_lock:
                    try:
                        _active_processes.remove(proc)
                    except ValueError:
                        pass
        except subprocess.CalledProcessError:
            raise
        except subprocess.TimeoutExpired:
            raise

    raw_stdout = _execute()
    response_text, is_error = _extract_qwen_response(raw_stdout)
    if is_error:
        system_logger.error(f"[LLMRunner] Qwen вернул ошибку для {label}: {response_text[:300]}")
        raise subprocess.CalledProcessError(1, command, raw_stdout, response_text)
    # Strip any <think>...</think> reasoning tokens that some Qwen models emit.
    response_text = _re.sub(r'<think>.*?</think>', '', response_text, flags=_re.DOTALL).strip()
    output_logger.info(f"[{worker_id}] --- SUCCESSFUL OUTPUT FROM: {label} ---\n{response_text}\n")
    return response_text


def run_ollama(
    prompt: str,
    model_name: str,
    output_format: str,
    rate_limiter: RateLimiter,
    timeout: int,
    retry_attempts: int,
    retry_wait_min: int,
    retry_wait_max: int,
    worker_id: str,
    label: str,
    ollama_url: str = "http://localhost:11434",
    ollama_options: dict | None = None,
) -> str:
    """Run a prompt against a local Ollama server and return the response text.

    Uses the /api/generate endpoint with stream=False.
    When output_format='json', passes format='json' to Ollama for grammar-constrained output.

    Args:
        prompt: The full prompt string to send.
        model_name: Ollama model name (e.g. 'qwen3:14b').
        output_format: 'text' or 'json'.
        rate_limiter: Shared rate limiter instance.
        timeout: HTTP request timeout in seconds.
        retry_attempts: Max retry attempts on transient errors.
        retry_wait_min: Min wait between retries (seconds).
        retry_wait_max: Max wait between retries (seconds).
        worker_id: Short ID for logging.
        label: Human-readable label for log messages (e.g. 'chunk_3').
        ollama_url: Base URL of the Ollama server.
        ollama_options: Optional generation parameters (temperature, num_ctx, etc.).

    Returns:
        Response text from Ollama.

    Raises:
        requests.exceptions.ConnectionError: If Ollama is not reachable (after retries).
        requests.exceptions.HTTPError: On non-retryable HTTP errors.
        requests.exceptions.Timeout: After exhausting retries.
    """
    if _cancelled.is_set():
        raise _LLMCancelledError("LLM call cancelled")

    input_logger.info(f"[{worker_id}] --- PROMPT FOR: {label} ---\n{prompt}\n")

    endpoint = f"{ollama_url.rstrip('/')}/api/generate"

    # Separate top-level Ollama params from model generation options.
    # 'think' is a top-level Ollama param (not inside 'options') controlling
    # Qwen3 chain-of-thought mode. 'stage_temperature' is our internal key
    # already resolved before this call — strip it defensively.
    raw_options = dict(ollama_options or {})
    raw_options.pop('stage_temperature', None)
    think_value = raw_options.pop('think', None)

    payload: dict = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": raw_options,
    }
    if think_value is not None:
        payload["think"] = bool(think_value)
    if output_format == "json":
        payload["format"] = "json"

    @retry(
        stop=stop_after_attempt(retry_attempts),
        wait=wait_exponential(multiplier=1, min=retry_wait_min, max=retry_wait_max),
        retry=retry_if_exception_type((
            _requests.exceptions.Timeout,
            _requests.exceptions.ConnectionError,
        )),
        reraise=True,
    )
    def _execute() -> str:
        # Check cancellation before each attempt — _LLMCancelledError is NOT in
        # the retry list so tenacity lets it propagate immediately without retrying.
        if _cancelled.is_set():
            raise _LLMCancelledError("LLM call cancelled")
        system_logger.info(f"[LLMRunner/Ollama] Запущен воркер [id: {worker_id}] для: {label} (модель: {model_name})")
        try:
            with rate_limiter:
                response = _requests.post(endpoint, json=payload, timeout=timeout)
            response.raise_for_status()
            text = response.json()["response"]
            # Strip <think>...</think> blocks — Qwen3 may emit these even when
            # think=false is sent. Defense-in-depth: remove them from output.
            text = _re.sub(r'<think>.*?</think>', '', text, flags=_re.DOTALL).strip()
            return text
        except _requests.exceptions.Timeout:
            system_logger.error(f"[LLMRunner/Ollama] Воркер [id: {worker_id}] превысил лимит времени ({timeout}с).")
            raise
        except _requests.exceptions.ConnectionError as e:
            system_logger.error(f"[LLMRunner/Ollama] Воркер [id: {worker_id}] не может подключиться к Ollama: {e}")
            raise
        except _requests.exceptions.HTTPError as e:
            system_logger.error(f"[LLMRunner/Ollama] Воркер [id: {worker_id}] для {label} HTTP-ошибка: {e}")
            output_logger.error(f"[{worker_id}] --- FAILED OUTPUT FROM: {label} ---\n{e.response.text[:500]}\n")
            raise

    stdout = _execute()
    output_logger.info(f"[{worker_id}] --- SUCCESSFUL OUTPUT FROM: {label} ---\n{stdout}\n")
    return stdout


def run_llm(
    backend: str,
    prompt: str,
    model_name: str,
    output_format: str,
    rate_limiter: RateLimiter,
    timeout: int,
    retry_attempts: int,
    retry_wait_min: int,
    retry_wait_max: int,
    worker_id: str,
    label: str,
    ollama_url: str = "http://localhost:11434",
    ollama_options: dict | None = None,
) -> str:
    """Dispatch an LLM call to the configured backend.

    Args:
        backend: 'gemini', 'qwen', or 'ollama'.
        All other args passed through to the backend-specific runner.

    Returns:
        Response text from the selected backend.
    """
    if backend == "ollama":
        return run_ollama(
            prompt=prompt,
            model_name=model_name,
            output_format=output_format,
            rate_limiter=rate_limiter,
            timeout=timeout,
            retry_attempts=retry_attempts,
            retry_wait_min=retry_wait_min,
            retry_wait_max=retry_wait_max,
            worker_id=worker_id,
            label=label,
            ollama_url=ollama_url,
            ollama_options=ollama_options,
        )
    if backend == "qwen":
        return run_qwen(
            prompt=prompt,
            model_name=model_name,
            output_format=output_format,
            rate_limiter=rate_limiter,
            timeout=timeout,
            retry_attempts=retry_attempts,
            retry_wait_min=retry_wait_min,
            retry_wait_max=retry_wait_max,
            worker_id=worker_id,
            label=label,
        )
    return run_gemini(
        prompt=prompt,
        model_name=model_name,
        output_format=output_format,
        rate_limiter=rate_limiter,
        timeout=timeout,
        retry_attempts=retry_attempts,
        retry_wait_min=retry_wait_min,
        retry_wait_max=retry_wait_max,
        worker_id=worker_id,
        label=label,
    )


def check_gemini_binary() -> None:
    """Verify that gemini-cli is available in PATH.

    Raises:
        RuntimeError: If 'gemini' binary is not found.
    """
    if shutil.which('gemini') is None:
        raise RuntimeError(
            "Команда 'gemini' не найдена в PATH. "
            "Установите gemini-cli: npm install -g @google/gemini-cli"
        )


def check_qwen_binary() -> None:
    """Verify that the qwen-code CLI is available in PATH.

    Raises:
        RuntimeError: If 'qwen' binary is not found.
    """
    if shutil.which('qwen') is None:
        raise RuntimeError(
            "Команда 'qwen' не найдена в PATH. "
            "Установите qwen-code: npm install -g qwen-code"
        )


def _normalize_ollama_model(name: str) -> str:
    """Normalize an Ollama model name: append ':latest' if no tag is specified."""
    return name if ':' in name else f"{name}:latest"


def check_ollama_connection(ollama_url: str, required_models: list[str]) -> None:
    """Verify that Ollama is running and the required models are available.

    Args:
        ollama_url: Base URL of the Ollama server.
        required_models: List of model names that must be present (e.g. ['qwen3:8b']).

    Raises:
        RuntimeError: If Ollama is unreachable or required models are missing.
    """
    tags_url = f"{ollama_url.rstrip('/')}/api/tags"
    try:
        response = _requests.get(tags_url, timeout=5)
        response.raise_for_status()
    except _requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Ollama не запущен (не удалось подключиться к {ollama_url}). "
            "Запустите сервер командой: ollama serve"
        )
    except Exception as e:
        raise RuntimeError(f"Ошибка при подключении к Ollama ({ollama_url}): {e}")

    # Normalize names so that 'qwen3' matches 'qwen3:latest' returned by the server
    available_normalized = {
        _normalize_ollama_model(m["name"])
        for m in response.json().get("models", [])
    }
    missing = [m for m in required_models if _normalize_ollama_model(m) not in available_normalized]
    if missing:
        pull_cmds = "\n".join(f"  ollama pull {m}" for m in missing)
        raise RuntimeError(
            f"Следующие модели не найдены в Ollama:\n{pull_cmds}\n"
            "Загрузите их перед запуском перевода."
        )
