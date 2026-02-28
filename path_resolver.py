"""
Path resolution module.
Centralizes ALL path logic for the series-centric architecture.
"""
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict


@dataclass
class SeriesPaths:
    root: Path                       # series root (where book-translator.toml lives)
    glossary_db: Path                # root / glossary.db
    world_info: Optional[Path]       # resolved world_info.md (volume or series level)
    style_guide: Optional[Path]      # resolved style_guide.md (volume or series level)


@dataclass
class VolumePaths:
    volume_dir: Path                 # root / volume-XX
    source_dir: Path                 # volume_dir / source
    output_dir: Path                 # volume_dir / output
    state_dir: Path                  # volume_dir / .state
    chunks_db: Path                  # state_dir / chunks.db
    logs_dir: Path                   # state_dir / logs
    cache_dir: Path                  # state_dir / cache


def resolve_volume_from_chapter(series_root: Path, chapter_path: Path) -> tuple:
    """Extract volume_name and chapter_name from chapter path.

    chapter_path must follow: {volume}/source/{chapter}.txt
    Both absolute and relative paths (relative to series_root) are supported.

    Args:
        series_root: Absolute path to series root directory
        chapter_path: Path to chapter file (absolute or relative to series_root)

    Returns:
        (volume_name: str, chapter_name: str)
        chapter_name is the stem without extension (e.g. 'chapter-01' from 'chapter-01.txt')

    Raises:
        ValueError: if path doesn't match expected pattern {volume}/source/{chapter}.txt
    """
    series_root = series_root.resolve()
    # Make chapter_path absolute
    if not chapter_path.is_absolute():
        chapter_path = (series_root / chapter_path).resolve()
    else:
        chapter_path = chapter_path.resolve()

    try:
        rel = chapter_path.relative_to(series_root)
    except ValueError:
        raise ValueError(
            f"Chapter path {chapter_path} is not inside series root {series_root}"
        )

    parts = rel.parts  # e.g. ('volume-01', 'source', 'chapter-01.txt')
    if len(parts) != 3 or parts[1] != 'source':
        raise ValueError(
            f"Chapter path must follow '{{volume}}/source/{{chapter}}.txt' pattern. "
            f"Got: {rel}"
        )

    volume_name = parts[0]
    chapter_name = Path(parts[2]).stem  # 'chapter-01' from 'chapter-01.txt'
    return volume_name, chapter_name


def get_series_paths(series_root: Path, volume_name: Optional[str] = None) -> SeriesPaths:
    """Resolve series-level paths with optional volume-level context overrides.

    Resolution order for world_info.md and style_guide.md:
    1. {volume_dir}/world_info.md  (if volume_name provided and file exists)
    2. {series_root}/world_info.md (fallback)
    3. None                        (if neither exists)

    Args:
        series_root: Path to series root directory
        volume_name: Optional volume folder name for context override lookup

    Returns:
        SeriesPaths dataclass with resolved paths
    """
    series_root = series_root.resolve()
    world_info = None
    style_guide = None

    # Volume-level override takes priority
    if volume_name:
        vol_wi = series_root / volume_name / 'world_info.md'
        vol_sg = series_root / volume_name / 'style_guide.md'
        if vol_wi.is_file():
            world_info = vol_wi
        if vol_sg.is_file():
            style_guide = vol_sg

    # Fallback to series-level
    if world_info is None:
        ser_wi = series_root / 'world_info.md'
        if ser_wi.is_file():
            world_info = ser_wi
    if style_guide is None:
        ser_sg = series_root / 'style_guide.md'
        if ser_sg.is_file():
            style_guide = ser_sg

    return SeriesPaths(
        root=series_root,
        glossary_db=series_root / 'glossary.db',
        world_info=world_info,
        style_guide=style_guide,
    )


def get_volume_paths(series_root: Path, volume_name: str) -> VolumePaths:
    """Resolve all paths for a volume directory.

    Does NOT create any directories — call ensure_volume_dirs() for that.

    Args:
        series_root: Path to series root
        volume_name: Volume folder name (e.g. 'volume-01')

    Returns:
        VolumePaths dataclass with all resolved paths
    """
    series_root = series_root.resolve()
    vol = series_root / volume_name
    state = vol / '.state'
    return VolumePaths(
        volume_dir=vol,
        source_dir=vol / 'source',
        output_dir=vol / 'output',
        state_dir=state,
        chunks_db=state / 'chunks.db',
        logs_dir=state / 'logs',
        cache_dir=state / 'cache',
    )


def ensure_volume_dirs(volume_paths: VolumePaths) -> None:
    """Create all required volume directories if they don't exist."""
    volume_paths.source_dir.mkdir(parents=True, exist_ok=True)
    volume_paths.output_dir.mkdir(parents=True, exist_ok=True)
    volume_paths.state_dir.mkdir(parents=True, exist_ok=True)
    volume_paths.logs_dir.mkdir(parents=True, exist_ok=True)
    volume_paths.cache_dir.mkdir(parents=True, exist_ok=True)


def resolve_prompt(series_root: Path, prompt_name: str, bundled_prompts: Dict[str, str]) -> str:
    """Resolve a prompt: series override → bundled default.

    Checks {series_root}/prompts/{prompt_name}.txt first.
    Falls back to bundled_prompts dict.

    Args:
        series_root: Path to series root
        prompt_name: Prompt name without extension (e.g. 'translation')
        bundled_prompts: Dict mapping prompt names to default content strings

    Returns:
        Prompt content string

    Raises:
        FileNotFoundError: if prompt not found in either location
    """
    override_path = series_root / 'prompts' / f'{prompt_name}.txt'
    if override_path.is_file():
        return override_path.read_text(encoding='utf-8')
    if prompt_name in bundled_prompts:
        return bundled_prompts[prompt_name]
    raise FileNotFoundError(
        f"Prompt '{prompt_name}' not found at {override_path} "
        f"and not in bundled defaults."
    )
