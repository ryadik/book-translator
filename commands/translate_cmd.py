from pathlib import Path
from discovery import find_series_root, load_series_config
from path_resolver import resolve_volume_from_chapter
import orchestrator


def run_translate(args):
    series_root = find_series_root()
    chapter_path = Path(args.chapter_file)

    # Validate chapter path
    if not chapter_path.is_file():
        print(f"Ошибка: Файл не найден: {chapter_path}")
        raise SystemExit(1)

    # Resolve to absolute if relative
    if not chapter_path.is_absolute():
        chapter_path = (Path.cwd() / chapter_path).resolve()

    orchestrator.run_translation_process(
        series_root=series_root,
        chapter_path=chapter_path,
        debug=args.debug,
        resume=args.resume,
        force=args.force
    )
