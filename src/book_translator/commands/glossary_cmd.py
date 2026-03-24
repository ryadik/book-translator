from pathlib import Path
from book_translator.discovery import find_series_root, load_series_config
from book_translator.glossary_manager import export_tsv, import_tsv


def _info(message: str) -> None:
    print(message)


def _success(message: str) -> None:
    print(message)


def _error(message: str) -> None:
    print(message)
    raise SystemExit(1)


def run_glossary(args, info_callback=None, success_callback=None, error_callback=None):
    info = info_callback or _info
    success = success_callback or _success
    error = error_callback or _error

    series_root = find_series_root()
    config = load_series_config(series_root)
    glossary_db = series_root / 'glossary.db'
    source_lang = config['series']['source_lang']
    target_lang = config['series']['target_lang']

    if args.glossary_command == 'export':
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                count = export_tsv(glossary_db, f, source_lang, target_lang)
            success(f"Экспортировано {count} терминов в {args.output}")
        else:
            export_tsv(glossary_db, source_lang=source_lang, target_lang=target_lang)

    elif args.glossary_command == 'import':
        tsv_path = Path(args.file)
        if not tsv_path.is_file():
            error(f"Ошибка: Файл не найден: {tsv_path}")
        count = import_tsv(glossary_db, tsv_path, source_lang, target_lang)
        success(f"Импортировано {count} терминов из {tsv_path}")

    elif args.glossary_command == 'list':
        from book_translator.db import get_terms
        terms = get_terms(glossary_db, source_lang, target_lang)
        if not terms:
            info("Глоссарий пуст.")
            return
        info(f"Глоссарий ({len(terms)} терминов):")
        info(f"{'Исходный':30} {'Перевод':30} {'Комментарий'}")
        info('─' * 80)
        for t in terms:
            info(f"{t['term_source']:30} {t['term_target']:30} {t.get('comment', '')}")
