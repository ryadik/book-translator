import argparse
import sys
from pathlib import Path

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='book-translator',
        description='CLI для перевода ранобэ с использованием gemini-cli'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # --- init ---
    init_parser = subparsers.add_parser('init', help='Создать новую серию')
    init_parser.add_argument('name', type=str, help='Название серии')
    init_parser.add_argument('--source-lang', default='ja', help='Исходный язык (ISO 639-1)')
    init_parser.add_argument('--target-lang', default='ru', help='Целевой язык (ISO 639-1)')
    
    # --- translate ---
    tr_parser = subparsers.add_parser('translate', help='Перевести главу')
    tr_parser.add_argument('chapter_file', type=str, help='Путь к файлу главы (volume/source/chapter.txt)')
    tr_parser.add_argument('--debug', action='store_true', help='Сохранить рабочую директорию')
    tr_parser.add_argument('--resume', action='store_true', help='Возобновить прерванный перевод')
    tr_parser.add_argument('--force', action='store_true', help='Очистить состояние и начать заново')
    
    # --- glossary ---
    gl_parser = subparsers.add_parser('glossary', help='Управление глоссарием')
    gl_sub = gl_parser.add_subparsers(dest='glossary_command', required=True)
    
    export_p = gl_sub.add_parser('export', help='Экспорт глоссария в TSV')
    export_p.add_argument('--output', '-o', type=str, help='Путь к файлу (по умолчанию stdout)')
    
    import_p = gl_sub.add_parser('import', help='Импорт глоссария из TSV')
    import_p.add_argument('file', type=str, help='Путь к TSV-файлу')
    
    gl_sub.add_parser('list', help='Показать все термины')
    
    # --- status ---
    subparsers.add_parser('status', help='Показать статус серии')
    
    return parser

def main():
    parser = build_parser()
    args = parser.parse_args()
    
    if args.command == 'init':
        from book_translator.commands.init_cmd import run_init
        run_init(args)
    elif args.command == 'translate':
        from book_translator.commands.translate_cmd import run_translate
        run_translate(args)
    elif args.command == 'glossary':
        from book_translator.commands.glossary_cmd import run_glossary
        run_glossary(args)
    elif args.command == 'status':
        from book_translator.commands.status_cmd import run_status
        run_status(args)
