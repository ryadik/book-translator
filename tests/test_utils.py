"""Tests for utils.parse_llm_json and strip_code_fence."""
import pytest
from book_translator.utils import parse_llm_json, strip_code_fence


class TestStripCodeFence:
    def test_strips_json_fence(self):
        text = "```json\n{\"key\": 1}\n```"
        assert strip_code_fence(text) == '{"key": 1}'

    def test_strips_plain_fence(self):
        text = "```\n{\"key\": 1}\n```"
        assert strip_code_fence(text) == '{"key": 1}'

    def test_no_fence_passthrough(self):
        text = '{"key": 1}'
        assert strip_code_fence(text) == '{"key": 1}'

    def test_strips_surrounding_whitespace(self):
        text = "   ```json\n[1, 2]\n```   "
        assert strip_code_fence(text) == '[1, 2]'


class TestParseLlmJson:
    def test_plain_json_dict(self):
        raw = '{"characters": {"hero": {"name": {"jp": "キリト", "ru": "Кирито"}}}}'
        result = parse_llm_json(raw)
        assert isinstance(result, dict)
        assert "characters" in result

    def test_plain_json_list(self):
        raw = '[{"find": "старый", "replace": "новый"}]'
        result = parse_llm_json(raw)
        assert isinstance(result, list)
        assert result[0]["find"] == "старый"

    def test_with_json_code_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        result = parse_llm_json(raw)
        assert result == {"key": "value"}

    def test_with_plain_code_fence(self):
        raw = '```\n{"key": "value"}\n```'
        result = parse_llm_json(raw)
        assert result == {"key": "value"}

    def test_gemini_cli_wrapper_dict(self):
        """Test handling of {"response": "..."} wrapper from gemini-cli."""
        inner = '{"key": "value"}'
        raw = f'{{"response": "{inner}"}}'
        # This is double-encoded, so parse_llm_json should unwrap it
        # But in practice the inner is a string, not escaped – simulate properly
        import json
        raw = json.dumps({"response": inner})
        result = parse_llm_json(raw)
        assert result == {"key": "value"}

    def test_gemini_cli_wrapper_with_fence(self):
        """Test {"response": "```json...```"} pattern."""
        import json
        inner_json = '{"terms": []}'
        response_str = f'```json\n{inner_json}\n```'
        raw = json.dumps({"response": response_str})
        result = parse_llm_json(raw)
        assert result == {"terms": []}

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Не удалось распарсить JSON"):
            parse_llm_json("это не JSON и не починить")

    def test_empty_object(self):
        raw = '{}'
        result = parse_llm_json(raw)
        assert result == {}

    def test_empty_list(self):
        raw = '[]'
        result = parse_llm_json(raw)
        assert result == []


class TestParseLlmJsonWrapper:
    def test_wrapper_with_valid_inner_json(self):
        """Обёртка с валидным inner JSON → возвращает inner dict."""
        import json as _json
        inner = '{"characters": {"hero": {"source": "Hero", "target": "Герой"}}}'
        raw = _json.dumps({"session_id": "abc", "response": inner})
        result = parse_llm_json(raw)
        assert result == {"characters": {"hero": {"source": "Hero", "target": "Герой"}}}

    def test_wrapper_with_code_fenced_inner_json(self):
        """Обёртка с code-fenced inner JSON → возвращает inner dict."""
        import json as _json
        inner_json = '{"key": "value"}'
        response_str = f'```json\n{inner_json}\n```'
        raw = _json.dumps({"session_id": "abc", "response": response_str})
        result = parse_llm_json(raw)
        assert result == {"key": "value"}

    def test_wrapper_with_empty_response_raises(self):
        """Обёртка с пустым response → ValueError."""
        import json as _json
        raw = _json.dumps({"session_id": "abc", "response": ""})
        with pytest.raises(ValueError, match="пустой response"):
            parse_llm_json(raw)

    def test_wrapper_with_whitespace_response_raises(self):
        """Обёртка с пробельным response → ValueError."""
        import json as _json
        raw = _json.dumps({"session_id": "abc", "response": "   "})
        with pytest.raises(ValueError, match="пустой response"):
            parse_llm_json(raw)

    def test_wrapper_with_invalid_inner_json_raises(self):
        """Обёртка с невалидным inner JSON → ValueError."""
        import json as _json
        raw = _json.dumps({"session_id": "abc", "response": "not valid json at all!!!"})
        with pytest.raises(ValueError):
            parse_llm_json(raw)
