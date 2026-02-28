import pytest
import sys
from book_translator.cli import build_parser


def test_parser_init():
    parser = build_parser()
    args = parser.parse_args(['init', 'Test Novel'])
    assert args.command == 'init'
    assert args.name == 'Test Novel'
    assert args.source_lang == 'ja'
    assert args.target_lang == 'ru'


def test_parser_translate():
    parser = build_parser()
    args = parser.parse_args(['translate', 'vol-01/source/ch01.txt', '--debug'])
    assert args.command == 'translate'
    assert args.chapter_file == 'vol-01/source/ch01.txt'
    assert args.debug is True


def test_parser_glossary_export():
    parser = build_parser()
    args = parser.parse_args(['glossary', 'export', '--output', 'out.tsv'])
    assert args.command == 'glossary'
    assert args.glossary_command == 'export'
    assert args.output == 'out.tsv'


def test_parser_glossary_import():
    parser = build_parser()
    args = parser.parse_args(['glossary', 'import', 'terms.tsv'])
    assert args.glossary_command == 'import'
    assert args.file == 'terms.tsv'


def test_parser_glossary_list():
    parser = build_parser()
    args = parser.parse_args(['glossary', 'list'])
    assert args.glossary_command == 'list'


def test_parser_status():
    parser = build_parser()
    args = parser.parse_args(['status'])
    assert args.command == 'status'


def test_parser_no_command_fails():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_translate_resume_force():
    parser = build_parser()
    args = parser.parse_args(['translate', 'vol/source/ch.txt', '--resume', '--force'])
    assert args.resume is True
    assert args.force is True


def test_translate_defaults():
    parser = build_parser()
    args = parser.parse_args(['translate', 'vol/source/ch.txt'])
    assert args.debug is False
    assert args.resume is False
    assert args.force is False
