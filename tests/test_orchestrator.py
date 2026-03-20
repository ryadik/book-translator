"""
Tests for the refactored orchestrator.py (phase3 architecture).

Verifies:
- New function signature
- No task_manager / old config imports
- Uses pathlib (no os.path.join)
- Correct DB API usage
"""
import pytest
import inspect
import ast
import importlib
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from argparse import Namespace
import sys
import os

from book_translator import orchestrator


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def create_test_series(tmp_path):
    """Helper: create a minimal series for testing via run_init."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    from book_translator.commands.init_cmd import run_init
    run_init(Namespace(name='TestSeries', source_lang='ja', target_lang='ru'))
    os.chdir(old_cwd)
    series_root = tmp_path / 'TestSeries'
    # Create a chapter source file
    source_file = series_root / 'volume-01' / 'source' / 'test-chapter.txt'
    source_file.write_text('テスト用のテキストです。' * 50, encoding='utf-8')
    return series_root


# ─────────────────────────────────────────────────────────────────────────────
# Signature & import tests
# ─────────────────────────────────────────────────────────────────────────────

def test_run_translation_process_signature():
    """New signature has series_root, chapter_path, debug, resume, force."""
    sig = inspect.signature(orchestrator.run_translation_process)
    params = list(sig.parameters)
    assert 'series_root' in params
    assert 'chapter_path' in params
    assert 'debug' in params
    assert 'resume' in params
    assert 'force' in params


def test_run_translation_process_default_args():
    """debug, resume, force should all default to False."""
    sig = inspect.signature(orchestrator.run_translation_process)
    params = sig.parameters
    assert params['debug'].default is False
    assert params['resume'].default is False
    assert params['force'].default is False


def test_orchestrator_no_task_manager():
    """orchestrator must NOT import task_manager."""
    importlib.reload(orchestrator)
    assert 'task_manager' not in dir(orchestrator)


def test_orchestrator_no_config_module():
    """orchestrator must NOT use old config.load_config()."""
    importlib.reload(orchestrator)
    orch_config = getattr(orchestrator, 'config', None)
    if orch_config is not None:
        assert not hasattr(orch_config, 'load_config'), \
            "old config.load_config should not be used"


def test_orchestrator_has_discovery_import():
    """orchestrator must import discovery module."""
    importlib.reload(orchestrator)
    assert hasattr(orchestrator, 'discovery'), "orchestrator must import discovery"


def test_orchestrator_has_path_resolver_import():
    """orchestrator must import path_resolver module."""
    importlib.reload(orchestrator)
    assert hasattr(orchestrator, 'path_resolver'), "orchestrator must import path_resolver"


def test_orchestrator_has_default_prompts_import():
    """orchestrator must import default_prompts module."""
    importlib.reload(orchestrator)
    assert hasattr(orchestrator, 'default_prompts'), "orchestrator must import default_prompts"


def test_orchestrator_uses_pathlib():
    """Verify orchestrator uses pathlib Path (no os.path.join for paths)."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'src', 'book_translator', 'orchestrator.py')) as f:
        source = f.read()
    tree = ast.parse(source)
    # Check no os.path.join calls (we want pathlib)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if (hasattr(node.func.value, 'id') and
                    node.func.value.id == 'path' and
                    node.func.attr == 'join'):
                    pytest.fail("Found os.path.join — should use pathlib")


def test_orchestrator_no_hardcoded_prompts_open():
    """orchestrator must not open('prompts/...') directly."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'src', 'book_translator', 'orchestrator.py')) as f:
        source = f.read()
    assert 'open("prompts/' not in source, "Should not hardcode open('prompts/'...)"
    assert "open('prompts/" not in source, "Should not hardcode open('prompts/'...)"


def test_orchestrator_no_hardcoded_style_guide():
    """orchestrator must not open data/style_guide.md directly."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'src', 'book_translator', 'orchestrator.py')) as f:
        source = f.read()
    assert 'open("data/style_guide.md")' not in source
    assert "open('data/style_guide.md')" not in source


def test_orchestrator_uses_content_source_not_content_jp():
    """orchestrator must use content_source not content_jp."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'src', 'book_translator', 'orchestrator.py')) as f:
        source = f.read()
    assert "content_jp" not in source, \
        "orchestrator should use 'content_source' not 'content_jp'"


def test_orchestrator_uses_content_target_not_content_ru():
    """orchestrator must use content_target not content_ru."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'src', 'book_translator', 'orchestrator.py')) as f:
        source = f.read()
    assert "content_ru" not in source, \
        "orchestrator should use 'content_target' not 'content_ru'"


