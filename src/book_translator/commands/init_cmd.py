import logging
import shutil
from importlib import resources
from pathlib import Path

_logger = logging.getLogger(__name__)

from book_translator.discovery import MARKER_FILE
from book_translator.db import init_glossary_db

TOML_TEMPLATE = '''[series]
name = "{name}"
source_lang = "{source_lang}"
target_lang = "{target_lang}"

[gemini_cli]
model = "gemini-2.5-pro"
worker_timeout_seconds = 120
proofreading_timeout_seconds = 300

[retry]
max_attempts = 3
wait_min_seconds = 4
wait_max_seconds = 10

[splitter]
target_chunk_size = 600
max_part_chars = 800
min_chunk_size = 300

[workers]
max_concurrent = 50
max_rps = 2.0
'''

WORLD_INFO_TEMPLATE = '''# Информация о мире

## Сеттинг
(Опишите сеттинг произведения)

## Главные персонажи
(Перечислите главных персонажей с краткими описаниями)
'''

STYLE_GUIDE_TEMPLATE = '''## Стайлгайд перевода

### 1. Пунктуация
- **Тире в диалогах:** Использовать оператор звука (`─`, U+2500).
- **Мысли и названия:** Кавычки-«ёлочки» (`«...»`).

### 2. Общие правила
- Литературный перевод, не дословный.
- Обязательно использовать букву «ё».
'''


def _find_bundled_style_guide(source_lang: str, target_lang: str) -> Path | None:
    """Find bundled style guide for the given language pair."""
    style_guides_ref = resources.files('book_translator') / 'data' / 'style_guides'
    for name in (f'{source_lang}_{target_lang}.md', 'default.md'):
        candidate = style_guides_ref / name
        try:
            path = Path(str(candidate))
            if path.is_file():
                return path
        except (TypeError, FileNotFoundError) as e:
            _logger.debug("Could not resolve bundled style guide '%s': %s", name, e)
    return None


def _print_info(message: str) -> None:
    print(message)


def _print_success(message: str) -> None:
    print(message)


def _raise_error(message: str) -> None:
    print(message)
    raise SystemExit(1)


def run_init(args, info_callback=None, success_callback=None, error_callback=None):
    info = info_callback or _print_info
    success = success_callback or _print_success
    error = error_callback or _raise_error

    series_dir = Path.cwd() / args.name

    if series_dir.exists():
        error(f"Ошибка: Директория '{args.name}' уже существует.")
    
    # Create directory structure
    series_dir.mkdir()
    
    # Write marker file (book-translator.toml)
    toml_content = TOML_TEMPLATE.format(
        name=args.name,
        source_lang=args.source_lang,
        target_lang=args.target_lang
    )
    (series_dir / MARKER_FILE).write_text(toml_content, encoding='utf-8')
    
    # Write template files
    (series_dir / 'world_info.md').write_text(WORLD_INFO_TEMPLATE, encoding='utf-8')
    bundled_guide = _find_bundled_style_guide(args.source_lang, args.target_lang)
    if bundled_guide:
        shutil.copy2(bundled_guide, series_dir / 'style_guide.md')
    else:
        (series_dir / 'style_guide.md').write_text(STYLE_GUIDE_TEMPLATE, encoding='utf-8')
    
    # Create prompts directory (empty — user places overrides here)
    (series_dir / 'prompts').mkdir()
    
    # Initialize glossary database
    init_glossary_db(series_dir / 'glossary.db')
    
    # Create volume-01 scaffold
    vol1 = series_dir / 'volume-01'
    (vol1 / 'source').mkdir(parents=True)
    (vol1 / 'output').mkdir()
    
    success(f"✅ Серия '{args.name}' создана успешно!")
    info(f"""
Структура:
  {args.name}/
  ├── book-translator.toml   ← настройки серии
  ├── world_info.md          ← контекст мира (заполните!)
  ├── style_guide.md         ← правила стиля
  ├── prompts/               ← кастомные промпты (опционально)
  ├── glossary.db            ← глоссарий серии
  └── volume-01/
      ├── source/             ← положите исходные .txt файлы сюда
      └── output/             ← переведённые файлы появятся здесь

Следующий шаг:
  1. Заполните world_info.md и style_guide.md
  2. Положите исходный текст в volume-01/source/
  3. cd {args.name} && book-translator translate volume-01/source/chapter.txt
""")
