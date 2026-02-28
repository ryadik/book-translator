import pytest
from pathlib import Path
from path_resolver import (
    resolve_volume_from_chapter,
    get_series_paths,
    get_volume_paths,
    ensure_volume_dirs,
    resolve_prompt,
    SeriesPaths,
    VolumePaths,
)


class TestResolveVolumeFromChapter:
    def test_valid_path_returns_volume_and_chapter(self, tmp_path):
        chapter = tmp_path / 'volume-01' / 'source' / 'chapter-01.txt'
        chapter.parent.mkdir(parents=True)
        chapter.touch()
        vol, ch = resolve_volume_from_chapter(tmp_path, chapter)
        assert vol == 'volume-01'
        assert ch == 'chapter-01'

    def test_stem_strips_extension(self, tmp_path):
        chapter = tmp_path / 'vol-02' / 'source' / 'prologue.txt'
        chapter.parent.mkdir(parents=True)
        chapter.touch()
        vol, ch = resolve_volume_from_chapter(tmp_path, chapter)
        assert vol == 'vol-02'
        assert ch == 'prologue'

    def test_relative_path_resolved_from_series_root(self, tmp_path):
        chapter = tmp_path / 'volume-01' / 'source' / 'ch01.txt'
        chapter.parent.mkdir(parents=True)
        chapter.touch()
        rel = Path('volume-01') / 'source' / 'ch01.txt'
        vol, ch = resolve_volume_from_chapter(tmp_path, rel)
        assert vol == 'volume-01'
        assert ch == 'ch01'

    def test_invalid_no_source_dir_raises(self, tmp_path):
        chapter = tmp_path / 'volume-01' / 'chapter-01.txt'
        chapter.parent.mkdir(parents=True)
        chapter.touch()
        with pytest.raises(ValueError, match='source'):
            resolve_volume_from_chapter(tmp_path, chapter)

    def test_invalid_flat_path_raises(self, tmp_path):
        chapter = tmp_path / 'chapter-01.txt'
        chapter.touch()
        with pytest.raises(ValueError):
            resolve_volume_from_chapter(tmp_path, chapter)

    def test_path_outside_series_root_raises(self, tmp_path):
        other = Path('/tmp/outside_file.txt')
        with pytest.raises(ValueError, match='not inside series root'):
            resolve_volume_from_chapter(tmp_path, other)

    def test_too_deep_path_raises(self, tmp_path):
        chapter = tmp_path / 'vol' / 'source' / 'subdir' / 'ch.txt'
        chapter.parent.mkdir(parents=True)
        chapter.touch()
        with pytest.raises(ValueError):
            resolve_volume_from_chapter(tmp_path, chapter)


