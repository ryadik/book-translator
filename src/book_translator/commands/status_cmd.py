from pathlib import Path

from book_translator.discovery import find_series_root, load_series_config
from book_translator.db import (
    get_terms, get_all_chapters, get_chunks, get_chunks_by_status, get_chapter_stage
)
from book_translator.tui import console
from rich.table import Table
from rich.text import Text
from rich import box


def run_status(args):
    series_root = find_series_root()
    config = load_series_config(series_root)
    glossary_db = series_root / 'glossary.db'

    # Header
    console.print(f"\n📚 [bold]Серия:[/bold] {config['series']['name']}")
    console.print(f"   Языки:  {config['series']['source_lang']} → {config['series']['target_lang']}")
    console.print(f"   Модель: {config['gemini_cli']['model']}")
    console.print(f"   Корень: {series_root}")

    # Glossary
    terms = get_terms(
        glossary_db,
        config['series']['source_lang'],
        config['series']['target_lang'],
    )
    console.print(f"   Глоссарий: [cyan]{len(terms)}[/cyan] терминов\n")

    # Volumes
    _STATUS_EMOJI = {
        'complete': '✅',
        'global_proofreading': '🔍',
        'proofreading': '✍️',
        'translation': '🌐',
        'discovery': '🔎',
        None: '⏳',
    }

    for vol_dir in sorted(series_root.iterdir()):
        if not (vol_dir.is_dir() and (vol_dir / 'source').is_dir()):
            continue

        chunks_db = vol_dir / '.state' / 'chunks.db'

        if not chunks_db.is_file():
            source_files = list((vol_dir / 'source').glob('*.txt'))
            console.print(f"📖 [bold]{vol_dir.name}[/bold] — {len(source_files)} файл(ов), не начат")
            continue

        chapters = get_all_chapters(chunks_db)
        if not chapters:
            console.print(f"📖 [bold]{vol_dir.name}[/bold] — пустая БД")
            continue

        console.print(f"📖 [bold]{vol_dir.name}[/bold] — {len(chapters)} гл.")

        table = Table(
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            expand=False,
        )
        table.add_column("Глава", style="bold")
        table.add_column("Этап", justify="center")
        table.add_column("Done", justify="right")
        table.add_column("Total", justify="right")
        table.add_column("Ошибки", justify="right", style="red")

        for chapter in chapters:
            chunks = get_chunks(chunks_db, chapter)
            total = len(chunks)
            stage = get_chapter_stage(chunks_db, chapter)
            emoji = _STATUS_EMOJI.get(stage, '⏳')

            done = sum(
                1 for c in chunks
                if c['status'].endswith('_done') or c['status'] == 'reading_done'
            )
            errors = sum(1 for c in chunks if c['status'].endswith('_failed'))
            stage_label = stage or 'не начат'

            table.add_row(
                chapter,
                f"{emoji} {stage_label}",
                str(done),
                str(total),
                str(errors) if errors else "[dim]-[/dim]",
            )

        console.print(table)
        console.print()
