"""
Tests for translate_cmd.py:
- run_translate: single file, directory, missing path
- run_translate_all: multiple volumes
- _translate_file: flag mapping (docx/no_docx, stage, dry_run), locked error → SystemExit
"""
import pytest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from book_translator.commands.translate_cmd import (
    run_translate,
    run_translate_all,
    _translate_file,
    _translate_directory,
)
from book_translator.exceptions import TranslationLockedError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _base_args(**kwargs) -> Namespace:
    """Return a Namespace with the typical translate defaults."""
    defaults = dict(
        debug=False,
        resume=False,
        force=False,
        docx=False,
        no_docx=False,
        stage=None,
        dry_run=False,
    )
    defaults.update(kwargs)
    return Namespace(**defaults)


def _make_series(tmp_path: Path, volumes: int = 1) -> Path:
    """Create a minimal series directory structure."""
    from argparse import Namespace as NS
    from book_translator.commands.init_cmd import run_init
    import os
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    run_init(NS(name='TestSeries', source_lang='ja', target_lang='ru'))
    os.chdir(old_cwd)
    series_root = tmp_path / 'TestSeries'

    for i in range(2, volumes + 1):
        vol = series_root / f'volume-0{i}'
        (vol / 'source').mkdir(parents=True)
        (vol / 'output').mkdir(parents=True)

    return series_root


# ─────────────────────────────────────────────────────────────────────────────
# _translate_file: flag mapping
# ─────────────────────────────────────────────────────────────────────────────

class TestTranslateFileFlags:

    @patch('book_translator.commands.translate_cmd.orchestrator.run_translation_process')
    def test_no_docx_flag_passes_false(self, mock_run, tmp_path):
        """--no-docx must pass auto_docx=False to orchestrator."""
        series_root = _make_series(tmp_path)
        chapter = series_root / 'volume-01' / 'source' / 'ch.txt'
        chapter.write_text('テスト', encoding='utf-8')
        args = _base_args(no_docx=True)

        _translate_file(series_root, chapter, args)

        _, kwargs = mock_run.call_args
        assert kwargs['auto_docx'] is False

    @patch('book_translator.commands.translate_cmd.orchestrator.run_translation_process')
    def test_docx_flag_passes_true(self, mock_run, tmp_path):
        """--docx must pass auto_docx=True to orchestrator."""
        series_root = _make_series(tmp_path)
        chapter = series_root / 'volume-01' / 'source' / 'ch.txt'
        chapter.write_text('テスト', encoding='utf-8')
        args = _base_args(docx=True)

        _translate_file(series_root, chapter, args)

        _, kwargs = mock_run.call_args
        assert kwargs['auto_docx'] is True

    @patch('book_translator.commands.translate_cmd.orchestrator.run_translation_process')
    def test_no_docx_flags_passes_none(self, mock_run, tmp_path):
        """Neither flag → auto_docx=None (interactive mode)."""
        series_root = _make_series(tmp_path)
        chapter = series_root / 'volume-01' / 'source' / 'ch.txt'
        chapter.write_text('テスト', encoding='utf-8')
        args = _base_args()  # both False

        _translate_file(series_root, chapter, args)

        _, kwargs = mock_run.call_args
        assert kwargs['auto_docx'] is None

    @patch('book_translator.commands.translate_cmd.orchestrator.run_translation_process')
    def test_stage_flag_forwarded(self, mock_run, tmp_path):
        """--stage proofreading must be forwarded as restart_stage."""
        series_root = _make_series(tmp_path)
        chapter = series_root / 'volume-01' / 'source' / 'ch.txt'
        chapter.write_text('テスト', encoding='utf-8')
        args = _base_args(stage='proofreading')

        _translate_file(series_root, chapter, args)

        _, kwargs = mock_run.call_args
        assert kwargs['restart_stage'] == 'proofreading'

    @patch('book_translator.commands.translate_cmd.orchestrator.run_translation_process')
    def test_dry_run_forwarded(self, mock_run, tmp_path):
        """--dry-run must be forwarded to orchestrator."""
        series_root = _make_series(tmp_path)
        chapter = series_root / 'volume-01' / 'source' / 'ch.txt'
        chapter.write_text('テスト', encoding='utf-8')
        args = _base_args(dry_run=True)

        _translate_file(series_root, chapter, args)

        _, kwargs = mock_run.call_args
        assert kwargs['dry_run'] is True

    @patch('book_translator.commands.translate_cmd.orchestrator.run_translation_process',
           side_effect=TranslationLockedError('locked'))
    def test_locked_error_becomes_system_exit(self, mock_run, tmp_path):
        """TranslationLockedError must be caught and converted to SystemExit(1)."""
        series_root = _make_series(tmp_path)
        chapter = series_root / 'volume-01' / 'source' / 'ch.txt'
        chapter.write_text('テスト', encoding='utf-8')
        args = _base_args()

        with pytest.raises(SystemExit) as exc_info:
            _translate_file(series_root, chapter, args)

        assert exc_info.value.code == 1


# ─────────────────────────────────────────────────────────────────────────────
# _translate_directory
# ─────────────────────────────────────────────────────────────────────────────