class TestGetSeriesPaths:
    def test_glossary_db_always_in_root(self, tmp_path):
        paths = get_series_paths(tmp_path)
        assert paths.glossary_db == tmp_path.resolve() / 'glossary.db'

    def test_root_is_resolved(self, tmp_path):
        paths = get_series_paths(tmp_path)
        assert paths.root == tmp_path.resolve()

    def test_no_context_files_returns_none(self, tmp_path):
        paths = get_series_paths(tmp_path)
        assert paths.world_info is None
        assert paths.style_guide is None

    def test_series_level_world_info(self, tmp_path):
        wi = tmp_path / 'world_info.md'
        wi.write_text('series level')
        paths = get_series_paths(tmp_path)
        assert paths.world_info == wi

    def test_series_level_style_guide(self, tmp_path):
        sg = tmp_path / 'style_guide.md'
        sg.write_text('series style')
        paths = get_series_paths(tmp_path)
        assert paths.style_guide == sg

    def test_volume_override_wins_for_world_info(self, tmp_path):
        # Both series and volume level exist
        (tmp_path / 'world_info.md').write_text('series level')
        vol_dir = tmp_path / 'vol-01'
        vol_dir.mkdir()
        vol_wi = vol_dir / 'world_info.md'
        vol_wi.write_text('volume level')
        paths = get_series_paths(tmp_path, 'vol-01')
        assert paths.world_info == vol_wi
        assert paths.world_info.read_text() == 'volume level'

    def test_volume_override_wins_for_style_guide(self, tmp_path):
        (tmp_path / 'style_guide.md').write_text('series style')
        vol_dir = tmp_path / 'vol-01'
        vol_dir.mkdir()
        vol_sg = vol_dir / 'style_guide.md'
        vol_sg.write_text('volume style')
        paths = get_series_paths(tmp_path, 'vol-01')
        assert paths.style_guide == vol_sg

    def test_fallback_to_series_when_no_volume_override(self, tmp_path):
        ser_wi = tmp_path / 'world_info.md'
        ser_wi.write_text('series level')
        (tmp_path / 'vol-01').mkdir()
        # No vol-01/world_info.md
        paths = get_series_paths(tmp_path, 'vol-01')
        assert paths.world_info == ser_wi

    def test_no_volume_name_skips_volume_override(self, tmp_path):
        # Series level exists, volume level also exists but no volume_name passed
        (tmp_path / 'world_info.md').write_text('series level')
        vol_dir = tmp_path / 'vol-01'
        vol_dir.mkdir()
        (vol_dir / 'world_info.md').write_text('volume level')
        paths = get_series_paths(tmp_path)  # No volume_name
        assert paths.world_info.read_text() == 'series level'


class TestGetVolumePaths:
    def test_all_paths_correct(self, tmp_path):
        paths = get_volume_paths(tmp_path, 'volume-01')
        assert paths.volume_dir == tmp_path.resolve() / 'volume-01'
        assert paths.source_dir == tmp_path.resolve() / 'volume-01' / 'source'
        assert paths.output_dir == tmp_path.resolve() / 'volume-01' / 'output'
        assert paths.state_dir == tmp_path.resolve() / 'volume-01' / '.state'
        assert paths.chunks_db == tmp_path.resolve() / 'volume-01' / '.state' / 'chunks.db'
        assert paths.logs_dir == tmp_path.resolve() / 'volume-01' / '.state' / 'logs'
        assert paths.cache_dir == tmp_path.resolve() / 'volume-01' / '.state' / 'cache'

    def test_does_not_create_dirs(self, tmp_path):
        paths = get_volume_paths(tmp_path, 'volume-01')
        assert not paths.volume_dir.exists()


class TestEnsureVolumeDirs:
    def test_creates_all_dirs(self, tmp_path):
        paths = get_volume_paths(tmp_path, 'volume-01')
        ensure_volume_dirs(paths)
        assert paths.source_dir.is_dir()
        assert paths.output_dir.is_dir()
        assert paths.state_dir.is_dir()
        assert paths.logs_dir.is_dir()
        assert paths.cache_dir.is_dir()

    def test_idempotent(self, tmp_path):
        paths = get_volume_paths(tmp_path, 'volume-01')
        ensure_volume_dirs(paths)
        ensure_volume_dirs(paths)  # Should not raise


class TestResolvePrompt:
    def test_series_override_wins(self, tmp_path):
        prompts_dir = tmp_path / 'prompts'
        prompts_dir.mkdir()
        (prompts_dir / 'translation.txt').write_text('custom prompt')
        result = resolve_prompt(tmp_path, 'translation', {'translation': 'default prompt'})
        assert result == 'custom prompt'

    def test_fallback_to_bundled(self, tmp_path):
        result = resolve_prompt(tmp_path, 'translation', {'translation': 'default prompt'})
        assert result == 'default prompt'

    def test_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            resolve_prompt(tmp_path, 'nonexistent', {})

    def test_empty_prompts_dir_uses_bundled(self, tmp_path):
        (tmp_path / 'prompts').mkdir()
        result = resolve_prompt(tmp_path, 'translation', {'translation': 'bundled'})
        assert result == 'bundled'
