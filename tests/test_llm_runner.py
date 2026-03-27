"""Tests for llm_runner — focuses on run_ollama(), run_qwen(), and run_llm() dispatcher.

run_gemini() is a thin subprocess wrapper tested implicitly via integration tests.
"""
import subprocess
from typing import Any
import pytest
from unittest.mock import patch, MagicMock

from book_translator.llm_runner import run_ollama, run_qwen, run_llm, check_ollama_connection, check_qwen_binary, check_gemini_binary
from book_translator.rate_limiter import RateLimiter


def _make_rate_limiter():
    return RateLimiter(max_rps=100.0)


class TestRunOllama:
    def _mock_post(self, response_text: str, status_code: int = 200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = {"response": response_text, "done": True}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_returns_response_text(self):
        mock_resp = self._mock_post("Translated text")
        with patch("book_translator.llm_runner._requests.post", return_value=mock_resp) as mock_post:
            result = run_ollama(
                prompt="Translate this",
                model_name="qwen3:8b",
                output_format="text",
                rate_limiter=_make_rate_limiter(),
                timeout=60,
                retry_attempts=1,
                retry_wait_min=1,
                retry_wait_max=2,
                worker_id="test",
                label="chunk_0",
            )
        assert result == "Translated text"
        mock_post.assert_called_once()

    def test_sends_json_format_when_output_format_is_json(self):
        mock_resp = self._mock_post('{"key": "value"}')
        with patch("book_translator.llm_runner._requests.post", return_value=mock_resp) as mock_post:
            run_ollama(
                prompt="Extract terms",
                model_name="qwen3:8b",
                output_format="json",
                rate_limiter=_make_rate_limiter(),
                timeout=60,
                retry_attempts=1,
                retry_wait_min=1,
                retry_wait_max=2,
                worker_id="test",
                label="chunk_0",
            )
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert payload["format"] == "json"

    def test_does_not_send_format_for_text_output(self):
        mock_resp = self._mock_post("plain text")
        with patch("book_translator.llm_runner._requests.post", return_value=mock_resp) as mock_post:
            run_ollama(
                prompt="Translate",
                model_name="qwen3:8b",
                output_format="text",
                rate_limiter=_make_rate_limiter(),
                timeout=60,
                retry_attempts=1,
                retry_wait_min=1,
                retry_wait_max=2,
                worker_id="test",
                label="chunk_0",
            )
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert "format" not in payload

    def test_uses_custom_ollama_url(self):
        mock_resp = self._mock_post("ok")
        with patch("book_translator.llm_runner._requests.post", return_value=mock_resp) as mock_post:
            run_ollama(
                prompt="test",
                model_name="qwen3:8b",
                output_format="text",
                rate_limiter=_make_rate_limiter(),
                timeout=60,
                retry_attempts=1,
                retry_wait_min=1,
                retry_wait_max=2,
                worker_id="test",
                label="chunk_0",
                ollama_url="http://192.168.1.100:11434",
            )
        url_called = mock_post.call_args[0][0]
        assert "192.168.1.100:11434" in url_called

    def test_passes_ollama_options(self):
        mock_resp = self._mock_post("ok")
        with patch("book_translator.llm_runner._requests.post", return_value=mock_resp) as mock_post:
            run_ollama(
                prompt="test",
                model_name="qwen3:8b",
                output_format="text",
                rate_limiter=_make_rate_limiter(),
                timeout=60,
                retry_attempts=1,
                retry_wait_min=1,
                retry_wait_max=2,
                worker_id="test",
                label="chunk_0",
                ollama_options={"temperature": 0.3, "num_ctx": 8192},
            )
        payload = mock_post.call_args[1]["json"]
        assert payload["options"]["temperature"] == 0.3
        assert payload["options"]["num_ctx"] == 8192

    def test_raises_on_connection_error_after_retries(self):
        import requests as req_lib
        with patch("book_translator.llm_runner._requests.post", side_effect=req_lib.exceptions.ConnectionError("refused")):
            with pytest.raises(req_lib.exceptions.ConnectionError):
                run_ollama(
                    prompt="test",
                    model_name="qwen3:8b",
                    output_format="text",
                    rate_limiter=_make_rate_limiter(),
                    timeout=5,
                    retry_attempts=2,
                    retry_wait_min=0,
                    retry_wait_max=0,
                    worker_id="test",
                    label="chunk_0",
                )


def _qwen_kwargs(**overrides) -> Any:
    base: dict[str, Any] = dict(
        prompt="test prompt",
        model_name="qwen-plus",
        output_format="text",
        rate_limiter=_make_rate_limiter(),
        timeout=60,
        retry_attempts=1,
        retry_wait_min=0,
        retry_wait_max=0,
        worker_id="t1",
        label="chunk_0",
    )
    base.update(overrides)
    return base


class TestRunQwen:
    def _mock_proc(self, stdout: str = "translated text", returncode: int = 0):
        proc = MagicMock()
        proc.communicate.return_value = (stdout, "")
        proc.returncode = returncode
        return proc

    def test_returns_stdout_on_success(self):
        proc = self._mock_proc("Переведённый текст")
        with patch("book_translator.llm_runner.subprocess.Popen", return_value=proc):
            result = run_qwen(**_qwen_kwargs())  # type: ignore[arg-type]
        assert result == "Переведённый текст"

    def test_command_uses_qwen_binary_and_approval_mode(self):
        proc = self._mock_proc()
        with patch("book_translator.llm_runner.subprocess.Popen", return_value=proc) as mock_popen:
            run_qwen(**_qwen_kwargs(model_name="qwen-max", output_format="json"))  # type: ignore[arg-type]
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "qwen"
        assert "-m" in cmd and "qwen-max" in cmd
        assert "--output-format" in cmd and "json" in cmd
        assert "--approval-mode" in cmd and "yolo" in cmd
        # Must NOT contain gemini's '-p' trick
        assert "-p" not in cmd

    def test_prompt_passed_via_stdin_not_args(self):
        """Prompt must go to stdin, not appear in the command array."""
        proc = self._mock_proc()
        with patch("book_translator.llm_runner.subprocess.Popen", return_value=proc) as mock_popen:
            run_qwen(**_qwen_kwargs(prompt="secret prompt"))  # type: ignore[arg-type]
        cmd = mock_popen.call_args[0][0]
        assert "secret prompt" not in " ".join(cmd)
        stdin_input = proc.communicate.call_args[1].get("input") or proc.communicate.call_args[0][0]
        assert "secret prompt" in stdin_input

    def test_raises_called_process_error_on_nonzero_exit(self):
        proc = self._mock_proc(returncode=1)
        with patch("book_translator.llm_runner.subprocess.Popen", return_value=proc):
            with pytest.raises(subprocess.CalledProcessError):
                run_qwen(**_qwen_kwargs())  # type: ignore[arg-type]

    def test_raises_timeout_expired_on_timeout(self):
        proc = MagicMock()
        proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="qwen", timeout=60)
        proc.returncode = None
        with patch("book_translator.llm_runner.subprocess.Popen", return_value=proc):
            with pytest.raises(subprocess.TimeoutExpired):
                run_qwen(**_qwen_kwargs())  # type: ignore[arg-type]

    def test_cancelled_raises_immediately_without_retry(self):
        import book_translator.llm_runner as runner_mod
        runner_mod._cancelled.set()
        try:
            proc = self._mock_proc()
            with patch("book_translator.llm_runner.subprocess.Popen", return_value=proc) as mock_popen:
                with pytest.raises(Exception):
                    run_qwen(**_qwen_kwargs(retry_attempts=3))  # type: ignore[arg-type]
            # Popen must never be called — cancellation fires before subprocess spawn
            mock_popen.assert_not_called()
        finally:
            runner_mod._cancelled.clear()

    def test_cancel_inside_rate_limiter_prevents_process_creation(self):
        """_cancelled set while holding rate_limiter must still prevent Popen (second guard)."""
        import book_translator.llm_runner as runner_mod

        original_enter = runner_mod.RateLimiter.__enter__

        def _cancel_on_enter(self_rl):
            runner_mod._cancelled.set()
            return original_enter(self_rl)

        proc = self._mock_proc()
        try:
            with patch("book_translator.llm_runner.subprocess.Popen", return_value=proc) as mock_popen, \
                 patch.object(runner_mod.RateLimiter, "__enter__", _cancel_on_enter):
                with pytest.raises(Exception):
                    run_qwen(**_qwen_kwargs(retry_attempts=1))  # type: ignore[arg-type]
            mock_popen.assert_not_called()
        finally:
            runner_mod._cancelled.clear()


