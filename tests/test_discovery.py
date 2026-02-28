import pytest
from pathlib import Path
from discovery import find_series_root, load_series_config, MARKER_FILE


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

    def test_applies_default_model(self, tmp_path):
        make_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['gemini_cli']['model'] == 'gemini-2.5-pro'

    def test_applies_default_splitter(self, tmp_path):
        make_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['splitter']['target_chunk_size'] == 600
        assert cfg['splitter']['max_part_chars'] == 800

    def test_applies_default_workers(self, tmp_path):
        make_toml(tmp_path)
        cfg = load_series_config(tmp_path)
        assert cfg['workers']['max_concurrent'] == 50

    def test_user_overrides_source_lang(self, tmp_path):
        make_toml(tmp_path, '[series]\nname = "Test"\nsource_lang = "en"')
        cfg = load_series_config(tmp_path)
        assert cfg['series']['source_lang'] == 'en'

    def test_user_overrides_model(self, tmp_path):
        content = '[series]\nname = "Test"\n[gemini_cli]\nmodel = "gemini-3-pro-preview"'
        make_toml(tmp_path, content)
        cfg = load_series_config(tmp_path)
        assert cfg['gemini_cli']['model'] == 'gemini-3-pro-preview'

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