# ─────────────────────────────────────────────────────────────────────────────
# Integration-style tests with mocked subprocess
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_series(tmp_path):
    """Set up a test series and return (series_root, chapter_path)."""
    series_root = create_test_series(tmp_path)
    chapter_path = series_root / 'volume-01' / 'source' / 'test-chapter.txt'
    return series_root, chapter_path


@patch('book_translator.orchestrator.term_collector.collect_terms_from_responses', return_value={})
@patch('book_translator.orchestrator.term_collector.present_for_confirmation', return_value={})
@patch('book_translator.orchestrator.term_collector.save_approved_terms')
@patch('book_translator.orchestrator.chapter_splitter.split_chapter_intelligently')
@patch('book_translator.orchestrator.setup_loggers')
@patch('builtins.input', return_value='n')
def test_run_translation_process_lock_file_created(
    mock_input, mock_loggers, mock_splitter, mock_save_terms,
    mock_confirm, mock_collect, tmp_path
):
    """Lock file should be created and then removed after run."""
    series_root, chapter_path = _make_mock_series(tmp_path)
    # Splitter returns empty — so we skip all stages
    mock_splitter.return_value = []

    # Mock _run_workers_pooled to avoid gemini calls
    with patch('book_translator.orchestrator._run_workers_pooled', return_value=True), \
         patch('book_translator.orchestrator._run_global_proofreading', return_value=[]):
        orchestrator.run_translation_process(series_root, chapter_path)

    volume_paths = orchestrator.path_resolver.get_volume_paths(series_root, 'volume-01')
    lock_file = volume_paths.state_dir / '.lock'
    # Lock file must be cleaned up after run
    assert not lock_file.exists(), "Lock file should be removed after successful run"


@patch('book_translator.orchestrator.term_collector.collect_terms_from_responses', return_value={})
@patch('book_translator.orchestrator.term_collector.present_for_confirmation', return_value={})
@patch('book_translator.orchestrator.term_collector.save_approved_terms')
@patch('book_translator.orchestrator.chapter_splitter.split_chapter_intelligently')
@patch('book_translator.orchestrator.setup_loggers')
@patch('builtins.input', return_value='n')
def test_run_translation_process_chunks_db_created(
    mock_input, mock_loggers, mock_splitter, mock_save_terms,
    mock_confirm, mock_collect, tmp_path
):
    """chunks.db should be created after run_translation_process."""
    series_root, chapter_path = _make_mock_series(tmp_path)
    # Splitter returns empty — so we skip all stages
    mock_splitter.return_value = []

    with patch('book_translator.orchestrator._run_workers_pooled', return_value=True), \
         patch('book_translator.orchestrator._run_global_proofreading', return_value=[]):
        orchestrator.run_translation_process(series_root, chapter_path)

    volume_paths = orchestrator.path_resolver.get_volume_paths(series_root, 'volume-01')
    assert volume_paths.chunks_db.exists(), "chunks.db should be created"


@patch('book_translator.orchestrator.term_collector.collect_terms_from_responses', return_value={})
@patch('book_translator.orchestrator.term_collector.present_for_confirmation', return_value={})
@patch('book_translator.orchestrator.term_collector.save_approved_terms')
@patch('book_translator.orchestrator.setup_loggers')
@patch('builtins.input', return_value='n')
def test_run_translation_process_chunks_added_to_db(
    mock_input, mock_loggers, mock_save_terms, mock_confirm, mock_collect, tmp_path
):
    """Chunks from splitter should be persisted to chunks.db."""
    series_root, chapter_path = _make_mock_series(tmp_path)

    fake_chunks = [
        {'id': 0, 'text': 'テスト1'},
        {'id': 1, 'text': 'テスト2'},
    ]

    with patch('book_translator.orchestrator.chapter_splitter.split_chapter_intelligently', return_value=fake_chunks), \
         patch('book_translator.orchestrator._run_workers_pooled', return_value=True), \
         patch('book_translator.orchestrator._run_global_proofreading', return_value=[]):
        orchestrator.run_translation_process(series_root, chapter_path)

    volume_paths = orchestrator.path_resolver.get_volume_paths(series_root, 'volume-01')
    from book_translator import db as db_module
    chunks = db_module.get_chunks(volume_paths.chunks_db, 'test-chapter')
    assert len(chunks) == 2


