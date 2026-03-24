import argparse
import sys

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='book-translator',
        description='CLI для перевода ранобэ с использованием gemini-cli'
    )
    subparsers = parser.add_subparsers(dest='command', required=False)

    # --- init ---
    init_parser = subparsers.add_parser('init', help='Создать новую серию')
    init_parser.add_argument('name', type=str, help='Название серии')
    init_parser.add_argument('--source-lang', default='ja', help='Исходный язык (ISO 639-1)')
    init_parser.add_argument('--target-lang', default='ru', help='Целевой язык (ISO 639-1)')

    # --- translate ---
    tr_parser = subparsers.add_parser('translate', help='Перевести главу или директорию')
    tr_parser.add_argument(
        'chapter_file', type=str,
        help='Путь к файлу главы или директории source/ (volume/source/chapter.txt)'
    )
    tr_parser.add_argument('--debug', action='store_true', help='Включить подробное логирование')
    tr_parser.add_argument('--resume', action='store_true', help='Возобновить прерванный перевод')
    tr_parser.add_argument('--force', action='store_true', help='Очистить состояние и начать заново')
    tr_parser.add_argument('--dry-run', action='store_true', help='Показать план без вызовов API')
    tr_parser.add_argument(
        '--stage',
        choices=['discovery', 'translation', 'proofreading', 'global_proofreading'],
        default=None,
        help='Принудительно перезапустить с указанного этапа'
    )
    docx_group = tr_parser.add_mutually_exclusive_group()
    docx_group.add_argument('--docx', action='store_true', dest='docx', help='Конвертировать в .docx')
    docx_group.add_argument('--no-docx', action='store_true', dest='no_docx', help='Не конвертировать в .docx')
    epub_group = tr_parser.add_mutually_exclusive_group()
    epub_group.add_argument('--epub', action='store_true', dest='epub', help='Конвертировать в .epub')
    epub_group.add_argument('--no-epub', action='store_true', dest='no_epub', help='Не конвертировать в .epub')

    # --- translate-all ---
    all_parser = subparsers.add_parser('translate-all', help='Перевести все тома серии')
    all_parser.add_argument('--debug', action='store_true', help='Включить подробное логирование')
    all_parser.add_argument('--resume', action='store_true', help='Возобновить прерванный перевод')
    all_parser.add_argument('--force', action='store_true', help='Очистить состояние и начать заново')
    all_parser.add_argument('--dry-run', action='store_true', help='Показать план без вызовов API')
    all_parser.add_argument(
        '--stage',
        choices=['discovery', 'translation', 'proofreading', 'global_proofreading'],
        default=None,
        help='Принудительно перезапустить с указанного этапа'
    )
    docx_group2 = all_parser.add_mutually_exclusive_group()
    docx_group2.add_argument('--docx', action='store_true', dest='docx', help='Конвертировать в .docx')
    docx_group2.add_argument('--no-docx', action='store_true', dest='no_docx', help='Не конвертировать в .docx')
    epub_group2 = all_parser.add_mutually_exclusive_group()
    epub_group2.add_argument('--epub', action='store_true', dest='epub', help='Конвертировать в .epub')
    epub_group2.add_argument('--no-epub', action='store_true', dest='no_epub', help='Не конвертировать в .epub')

    # --- glossary ---
    gl_parser = subparsers.add_parser('glossary', help='Управление глоссарием')
    gl_sub = gl_parser.add_subparsers(dest='glossary_command', required=True)

    export_p = gl_sub.add_parser('export', help='Экспорт глоссария в TSV')
    export_p.add_argument('--output', '-o', type=str, help='Путь к файлу (по умолчанию stdout)')

    import_p = gl_sub.add_parser('import', help='Импорт глоссария из TSV')
    import_p.add_argument('file', type=str, help='Путь к TSV-файлу')

    gl_sub.add_parser('list', help='Показать все термины')

    # --- status ---
    subparsers.add_parser('status', help='Показать детальный статус серии')

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        # No subcommand — launch TUI
        try:
            from book_translator.textual_app import BookTranslatorApp
            app = BookTranslatorApp()
            app.run()
        except ImportError:
            parser.print_help()
            raise SystemExit(1)
        return

    if args.command == 'init':
        from book_translator.commands.init_cmd import run_init
        run_init(args)
    elif args.command == 'translate':
        raise SystemExit(
            "Перевод через CLI удален. Используйте Textual-интерфейс: `book-translator`."
        )
    elif args.command == 'translate-all':
        raise SystemExit(
            "Пакетный перевод через CLI удален. Используйте Textual-интерфейс: `book-translator`."
        )
    elif args.command == 'glossary':
        from book_translator.commands.glossary_cmd import run_glossary
        run_glossary(args)
    elif args.command == 'status':
        from book_translator.commands.status_cmd import run_status
        run_status(args)
