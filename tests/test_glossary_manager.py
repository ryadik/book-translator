import pytest
from io import StringIO
from pathlib import Path
from book_translator.db import init_glossary_db, add_term, get_terms
from book_translator.glossary_manager import export_tsv, import_tsv, generate_approval_tsv


def test_export_tsv(tmp_path):
    db_path = tmp_path / 'glossary.db'
    init_glossary_db(db_path)
    add_term(db_path, 'キリト', 'Кирито', comment='Главный герой')
    add_term(db_path, 'アスナ', 'Асуна')
    output = StringIO()
    count = export_tsv(db_path, output)
    assert count == 2
    lines = output.getvalue().strip().split('\n')
    assert lines[0].startswith('#')  # header comment
    content = output.getvalue()
    assert 'キリト\tКирито\tГлавный герой' in content


def test_import_tsv(tmp_path):
    db_path = tmp_path / 'glossary.db'
    init_glossary_db(db_path)
    tsv = tmp_path / 'terms.tsv'
    tsv.write_text('# Comment line\nキリト\tКирито\tГерой\nアスナ\tАсуна\n', encoding='utf-8')
    count = import_tsv(db_path, tsv)
    assert count == 2
    terms = get_terms(db_path)
    assert len(terms) == 2


def test_import_tsv_skips_malformed(tmp_path):
    db_path = tmp_path / 'glossary.db'
    init_glossary_db(db_path)
    tsv = tmp_path / 'bad.tsv'
    tsv.write_text('only_one_column\n\n# comment\nvalid\tterm\n', encoding='utf-8')
    count = import_tsv(db_path, tsv)
    assert count == 1


def test_export_import_roundtrip(tmp_path):
    db_path = tmp_path / 'glossary.db'
    init_glossary_db(db_path)
    add_term(db_path, 'テスト', 'Тест', comment='test')
    tsv_path = tmp_path / 'export.tsv'
    with open(tsv_path, 'w', encoding='utf-8') as f:
        export_tsv(db_path, f)
    # Clear DB
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute('DELETE FROM glossary')
    conn.commit()
    conn.close()
    # Import back
    count = import_tsv(db_path, tsv_path)
    assert count == 1
    terms = get_terms(db_path)
    assert terms[0]['term_source'] == 'テスト'
    assert terms[0]['term_target'] == 'Тест'


def test_generate_approval_tsv(tmp_path):
    terms = [
        {'term_source': 'キリト', 'term_target': 'Кирито', 'comment': 'герой'},
        {'term_jp': 'アスナ', 'term_ru': 'Асуна', 'comment': ''},
    ]
    output_path = tmp_path / 'approval.tsv'
    generate_approval_tsv(terms, output_path)
    content = output_path.read_text(encoding='utf-8')
    assert content.startswith('#')
    assert 'キリト' in content
    assert 'アスナ' in content


def test_export_empty_glossary(tmp_path):
    db_path = tmp_path / 'glossary.db'
    init_glossary_db(db_path)
    output = StringIO()
    count = export_tsv(db_path, output)
    assert count == 0
    assert output.getvalue().startswith('#')  # header still written


def test_import_empty_file(tmp_path):
    db_path = tmp_path / 'glossary.db'
    init_glossary_db(db_path)
    tsv = tmp_path / 'empty.tsv'
    tsv.write_text('', encoding='utf-8')
    count = import_tsv(db_path, tsv)
    assert count == 0


def test_export_tsv_stdout_default(tmp_path, capsys):
    """export_tsv with no output arg writes to stdout."""
    db_path = tmp_path / 'glossary.db'
    init_glossary_db(db_path)
    add_term(db_path, '勇者', 'герой')
    count = export_tsv(db_path)
    captured = capsys.readouterr()
    assert count == 1
    assert '勇者' in captured.out


def test_import_tsv_with_comment(tmp_path):
    """Verify the comment field is stored correctly on import."""
    db_path = tmp_path / 'glossary.db'
    init_glossary_db(db_path)
    tsv = tmp_path / 'terms.tsv'
    tsv.write_text('剣士\tмечник\tтермин из главы 5\n', encoding='utf-8')
    count = import_tsv(db_path, tsv)
    assert count == 1
    terms = get_terms(db_path)
    assert terms[0]['comment'] == 'термин из главы 5'


def test_generate_approval_tsv_mixed_keys(tmp_path):
    """generate_approval_tsv handles both old (term_jp/term_ru) and new (term_source/term_target) keys."""
    terms = [
        {'term_jp': '魔王', 'term_ru': 'Повелитель тьмы'},
        {'term_source': '勇者', 'term_target': 'герой', 'comment': 'главный герой'},
    ]
    output_path = tmp_path / 'approval.tsv'
    generate_approval_tsv(terms, output_path)
    content = output_path.read_text(encoding='utf-8')
    assert '魔王' in content
    assert '勇者' in content
    assert 'главный герой' in content