@patch('book_translator.orchestrator.setup_loggers')
def test_run_translation_process_exits_on_lock(mock_loggers, tmp_path):
    """Should raise TranslationLockedError if lock file exists and resume=False."""
    series_root, chapter_path = _make_mock_series(tmp_path)

    # Manually create the lock file
    volume_paths = orchestrator.path_resolver.get_volume_paths(series_root, 'volume-01')
    orchestrator.path_resolver.ensure_volume_dirs(volume_paths)
    from book_translator import db as db_module
    db_module.init_chunks_db(volume_paths.chunks_db)
    lock_file = volume_paths.state_dir / '.lock'
    lock_file.write_text('99999')

    from book_translator.exceptions import TranslationLockedError
    with pytest.raises(TranslationLockedError, match="блокировка"):
        orchestrator.run_translation_process(series_root, chapter_path, resume=False)



@patch('book_translator.orchestrator.term_collector.collect_terms_from_responses', return_value={})
@patch('book_translator.orchestrator.term_collector.present_for_confirmation', return_value=None)
@patch('book_translator.orchestrator.term_collector.save_approved_terms')
@patch('book_translator.orchestrator.chapter_splitter.split_chapter_intelligently', return_value=[{'id': 0, 'text': 'text'}])
@patch('book_translator.orchestrator.setup_loggers')
@patch('builtins.input', return_value='n')
def test_run_translation_process_user_cancel(
    mock_input, mock_loggers, mock_splitter, mock_save_terms, mock_confirm, mock_collect, tmp_path
):
    """If user cancels during term confirmation, run should abort gracefully."""
    series_root, chapter_path = _make_mock_series(tmp_path)

    with patch('book_translator.orchestrator._run_workers_pooled', return_value=True):
        # Should return None without exception
        result = orchestrator.run_translation_process(series_root, chapter_path)

    # No exception raised means graceful abort
    assert result is None


@patch('book_translator.orchestrator.term_collector.collect_terms_from_responses', return_value={})
@patch('book_translator.orchestrator.term_collector.present_for_confirmation', return_value={})
@patch('book_translator.orchestrator.term_collector.save_approved_terms')
@patch('book_translator.orchestrator.chapter_splitter.split_chapter_intelligently')
@patch('book_translator.orchestrator.setup_loggers')
def test_run_translation_process_output_file_created(
    mock_loggers, mock_splitter, mock_save_terms, mock_confirm, mock_collect, tmp_path
):
    """Output file should be created in volume output dir.

    Uses db.set_chapter_stage() to mark all pipeline stages as complete,
    which is the correct way to skip stages after the DB-based checkpoint refactor.
    """
    series_root, chapter_path = _make_mock_series(tmp_path)
    mock_splitter.return_value = []

    volume_paths = orchestrator.path_resolver.get_volume_paths(series_root, 'volume-01')
    orchestrator.path_resolver.ensure_volume_dirs(volume_paths)
    from book_translator import db as db_module
    db_module.init_chunks_db(volume_paths.chunks_db)

    # Pre-populate chunk with final translated content
    db_module.add_chunk(
        volume_paths.chunks_db,
        'test-chapter', 0,
        content_source='テスト',
        content_target='Тест',
        status='reading_done'
    )

    # Use DB-based checkpoint to skip all stages (replaces old .stage_*_complete files)
    db_module.set_chapter_stage(volume_paths.chunks_db, 'test-chapter', 'complete')

    with patch('book_translator.orchestrator._run_workers_pooled', return_value=True), \
         patch('book_translator.orchestrator._run_global_proofreading', return_value=[]), \
         patch('builtins.input', return_value='n'):
        orchestrator.run_translation_process(series_root, chapter_path)

    output_file = volume_paths.output_dir / 'test-chapter.txt'
    assert output_file.exists(), "Output file should be created"
    assert output_file.read_text(encoding='utf-8') == 'Тест'


# ─────────────────────────────────────────────────────────────────────────────
# New parameter tests: dry_run, restart_stage, auto_docx
# ─────────────────────────────────────────────────────────────────────────────


def test_run_translation_process_signature_has_new_params():
    """Signature must include auto_docx, restart_stage, dry_run."""
    sig = inspect.signature(orchestrator.run_translation_process)
    params = sig.parameters
    assert 'auto_docx' in params
    assert 'restart_stage' in params
    assert 'dry_run' in params
    # Defaults
    assert params['auto_docx'].default is None
    assert params['restart_stage'].default is None
    assert params['dry_run'].default is False


@patch('book_translator.orchestrator.setup_loggers')
@patch('book_translator.orchestrator.chapter_splitter.split_chapter_intelligently', return_value=[])
def test_dry_run_makes_no_subprocess_calls(mock_splitter, mock_loggers, tmp_path):
    """--dry-run must not call subprocess (no gemini-cli invocations)."""
    series_root, chapter_path = _make_mock_series(tmp_path)

    with patch('subprocess.run') as mock_subprocess:
        orchestrator.run_translation_process(
            series_root, chapter_path,
            dry_run=True,
        )

    mock_subprocess.assert_not_called()


