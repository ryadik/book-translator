import pytest
from pathlib import Path
from book_translator.discovery import find_series_root, load_series_config, MARKER_FILE


def make_toml(path: Path, content: str = '[series]\nname = "Test"'):
    """Helper: write a book-translator.toml at path."""
    (path / MARKER_FILE).write_text(content, encoding='utf-8')


class TestFindSeriesRoot:
    def test_finds_from_root(self, tmp_path):
        make_toml(tmp_path)
        assert find_series_root(tmp_path) == tmp_path

    def test_finds_from_depth_1(self, tmp_path):
        make_toml(tmp_path)
        subdir = tmp_path / "volume-01"
        subdir.mkdir()
        assert find_series_root(subdir) == tmp_path

    def test_finds_from_depth_2(self, tmp_path):
        make_toml(tmp_path)
        subdir = tmp_path / "volume-01" / "source"
        subdir.mkdir(parents=True)
        assert find_series_root(subdir) == tmp_path

    def test_finds_from_depth_3(self, tmp_path):
        make_toml(tmp_path)
        subdir = tmp_path / "a" / "b" / "c"
        subdir.mkdir(parents=True)
        assert find_series_root(subdir) == tmp_path

    def test_raises_when_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="book-translator.toml not found"):
            find_series_root(tmp_path)

    def test_raises_contains_init_hint(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="book-translator init"):
            find_series_root(tmp_path)

    def test_first_found_wins_not_nested(self, tmp_path):
        """First toml found walking up wins — no nested series support."""
        make_toml(tmp_path, '[series]\nname = "Outer"')
        inner = tmp_path / "inner"
        inner.mkdir()
        make_toml(inner, '[series]\nname = "Inner"')
        result = find_series_root(inner)
        assert result == inner  # inner wins since it's found first walking up


class TestLoadSeriesConfig:
    def test_loads_minimal_config(self, tmp_path):
        make_toml(tmp_path, '[series]\nname = "Test Novel"')
        cfg = load_series_config(tmp_path)
        assert cfg['series']['name'] == 'Test Novel'

    def test_applies_default_source_lang(self, tmp_path):
        make_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['series']['source_lang'] == 'ja'

    def test_applies_default_target_lang(self, tmp_path):
        make_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['series']['target_lang'] == 'ru'

    def test_applies_default_backend(self, tmp_path):
        make_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['llm']['backend'] == 'gemini'

    def test_applies_default_splitter(self, tmp_path):
        make_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['splitter']['target_chunk_size'] == 600
        assert cfg['splitter']['max_part_chars'] == 800
        assert cfg['splitter']['min_chunk_size'] == 300

    def test_applies_default_workers(self, tmp_path):
        make_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['workers']['max_concurrent'] == 50

    def test_user_overrides_source_lang(self, tmp_path):
        make_toml(tmp_path, '[series]\nname = "Test"\nsource_lang = "en"')
        cfg = load_series_config(tmp_path)
        assert cfg['series']['source_lang'] == 'en'

    def test_user_overrides_backend(self, tmp_path):
        content = '[series]\nname = "Test"\n[llm]\nbackend = "ollama"'
        make_toml(tmp_path, content)
        cfg = load_series_config(tmp_path)
        assert cfg['llm']['backend'] == 'ollama'

    def test_user_overrides_workers(self, tmp_path):
        content = '[series]\nname = "Test"\n[workers]\nmax_concurrent = 10'
        make_toml(tmp_path, content)
        cfg = load_series_config(tmp_path)
        assert cfg['workers']['max_concurrent'] == 10

    def test_raises_missing_series_section(self, tmp_path):
        (tmp_path / MARKER_FILE).write_text('[other]\nkey = "value"', encoding='utf-8')
        with pytest.raises(ValueError, match="Missing required \\[series\\] section"):
            load_series_config(tmp_path)

    def test_raises_missing_series_name(self, tmp_path):
        (tmp_path / MARKER_FILE).write_text('[series]\nsource_lang = "ja"', encoding='utf-8')
        with pytest.raises(ValueError, match="Missing required 'name' field"):
            load_series_config(tmp_path)

    def test_raises_missing_toml_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_series_config(tmp_path)


