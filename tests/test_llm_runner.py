"""Tests for llm_runner — focuses on run_ollama() and run_llm() dispatcher.

run_gemini() is a thin subprocess wrapper tested implicitly via integration tests.
"""
import pytest
from unittest.mock import patch, MagicMock

from book_translator.llm_runner import run_ollama, run_llm, check_ollama_connection
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


class TestRunLlmDispatcher:
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