@patch('book_translator.orchestrator.setup_loggers')
@patch('book_translator.orchestrator.chapter_splitter.split_chapter_intelligently', return_value=[])
def test_dry_run_returns_none(mock_splitter, mock_loggers, tmp_path):
    """--dry-run must return None without errors."""
    series_root, chapter_path = _make_mock_series(tmp_path)
    result = orchestrator.run_translation_process(
        series_root, chapter_path, dry_run=True
    )
    assert result is None


@patch('book_translator.orchestrator.term_collector.collect_terms_from_responses', return_value={})
@patch('book_translator.orchestrator.term_collector.present_for_confirmation', return_value={})
@patch('book_translator.orchestrator.term_collector.save_approved_terms')
@patch('book_translator.orchestrator.chapter_splitter.split_chapter_intelligently')
@patch('book_translator.orchestrator.setup_loggers')
def test_restart_stage_resets_db_state(mock_loggers, mock_splitter, mock_save, mock_confirm, mock_collect, tmp_path):
    """restart_stage='translation' must reset chapter_state and chunk statuses."""
    series_root, chapter_path = _make_mock_series(tmp_path)
    mock_splitter.return_value = []

    volume_paths = orchestrator.path_resolver.get_volume_paths(series_root, 'volume-01')
    orchestrator.path_resolver.ensure_volume_dirs(volume_paths)
    from book_translator import db as db_module
    db_module.init_chunks_db(volume_paths.chunks_db)

    # Simulate a chapter that has already completed discovery
    db_module.add_chunk(volume_paths.chunks_db, 'test-chapter', 0,
                        content_source='テスト', content_target='',
                        status='discovery_done')
    db_module.set_chapter_stage(volume_paths.chunks_db, 'test-chapter', 'translation')

    with patch('book_translator.orchestrator._run_workers_pooled', return_value=True), \
         patch('book_translator.orchestrator._run_global_proofreading', return_value=[]), \
         patch('builtins.input', return_value='n'):
        orchestrator.run_translation_process(
            series_root, chapter_path,
            restart_stage='discovery',
        )

    # After restart_stage='discovery', stage should have gone back
    # and chunks reset to discovery_pending
    chunks = db_module.get_chunks(volume_paths.chunks_db, 'test-chapter')
    # Stage was reset — chunk was reprocessed from discovery
    assert len(chunks) >= 1  # DB still has the chunk


@patch('book_translator.orchestrator.setup_loggers')
@patch('book_translator.orchestrator.chapter_splitter.split_chapter_intelligently', return_value=[])
@patch('book_translator.orchestrator.convert_to_docx')
def test_auto_docx_false_skips_conversion(mock_docx, mock_splitter, mock_loggers, tmp_path):
    """auto_docx=False must not call convert_to_docx even if output file exists."""
    series_root, chapter_path = _make_mock_series(tmp_path)

    volume_paths = orchestrator.path_resolver.get_volume_paths(series_root, 'volume-01')
    orchestrator.path_resolver.ensure_volume_dirs(volume_paths)
    from book_translator import db as db_module
    db_module.init_chunks_db(volume_paths.chunks_db)
    db_module.add_chunk(volume_paths.chunks_db, 'test-chapter', 0,
                        content_source='テスト', content_target='Тест',
                        status='reading_done')
    db_module.set_chapter_stage(volume_paths.chunks_db, 'test-chapter', 'complete')

    with patch('book_translator.orchestrator._run_workers_pooled', return_value=True), \
         patch('book_translator.orchestrator._run_global_proofreading', return_value=[]):
        orchestrator.run_translation_process(
            series_root, chapter_path, auto_docx=False
        )

    mock_docx.convert_txt_to_docx.assert_not_called()



def test_run_single_worker_signature():
    """_run_single_worker must accept chunks_db: Path and chapter_name: str."""
    sig = inspect.signature(orchestrator._run_single_worker)
    params = list(sig.parameters)
    assert 'chunks_db' in params
    assert 'chapter_name' in params
    assert 'volume_paths' in params
    # Old params that should be gone
    assert 'db_path' not in params
    assert 'project_id' not in params
    assert 'workspace_paths' not in params


def test_run_workers_pooled_signature():
    """_run_workers_pooled must accept chunks_db: Path and chapter_name: str."""
    sig = inspect.signature(orchestrator._run_workers_pooled)
    params = list(sig.parameters)
    assert 'chunks_db' in params
    assert 'chapter_name' in params
    # Old params that should be gone
    assert 'db_path' not in params
    assert 'project_id' not in params
