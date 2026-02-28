from pathlib import Path
from discovery import find_series_root, load_series_config
from glossary_manager import export_tsv, import_tsv


def run_glossary(args):
    series_root = find_series_root()
    config = load_series_config(series_root)
    glossary_db = series_root / 'glossary.db'
    source_lang = config['series']['source_lang']
    target_lang = config['series']['target_lang']

    if args.glossary_command == 'export':
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                count = export_tsv(glossary_db, f, source_lang, target_lang)
            print(f"Экспортировано {count} терминов в {args.output}")
        else:
            export_tsv(glossary_db, source_lang=source_lang, target_lang=target_lang)

    elif args.glossary_command == 'import':
        tsv_path = Path(args.file)
        if not tsv_path.is_file():
            print(f"Ошибка: Файл не найден: {tsv_path}")
            raise SystemExit(1)
        count = import_tsv(glossary_db, tsv_path, source_lang, target_lang)
        print(f"Импортировано {count} терминов из {tsv_path}")

    elif args.glossary_command == 'list':
        from db import get_terms
        terms = get_terms(glossary_db, source_lang, target_lang)
        if not terms:
            print("Глоссарий пуст.")
            return
        print(f"Глоссарий ({len(terms)} терминов):")
        print(f"{'Исходный':30} {'Перевод':30} {'Комментарий'}")
        print('─' * 80)
        for t in terms:
            print(f"{t['term_source']:30} {t['term_target']:30} {t.get('comment', '')}")