class TestCheckQwenBinary:
    def test_passes_when_binary_found(self):
        with patch("book_translator.llm_runner.shutil.which", return_value="/usr/local/bin/qwen"):
            check_qwen_binary()  # should not raise

    def test_raises_runtime_error_when_binary_missing(self):
        with patch("book_translator.llm_runner.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="qwen"):
                check_qwen_binary()


class TestRunLlmDispatcher:
    def test_routes_qwen_to_run_qwen(self):
        rl = _make_rate_limiter()
        with patch("book_translator.llm_runner.run_qwen", return_value="qwen result") as mock_qwen:
            result = run_llm(
                backend="qwen", prompt="test", model_name="qwen-plus",
                output_format="text", rate_limiter=rl, timeout=60,
                retry_attempts=1, retry_wait_min=1, retry_wait_max=2,
                worker_id="test", label="chunk_0",
            )
        assert result == "qwen result"
        mock_qwen.assert_called_once()

    def test_routes_ollama_to_run_ollama(self):
        with patch("book_translator.llm_runner.run_ollama", return_value="ollama result") as mock_ollama:
            result = run_llm(
                backend="ollama",
                prompt="test",
                model_name="qwen3:8b",
                output_format="text",
                rate_limiter=_make_rate_limiter(),
                timeout=60,
                retry_attempts=1,
                retry_wait_min=1,
                retry_wait_max=2,
                worker_id="test",
                label="chunk_0",
            )
        assert result == "ollama result"
        mock_ollama.assert_called_once()

    def test_routes_gemini_to_run_gemini(self):
        with patch("book_translator.llm_runner.run_gemini", return_value="gemini result") as mock_gemini:
            result = run_llm(
                backend="gemini",
                prompt="test",
                model_name="gemini-2.5-pro",
                output_format="text",
                rate_limiter=_make_rate_limiter(),
                timeout=60,
                retry_attempts=1,
                retry_wait_min=1,
                retry_wait_max=2,
                worker_id="test",
                label="chunk_0",
            )
        assert result == "gemini result"
        mock_gemini.assert_called_once()


class TestRunOllamaThinkParam:
    def _mock_post(self, response_text: str = "ok"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": response_text, "done": True}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def _call_with_options(self, opts: dict):
        mock_resp = self._mock_post()
        with patch("book_translator.llm_runner._requests.post", return_value=mock_resp) as mock_post:
            run_ollama(
                prompt="test", model_name="qwen3:8b", output_format="text",
                rate_limiter=_make_rate_limiter(), timeout=60,
                retry_attempts=1, retry_wait_min=0, retry_wait_max=0,
                worker_id="t", label="c0", ollama_options=opts,
            )
        return mock_post.call_args[1]["json"]

    def test_think_false_sent_as_top_level_param(self):
        payload = self._call_with_options({"think": False, "temperature": 0.3})
        assert payload["think"] is False
        assert "think" not in payload["options"]

    def test_think_true_sent_as_top_level_param(self):
        payload = self._call_with_options({"think": True})
        assert payload["think"] is True

    def test_no_think_key_when_not_in_options(self):
        payload = self._call_with_options({"temperature": 0.3})
        assert "think" not in payload

    def test_stage_temperature_stripped_from_options(self):
        """stage_temperature is an internal key, must never reach Ollama."""
        payload = self._call_with_options({
            "temperature": 0.3,
            "stage_temperature": {"discovery": 0.1},
        })
        assert "stage_temperature" not in payload["options"]


class TestCheckOllamaConnection:
    def test_raises_runtime_error_when_server_unreachable(self):
        import requests as req_lib
        with patch("book_translator.llm_runner._requests.get", side_effect=req_lib.exceptions.ConnectionError()):
            with pytest.raises(RuntimeError, match="Ollama не запущен"):
                check_ollama_connection("http://localhost:11434", [])

    def test_raises_when_model_missing(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "llama3:8b"}]}
        with patch("book_translator.llm_runner._requests.get", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="qwen3:14b"):
                check_ollama_connection("http://localhost:11434", ["qwen3:14b"])

    def test_passes_when_all_models_present(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "qwen3:8b"}, {"name": "qwen3:14b"}]}
        with patch("book_translator.llm_runner._requests.get", return_value=mock_resp):
            check_ollama_connection("http://localhost:11434", ["qwen3:8b", "qwen3:14b"])

    def test_passes_with_empty_required_models(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"models": []}
        with patch("book_translator.llm_runner._requests.get", return_value=mock_resp):
            check_ollama_connection("http://localhost:11434", [])

    def test_passes_when_model_name_lacks_tag_and_server_returns_latest(self):
        """Config says 'qwen3', Ollama stores it as 'qwen3:latest' — must not raise."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "qwen3:latest"}]}
        with patch("book_translator.llm_runner._requests.get", return_value=mock_resp):
            check_ollama_connection("http://localhost:11434", ["qwen3"])  # no tag in config

    def test_raises_when_model_tag_wrong(self):
        """Config says 'qwen3:9b' but only 'qwen3:8b' is installed."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "qwen3:8b"}]}
        with patch("book_translator.llm_runner._requests.get", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="qwen3:9b"):
                check_ollama_connection("http://localhost:11434", ["qwen3:9b"])


class TestCheckGeminiBinary:
    def test_passes_when_binary_found(self):
        with patch("book_translator.llm_runner.shutil.which", return_value="/usr/local/bin/gemini"):
            check_gemini_binary()  # should not raise

    def test_raises_runtime_error_when_binary_missing(self):
        with patch("book_translator.llm_runner.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="gemini"):
                check_gemini_binary()
