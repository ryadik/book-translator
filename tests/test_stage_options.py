"""Tests for orchestrator._stage_options helper."""
from book_translator.orchestrator import _stage_options


class TestStageOptions:
    def test_applies_stage_temperature_override(self):
        base = {"temperature": 0.3, "num_ctx": 8192, "stage_temperature": {"discovery": 0.1}}
        result = _stage_options(base, "discovery")
        assert result["temperature"] == 0.1

    def test_keeps_base_temperature_when_no_override(self):
        base = {"temperature": 0.3, "num_ctx": 8192, "stage_temperature": {"discovery": 0.1}}
        result = _stage_options(base, "translation")
        assert result["temperature"] == 0.3

    def test_stage_temperature_key_removed_from_result(self):
        base = {"temperature": 0.3, "stage_temperature": {"translation": 0.5}}
        result = _stage_options(base, "translation")
        assert "stage_temperature" not in result

    def test_empty_stage_temperature_dict(self):
        base = {"temperature": 0.3, "num_ctx": 8192, "stage_temperature": {}}
        result = _stage_options(base, "translation")
        assert result["temperature"] == 0.3
        assert result["num_ctx"] == 8192

    def test_no_stage_temperature_key_at_all(self):
        base = {"temperature": 0.3, "num_ctx": 8192}
        result = _stage_options(base, "discovery")
        assert result == {"temperature": 0.3, "num_ctx": 8192}

    def test_does_not_mutate_original(self):
        base = {"temperature": 0.3, "stage_temperature": {"discovery": 0.1}}
        _stage_options(base, "discovery")
        assert "stage_temperature" in base  # original unchanged

    def test_think_flag_preserved(self):
        base = {"temperature": 0.3, "think": False, "stage_temperature": {}}
        result = _stage_options(base, "translation")
        assert result["think"] is False
