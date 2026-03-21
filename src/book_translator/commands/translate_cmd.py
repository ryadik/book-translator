from pathlib import Path
from book_translator.discovery import find_series_root
from book_translator.path_resolver import resolve_volume_from_chapter
from book_translator import orchestrator
from book_translator.exceptions import TranslationLockedError
import sys


def run_translate(args):
    series_root = find_series_root()
    chapter_file = args.chapter_file

    # If a directory is provided, translate all .txt files in it
    target = Path(chapter_file)
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()

    if target.is_dir():
        _translate_directory(series_root, target, args)
    elif target.is_file():
        _translate_file(series_root, target, args)
    else:
        print(f"Ошибка: Файл или директория не найдены: {chapter_file}")
        raise SystemExit(1)


def _translate_file(series_root: Path, chapter_path: Path, args):
    """Translate a single chapter file."""
    # Determine auto_docx flag
    docx = getattr(args, 'docx', False)
    no_docx = getattr(args, 'no_docx', False)
    if docx:
        auto_docx = True
    elif no_docx:
        auto_docx = False
    else:
        auto_docx = None  # Will prompt interactively

    # Determine auto_epub flag
    epub = getattr(args, 'epub', False)
    no_epub = getattr(args, 'no_epub', False)
    if epub:
        auto_epub = True
    elif no_epub:
        auto_epub = False
    else:
        auto_epub = None  # Will prompt interactively

    restart_stage = getattr(args, 'stage', None)
    dry_run = getattr(args, 'dry_run', False)

    try:
        orchestrator.run_translation_process(
            series_root=series_root,
            chapter_path=chapter_path,
            debug=args.debug,
            resume=args.resume,
            force=args.force,
            auto_docx=auto_docx,
            auto_epub=auto_epub,
            restart_stage=restart_stage,
            dry_run=dry_run,
        )
    except TranslationLockedError as e:
        print(f"\n🔒 {e}")
        raise SystemExit(1)


def run_translate_all(args):
    """Translate all chapters in all volumes of the series."""
    series_root = find_series_root()

    # Find all volume directories (contain a source/ subdir)
    volumes = sorted(
        d for d in series_root.iterdir()
        if d.is_dir() and (d / 'source').is_dir()
    )

    if not volumes:
        print("Ошибка: Не найдено ни одного тома. Создайте структуру volume-01/source/")
        raise SystemExit(1)

    print(f"\n📚 Найдено {len(volumes)} том(а):")
    for v in volumes:
        print(f"   {v.name}")
    print()

    for vol in volumes:
        source_dir = vol / 'source'
        print(f"\n📖 Том: {vol.name}")
        _translate_directory(series_root, source_dir, args)


def _translate_directory(series_root: Path, source_dir: Path, args):
    """Translate all .txt files found in source_dir."""
    txt_files = sorted(source_dir.glob('*.txt'))
    if not txt_files:
        print(f"Ошибка: В директории '{source_dir}' нет .txt файлов.")
        raise SystemExit(1)

    print(f"\n📂 Найдено {len(txt_files)} файл(ов) для перевода:")
    for f in txt_files:
        print(f"   {f.name}")
    print()

    for i, chapter_path in enumerate(txt_files, 1):
        print(f"\n[{i}/{len(txt_files)}] Перевод: {chapter_path.name}")
        _translate_file(series_root, chapter_path, args)