class TestConfigValidation:
    """Tests for _validate_config — called inside load_series_config after defaults."""

    def _write_toml(self, tmp_path, extra_content: str = '') -> Path:
        content = '[series]\nname = "TestSeries"\n' + extra_content
        (tmp_path / MARKER_FILE).write_text(content, encoding='utf-8')
        return tmp_path

    # ── Language codes ────────────────────────────────────────────────────────

    def test_invalid_source_lang_raises(self, tmp_path):
        self._write_toml(tmp_path, 'source_lang = "xyz123"')
        with pytest.raises(ValueError, match="source_lang"):
            load_series_config(tmp_path)

    def test_invalid_target_lang_raises(self, tmp_path):
        self._write_toml(tmp_path, 'target_lang = "RUUU"')
        with pytest.raises(ValueError, match="target_lang"):
            load_series_config(tmp_path)

    def test_uppercase_lang_code_raises(self, tmp_path):
        self._write_toml(tmp_path, 'source_lang = "JA"')
        with pytest.raises(ValueError, match="source_lang"):
            load_series_config(tmp_path)

    def test_valid_lang_codes_pass(self, tmp_path):
        """Standard 2-letter codes should not raise."""
        self._write_toml(tmp_path, 'source_lang = "ja"\ntarget_lang = "ru"')
        cfg = load_series_config(tmp_path)
        assert cfg['series']['source_lang'] == 'ja'

    # ── Splitter ──────────────────────────────────────────────────────────────

    def test_negative_chunk_size_raises(self, tmp_path):
        self._write_toml(tmp_path, '[splitter]\ntarget_chunk_size = -1')
        with pytest.raises(ValueError, match="target_chunk_size"):
            load_series_config(tmp_path)

    def test_zero_max_part_chars_raises(self, tmp_path):
        self._write_toml(tmp_path, '[splitter]\nmax_part_chars = 0')
        with pytest.raises(ValueError, match="max_part_chars"):
            load_series_config(tmp_path)

    def test_float_chunk_size_raises(self, tmp_path):
        """Chunk sizes must be integers, not floats."""
        self._write_toml(tmp_path, '[splitter]\ntarget_chunk_size = 600.5')
        with pytest.raises(ValueError, match="target_chunk_size"):
            load_series_config(tmp_path)

    # ── Workers ───────────────────────────────────────────────────────────────

    def test_zero_max_concurrent_raises(self, tmp_path):
        self._write_toml(tmp_path, '[workers]\nmax_concurrent = 0')
        with pytest.raises(ValueError, match="max_concurrent"):
            load_series_config(tmp_path)

    def test_over_limit_max_concurrent_raises(self, tmp_path):
        self._write_toml(tmp_path, '[workers]\nmax_concurrent = 201')
        with pytest.raises(ValueError, match="max_concurrent"):
            load_series_config(tmp_path)

    def test_valid_max_concurrent_boundary(self, tmp_path):
        """max_concurrent=1 and 200 should both pass."""
        self._write_toml(tmp_path, '[workers]\nmax_concurrent = 1')
        cfg = load_series_config(tmp_path)
        assert cfg['workers']['max_concurrent'] == 1

    # ── Retry ─────────────────────────────────────────────────────────────────

    def test_zero_max_attempts_raises(self, tmp_path):
        self._write_toml(tmp_path, '[retry]\nmax_attempts = 0')
        with pytest.raises(ValueError, match="max_attempts"):
            load_series_config(tmp_path)

    def test_eleven_max_attempts_raises(self, tmp_path):
        self._write_toml(tmp_path, '[retry]\nmax_attempts = 11')
        with pytest.raises(ValueError, match="max_attempts"):
            load_series_config(tmp_path)

    def test_valid_max_attempts(self, tmp_path):
        self._write_toml(tmp_path, '[retry]\nmax_attempts = 5')
        cfg = load_series_config(tmp_path)
        assert cfg['retry']['max_attempts'] == 5

    # ── Timeouts ──────────────────────────────────────────────────────────────

    def test_negative_worker_timeout_raises(self, tmp_path):
        self._write_toml(tmp_path, '[llm]\nworker_timeout_seconds = -10')
        with pytest.raises(ValueError, match="worker_timeout_seconds"):
            load_series_config(tmp_path)

    def test_zero_proofreading_timeout_raises(self, tmp_path):
        self._write_toml(tmp_path, '[llm]\nproofreading_timeout_seconds = 0')
        with pytest.raises(ValueError, match="proofreading_timeout_seconds"):
            load_series_config(tmp_path)

    def test_valid_float_timeout_passes(self, tmp_path):
        """Timeouts can be floats, e.g. 0.5 for testing."""
        self._write_toml(tmp_path, '[llm]\nworker_timeout_seconds = 30.5')
        cfg = load_series_config(tmp_path)
        assert cfg['llm']['worker_timeout_seconds'] == 30.5

    # ── LLM backend ───────────────────────────────────────────────────────────

    def test_default_backend_is_gemini(self, tmp_path):
        self._write_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['llm']['backend'] == 'gemini'

    def test_default_ollama_url(self, tmp_path):
        self._write_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['llm']['ollama_url'] == 'http://localhost:11434'

    def test_default_stage_models_present(self, tmp_path):
        self._write_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        models = cfg['llm']['models']
        assert models['discovery'] == 'qwen3:8b'
        assert models['translation'] == 'qwen3:30b-a3b'
        assert models['proofreading'] == 'qwen3:30b-a3b'
        assert models['global_proofreading'] == 'qwen3:14b'

    def test_user_can_set_ollama_backend(self, tmp_path):
        self._write_toml(tmp_path, '[llm]\nbackend = "ollama"')
        cfg = load_series_config(tmp_path)
        assert cfg['llm']['backend'] == 'ollama'

    def test_user_can_override_individual_model(self, tmp_path):
        self._write_toml(tmp_path, '[llm]\nbackend = "ollama"\n[llm.models]\ntranslation = "llama3.1:8b"')
        cfg = load_series_config(tmp_path)
        assert cfg['llm']['models']['translation'] == 'llama3.1:8b'
        # other models keep defaults
        assert cfg['llm']['models']['discovery'] == 'qwen3:8b'

    def test_invalid_backend_raises(self, tmp_path):
        self._write_toml(tmp_path, '[llm]\nbackend = "invalid_backend"')
        with pytest.raises(ValueError, match="llm.backend"):
            load_series_config(tmp_path)

    def test_empty_model_name_raises(self, tmp_path):
        self._write_toml(tmp_path, '[llm]\nbackend = "ollama"\n[llm.models]\ntranslation = ""')
        with pytest.raises(ValueError, match="llm.models.translation"):
            load_series_config(tmp_path)

    def test_default_think_is_false(self, tmp_path):
        self._write_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['llm']['options']['think'] is False

    def test_user_can_enable_think(self, tmp_path):
        self._write_toml(tmp_path, '[llm.options]\nthink = true')
        cfg = load_series_config(tmp_path)
        assert cfg['llm']['options']['think'] is True

    def test_default_stage_temperatures_present(self, tmp_path):
        self._write_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        st = cfg['llm']['options']['stage_temperature']
        assert st['discovery'] == 0.1
        assert st['translation'] == 0.4
        assert st['proofreading'] == 0.3
        assert st['global_proofreading'] == 0.1

    def test_user_can_override_stage_temperature(self, tmp_path):
        self._write_toml(tmp_path, '[llm.options.stage_temperature]\ntranslation = 0.7')
        cfg = load_series_config(tmp_path)
        assert cfg['llm']['options']['stage_temperature']['translation'] == 0.7
        # Other stages keep defaults
        assert cfg['llm']['options']['stage_temperature']['discovery'] == 0.1
