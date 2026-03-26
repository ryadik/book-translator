import pytest
import tomllib
from argparse import Namespace
from book_translator.textual_app.screens.init_screen import run_init
from book_translator.db import connection


def test_init_creates_full_structure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = Namespace(name='Test Novel', source_lang='ja', target_lang='ru')
    run_init(args)
    series_dir = tmp_path / 'Test Novel'
    assert (series_dir / 'book-translator.toml').is_file()
    assert (series_dir / 'prompts').is_dir()
    assert (series_dir / 'prompts' / 'world_info.md').is_file()
    assert (series_dir / 'prompts' / 'style_guide.md').is_file()
    assert (series_dir / 'glossary.db').is_file()
    assert (series_dir / 'volume-01' / 'source').is_dir()
    assert (series_dir / 'volume-01' / 'output').is_dir()


def test_init_toml_is_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(Namespace(name='Test', source_lang='en', target_lang='ru'))
    with open(tmp_path / 'Test' / 'book-translator.toml', 'rb') as f:
        cfg = tomllib.load(f)
    assert cfg['series']['name'] == 'Test'
    assert cfg['series']['source_lang'] == 'en'
    assert cfg['series']['target_lang'] == 'ru'
    assert cfg['llm']['backend'] == 'gemini'
    assert cfg['gemini_cli']['model'] == 'gemini-2.5-pro'
    assert cfg['workers']['max_concurrent'] == 50


def test_init_existing_dir_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'Existing').mkdir()
    with pytest.raises(ValueError):
        run_init(Namespace(name='Existing', source_lang='ja', target_lang='ru'))


def test_init_glossary_db_initialized(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(Namespace(name='Test', source_lang='ja', target_lang='ru'))
    with connection(tmp_path / 'Test' / 'glossary.db') as conn:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        assert version == 1


def test_init_world_info_not_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(Namespace(name='Test', source_lang='ja', target_lang='ru'))
    content = (tmp_path / 'Test' / 'prompts' / 'world_info.md').read_text(encoding='utf-8')
    assert len(content) > 10  # not empty


def test_init_style_guide_not_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(Namespace(name='Test', source_lang='ja', target_lang='ru'))
    content = (tmp_path / 'Test' / 'prompts' / 'style_guide.md').read_text(encoding='utf-8')
    assert len(content) > 10


def test_init_toml_splitter_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(Namespace(name='Test', source_lang='ja', target_lang='ru'))
    with open(tmp_path / 'Test' / 'book-translator.toml', 'rb') as f:
        cfg = tomllib.load(f)
    assert cfg['splitter']['target_chunk_size'] == 600
    assert cfg['splitter']['max_part_chars'] == 800
    assert cfg['splitter']['min_chunk_size'] == 300


def test_init_glossary_table_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(Namespace(name='Test', source_lang='ja', target_lang='ru'))
    with connection(tmp_path / 'Test' / 'glossary.db') as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='glossary'"
        ).fetchall()
        assert len(tables) == 1


def test_init_series_dir_uses_cwd(tmp_path, monkeypatch):
    """Ensure series dir is created relative to CWD, not script location."""
    subdir = tmp_path / 'workspace'
    subdir.mkdir()
    monkeypatch.chdir(subdir)
    run_init(Namespace(name='MyNovel', source_lang='ja', target_lang='ru'))
    assert (subdir / 'MyNovel').is_dir()
    assert not (tmp_path / 'MyNovel').exists()


def test_init_prompts_dir_has_template_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(Namespace(name='Test', source_lang='ja', target_lang='ru'))
    prompts_dir = tmp_path / 'Test' / 'prompts'
    assert prompts_dir.is_dir()
    # prompts dir now contains world_info.md and style_guide.md
    assert (prompts_dir / 'world_info.md').is_file()
    assert (prompts_dir / 'style_guide.md').is_file()


def test_init_ollama_backend(tmp_path, monkeypatch):
    """Test that Ollama backend generates correct config."""
    monkeypatch.chdir(tmp_path)
    args = Namespace(name='Test', source_lang='ja', target_lang='ru', backend='ollama')
    run_init(args)
    with open(tmp_path / 'Test' / 'book-translator.toml', 'rb') as f:
        cfg = tomllib.load(f)
    assert cfg['llm']['backend'] == 'ollama'
    assert cfg['llm']['ollama_url'] == 'http://localhost:11434'
    assert cfg['llm']['models']['discovery'] == 'qwen3:8b'
    assert cfg['workers']['max_concurrent'] == 3
    assert cfg['workers']['max_rps'] == 100.0


def test_init_use_current_dir(tmp_path, monkeypatch):
    """Test initialization in current directory."""
    work_dir = tmp_path / 'workspace'
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    args = Namespace(
        name='IgnoredName',
        source_lang='ja',
        target_lang='ru',
        use_current_dir=True
    )
    run_init(args)
    # Files should be created directly in work_dir, not in a subfolder
    assert (work_dir / 'book-translator.toml').is_file()
    assert (work_dir / 'prompts' / 'world_info.md').is_file()
    assert (work_dir / 'prompts' / 'style_guide.md').is_file()
    assert (work_dir / 'glossary.db').is_file()


def test_init_use_current_dir_fails_if_already_initialized(tmp_path, monkeypatch):
    """Test that initializing in current dir fails if already initialized."""
    monkeypatch.chdir(tmp_path)
    # First initialization
    args = Namespace(name='Test', source_lang='ja', target_lang='ru', use_current_dir=True)
    run_init(args)
    # Second initialization should fail
    with pytest.raises(ValueError):
        run_init(args)
