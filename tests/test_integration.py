"""Integration tests: verify all pieces work together end-to-end."""
import pytest
import os
from pathlib import Path
from argparse import Namespace


def create_series(tmp_path, monkeypatch, name='TestNovel'):
    """Helper: init a series and return its root."""
    monkeypatch.chdir(tmp_path)
    from book_translator.commands.init_cmd import run_init
    run_init(Namespace(name=name, source_lang='ja', target_lang='ru'))
    return tmp_path / name


def test_full_init_to_status_flow(tmp_path, monkeypatch):
    """Test: init → populate glossary → status shows correct data."""
    monkeypatch.chdir(tmp_path)
    from book_translator.commands.init_cmd import run_init
    from book_translator.commands.status_cmd import run_status
    from book_translator.commands.glossary_cmd import run_glossary
    
    # Init
    run_init(Namespace(name='TestNovel', source_lang='ja', target_lang='ru'))
    
    # Import glossary terms
    monkeypatch.chdir(tmp_path / 'TestNovel')
    tsv = tmp_path / 'terms.tsv'
    tsv.write_text('キリト\tКирито\nアスナ\tАсуна\n', encoding='utf-8')
    run_glossary(Namespace(glossary_command='import', file=str(tsv)))
    
    # Status should not raise
    run_status(Namespace())


def test_walk_up_from_subdirectory(tmp_path, monkeypatch):
    """Test: walk-up finds series root from volume/source/."""
    series_root = create_series(tmp_path, monkeypatch)
    
    # cd into deep subdirectory
    subdir = series_root / 'volume-01' / 'source'
    monkeypatch.chdir(subdir)
    
    from book_translator.discovery import find_series_root
    root = find_series_root()
    assert root == series_root.resolve()


def test_walk_up_from_volume_dir(tmp_path, monkeypatch):
    """Test: walk-up finds series root from volume-01/ directly."""
    series_root = create_series(tmp_path, monkeypatch)
    
    monkeypatch.chdir(series_root / 'volume-01')
    
    from book_translator.discovery import find_series_root
    root = find_series_root()
    assert root == series_root.resolve()


def test_no_series_root_error(tmp_path, monkeypatch):
    """Test: FileNotFoundError when no book-translator.toml found."""
    monkeypatch.chdir(tmp_path)
    from book_translator.discovery import find_series_root
    with pytest.raises(FileNotFoundError):
        find_series_root()


def test_glossary_export_import_roundtrip(tmp_path, monkeypatch):
    """Test: export → modify → import preserves updated data."""
    series_root = create_series(tmp_path, monkeypatch)
    glossary_db = series_root / 'glossary.db'
    
    from book_translator.db import add_term, get_terms
    from book_translator.glossary_manager import export_tsv, import_tsv
    
    add_term(glossary_db, 'テスト', 'Тест')
    add_term(glossary_db, 'ソード', 'Меч')
    
    # Export to TSV
    tsv_path = tmp_path / 'export.tsv'
    with open(tsv_path, 'w', encoding='utf-8') as f:
        export_tsv(glossary_db, f)
    
    # Modify the TSV
    content = tsv_path.read_text(encoding='utf-8')
    content = content.replace('Тест', 'Тест (исправлено)')
    tsv_path.write_text(content, encoding='utf-8')
    
    # Import back (upsert updates the translation)
    import_tsv(glossary_db, tsv_path)
    terms = get_terms(glossary_db)
    test_term = [t for t in terms if t['term_source'] == 'テスト'][0]
    assert test_term['term_target'] == 'Тест (исправлено)'


def test_volume_context_override(tmp_path, monkeypatch):
    """Test: volume-level world_info.md overrides series-level."""
    series_root = create_series(tmp_path, monkeypatch)
    
    # Series-level world_info exists from init
    assert (series_root / 'world_info.md').is_file()
    
    # Add volume-level override
    vol_wi = series_root / 'volume-01' / 'world_info.md'
    vol_wi.write_text('Volume 1 specific context', encoding='utf-8')
    
    from book_translator.path_resolver import get_series_paths
    paths = get_series_paths(series_root, 'volume-01')
    assert paths.world_info is not None
    assert paths.world_info.read_text(encoding='utf-8') == 'Volume 1 specific context'


def test_glossary_list_command(tmp_path, monkeypatch):
    """Test: glossary list shows all terms without error."""
    series_root = create_series(tmp_path, monkeypatch)
    monkeypatch.chdir(series_root)
    
    from book_translator.db import add_term
    from book_translator.commands.glossary_cmd import run_glossary
    
    add_term(series_root / 'glossary.db', 'テスト', 'Тест')
    
    # Should not raise
    run_glossary(Namespace(glossary_command='list'))


def test_init_creates_valid_series_root(tmp_path, monkeypatch):
    """Test: after init, find_series_root() from within the series works."""
    series_root = create_series(tmp_path, monkeypatch)
    monkeypatch.chdir(series_root)
    
    from book_translator.discovery import find_series_root, load_series_config
    root = find_series_root()
    cfg = load_series_config(root)
    assert cfg['series']['name'] == 'TestNovel'
    assert cfg['series']['source_lang'] == 'ja'
    assert cfg['series']['target_lang'] == 'ru'
    assert cfg['workers']['max_concurrent'] == 50


def test_glossary_export_to_file(tmp_path, monkeypatch):
    """Test: glossary export --output writes to file."""
    series_root = create_series(tmp_path, monkeypatch)
    monkeypatch.chdir(series_root)
    
    from book_translator.db import add_term
    from book_translator.commands.glossary_cmd import run_glossary
    
    add_term(series_root / 'glossary.db', 'キリト', 'Кирито')
    
    output_path = tmp_path / 'out.tsv'
    run_glossary(Namespace(glossary_command='export', output=str(output_path)))
    
    assert output_path.is_file()
    content = output_path.read_text(encoding='utf-8')
    assert 'キリト' in content
    assert 'Кирито' in content