class TestTranslateDirectory:

    @patch('book_translator.commands.translate_cmd._translate_file')
    def test_translates_all_txt_files(self, mock_file, tmp_path):
        """All .txt files in source dir should be translated."""
        series_root = _make_series(tmp_path)
        source = series_root / 'volume-01' / 'source'
        (source / 'ch01.txt').write_text('テスト1', encoding='utf-8')
        (source / 'ch02.txt').write_text('テスト2', encoding='utf-8')

        args = _base_args()
        _translate_directory(series_root, source, args)

        assert mock_file.call_count == 2
        called_paths = {c[0][1].name for c in mock_file.call_args_list}
        assert called_paths == {'ch01.txt', 'ch02.txt'}

    @patch('book_translator.commands.translate_cmd._translate_file')
    def test_ignores_non_txt_files(self, mock_file, tmp_path):
        """Non-.txt files (e.g. .md) must be ignored."""
        series_root = _make_series(tmp_path)
        source = series_root / 'volume-01' / 'source'
        (source / 'ch01.txt').write_text('テスト', encoding='utf-8')
        (source / 'notes.md').write_text('notes', encoding='utf-8')

        args = _base_args()
        _translate_directory(series_root, source, args)

        assert mock_file.call_count == 1

    def test_empty_directory_raises_system_exit(self, tmp_path):
        """Empty source dir must raise SystemExit(1)."""
        series_root = _make_series(tmp_path)
        source = series_root / 'volume-01' / 'source'
        # source is empty by default (no txt files placed)

        args = _base_args()
        with pytest.raises(SystemExit) as exc_info:
            _translate_directory(series_root, source, args)

        assert exc_info.value.code == 1

    @patch('book_translator.commands.translate_cmd._translate_file')
    def test_files_processed_in_sorted_order(self, mock_file, tmp_path):
        """Files should be processed in sorted (alphabetical) order."""
        series_root = _make_series(tmp_path)
        source = series_root / 'volume-01' / 'source'
        for name in ['ch03.txt', 'ch01.txt', 'ch02.txt']:
            (source / name).write_text('テスト', encoding='utf-8')

        args = _base_args()
        _translate_directory(series_root, source, args)

        call_names = [c[0][1].name for c in mock_file.call_args_list]
        assert call_names == ['ch01.txt', 'ch02.txt', 'ch03.txt']


# ─────────────────────────────────────────────────────────────────────────────
# run_translate: routing
# ─────────────────────────────────────────────────────────────────────────────

class TestRunTranslateRouting:

    @patch('book_translator.commands.translate_cmd._translate_file')
    @patch('book_translator.commands.translate_cmd.find_series_root')
    def test_routes_file_to_translate_file(self, mock_root, mock_file, tmp_path):
        """Passing a file path routes to _translate_file."""
        series_root = _make_series(tmp_path)
        mock_root.return_value = series_root

        chapter = series_root / 'volume-01' / 'source' / 'ch.txt'
        chapter.write_text('テスト', encoding='utf-8')

        args = _base_args(chapter_file=str(chapter))
        run_translate(args)

        mock_file.assert_called_once()

    @patch('book_translator.commands.translate_cmd._translate_directory')
    @patch('book_translator.commands.translate_cmd.find_series_root')
    def test_routes_directory_to_translate_directory(self, mock_root, mock_dir, tmp_path):
        """Passing a directory path routes to _translate_directory."""
        series_root = _make_series(tmp_path)
        mock_root.return_value = series_root

        source = series_root / 'volume-01' / 'source'
        args = _base_args(chapter_file=str(source))
        run_translate(args)

        mock_dir.assert_called_once()

    @patch('book_translator.commands.translate_cmd.find_series_root')
    def test_nonexistent_path_raises_system_exit(self, mock_root, tmp_path):
        """A path that doesn't exist should raise SystemExit(1)."""
        series_root = _make_series(tmp_path)
        mock_root.return_value = series_root

        args = _base_args(chapter_file=str(tmp_path / 'nonexistent.txt'))
        with pytest.raises(SystemExit) as exc_info:
            run_translate(args)

        assert exc_info.value.code == 1


# ─────────────────────────────────────────────────────────────────────────────
# run_translate_all
# ─────────────────────────────────────────────────────────────────────────────

class TestRunTranslateAll:

    @patch('book_translator.commands.translate_cmd._translate_directory')
    @patch('book_translator.commands.translate_cmd.find_series_root')
    def test_translates_each_volume(self, mock_root, mock_dir, tmp_path):
        """translate-all should call _translate_directory for each volume."""
        series_root = _make_series(tmp_path, volumes=3)
        mock_root.return_value = series_root

        args = _base_args()
        run_translate_all(args)

        # volume-01, volume-02, volume-03
        assert mock_dir.call_count == 3

    @patch('book_translator.commands.translate_cmd.find_series_root')
    def test_no_volumes_raises_system_exit(self, mock_root, tmp_path):
        """No volumes (no subdir with source/) should raise SystemExit(1)."""
        # series_root with no volume dirs
        series_root = tmp_path / 'EmptySeries'
        (series_root).mkdir()
        (series_root / 'book-translator.toml').write_text('[series]\nname = "Empty"', encoding='utf-8')
        mock_root.return_value = series_root

        args = _base_args()
        with pytest.raises(SystemExit) as exc_info:
            run_translate_all(args)

        assert exc_info.value.code == 1

    @patch('book_translator.commands.translate_cmd._translate_directory')
    @patch('book_translator.commands.translate_cmd.find_series_root')
    def test_volumes_processed_in_sorted_order(self, mock_root, mock_dir, tmp_path):
        """Volumes must be processed in sorted (alphabetical) order."""
        series_root = _make_series(tmp_path, volumes=3)
        mock_root.return_value = series_root

        args = _base_args()
        run_translate_all(args)

        call_dirs = [c[0][1].parent.name for c in mock_dir.call_args_list]
        assert call_dirs == sorted(call_dirs)
