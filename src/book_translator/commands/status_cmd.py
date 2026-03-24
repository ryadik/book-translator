from book_translator.discovery import find_series_root, load_series_config
from book_translator.db import get_terms, get_all_chapters, get_chunks, get_chapter_stage


def run_status(args):
    series_root = find_series_root()
    config = load_series_config(series_root)
    glossary_db = series_root / 'glossary.db'

    # Header
    print(f"\n📚 Серия: {config['series']['name']}")
    print(f"   Языки:  {config['series']['source_lang']} → {config['series']['target_lang']}")
    print(f"   Модель: {config['gemini_cli']['model']}")
    print(f"   Корень: {series_root}")

    # Glossary
    terms = get_terms(
        glossary_db,
        config['series']['source_lang'],
        config['series']['target_lang'],
    )
    print(f"   Глоссарий: {len(terms)} терминов\n")

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
            print(f"📖 {vol_dir.name} — {len(source_files)} файл(ов), не начат")
            continue

        chapters = get_all_chapters(chunks_db)
        if not chapters:
            print(f"📖 {vol_dir.name} — пустая БД")
            continue

        print(f"📖 {vol_dir.name} — {len(chapters)} гл.")
        rows = [("Глава", "Этап", "Done", "Total", "Ошибки")]

        for chapter in chapters:
            chunks = get_chunks(chunks_db, chapter)
            total = len(chunks)
            stage = get_chapter_stage(chunks_db, chapter)
            emoji = _STATUS_EMOJI.get(stage, '⏳')

            done = sum(1 for c in chunks if c['status'] == 'reading_done')
            errors = sum(1 for c in chunks if c['status'].endswith('_failed'))
            stage_label = stage or 'не начат'

            rows.append(
                (
                chapter,
                f"{emoji} {stage_label}",
                str(done),
                str(total),
                str(errors) if errors else "-",
                )
            )

        widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]
        for row_index, row in enumerate(rows):
            line = " | ".join(str(value).ljust(widths[i]) for i, value in enumerate(row))
            print(line)
            if row_index == 0:
                print("-+-".join("-" * width for width in widths))
        print()
