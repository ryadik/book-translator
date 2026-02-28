from book_translator.discovery import find_series_root, load_series_config
from book_translator.db import get_terms, get_all_chapters, get_chunks
from pathlib import Path


def run_status(args):
    series_root = find_series_root()
    config = load_series_config(series_root)
    glossary_db = series_root / 'glossary.db'

    print(f"📚 Серия: {config['series']['name']}")
    print(f"   Языки: {config['series']['source_lang']} → {config['series']['target_lang']}")
    print(f"   Модель: {config['gemini_cli']['model']}")
    print(f"   Корень: {series_root}")

    # Count glossary terms
    terms = get_terms(glossary_db,
                     config['series']['source_lang'],
                     config['series']['target_lang'])
    print(f"   Глоссарий: {len(terms)} терминов")

    # List volumes and their status
    print("\n📖 Тома:")
    for item in sorted(series_root.iterdir()):
        if item.is_dir() and (item / 'source').is_dir():
            chunks_db = item / '.state' / 'chunks.db'
            if chunks_db.is_file():
                chapters = get_all_chapters(chunks_db)
                total_chunks = sum(len(get_chunks(chunks_db, ch)) for ch in chapters)
                print(f"   {item.name}: {len(chapters)} глав, {total_chunks} чанков")
            else:
                source_files = list((item / 'source').glob('*.txt'))
                print(f"   {item.name}: {len(source_files)} файлов (не начат)")
