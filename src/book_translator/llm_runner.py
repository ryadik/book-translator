"""
LLM runner — thin wrapper around gemini-cli subprocess.

Provides run_gemini() which handles subprocess execution, retry logic,
rate limiting, and input/output logging.
"""
import subprocess
from pathlib import Path
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from book_translator.logger import system_logger, input_logger, output_logger
from book_translator.rate_limiter import RateLimiter
from book_translator.utils import find_tool_versions_dir

_SUBPROCESS_CWD = find_tool_versions_dir()


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
    command = ['gemini', '-m', model_name, '-p', prompt, '--output-format', output_format]
    input_logger.info(f"[{worker_id}] --- PROMPT FOR: {label} ---\n{prompt}\n")

    @retry(
        stop=stop_after_attempt(retry_attempts),
        wait=wait_exponential(multiplier=1, min=retry_wait_min, max=retry_wait_max),
        retry=retry_if_exception_type((subprocess.CalledProcessError, subprocess.TimeoutExpired)),
        reraise=True,
    )
    def _execute() -> str:
        system_logger.info(f"[LLMRunner] Запущен воркер [id: {worker_id}] для: {label}")
        try:
            with rate_limiter:
                result = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    timeout=timeout,
                    check=True,
                    cwd=_SUBPROCESS_CWD,
                )
            return result.stdout
        except subprocess.CalledProcessError as e:
            system_logger.error(f"[LLMRunner] Воркер [id: {worker_id}] для {label} завершился с ошибкой (код: {e.returncode}).")
            output_logger.error(f"[{worker_id}] --- FAILED OUTPUT FROM: {label} ---\n{e.stderr.strip()}\n")
            raise
        except subprocess.TimeoutExpired:
            system_logger.error(f"[LLMRunner] Воркер [id: {worker_id}] превысил лимит времени ({timeout}с). Принудительное завершение.")
            raise

    stdout = _execute()
    output_logger.info(f"[{worker_id}] --- SUCCESSFUL OUTPUT FROM: {label} ---\n{stdout}\n")
    return stdout
