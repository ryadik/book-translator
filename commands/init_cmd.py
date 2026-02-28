from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from discovery import MARKER_FILE
from db import init_glossary_db

TOML_TEMPLATE = '''[series]
name = "{name}"
source_lang = "{source_lang}"
target_lang = "{target_lang}"

[gemini_cli]
model = "gemini-2.5-pro"

[splitter]
target_chunk_size = 600
max_part_chars = 800
min_chunk_size = 300

[workers]
max_concurrent = 50
'''

WORLD_INFO_TEMPLATE = '''# Информация о мире

## Сеттинг
(Опишите сеттинг произведения)

## Главные персонажи
(Перечислите главных персонажей с краткими описаниями)
'''

STYLE_GUIDE_TEMPLATE = '''# Стайлгайд перевода

## Общие правила
- Сохраняйте японские суффиксы обращения (-сан, -кун, -тян)
- Используйте «ёлочки» для прямой речи
'''

def run_init(args):
    series_dir = Path.cwd() / args.name
    
    if series_dir.exists():
        print(f"Ошибка: Директория '{args.name}' уже существует.")
        raise SystemExit(1)
    
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
    (series_dir / 'style_guide.md').write_text(STYLE_GUIDE_TEMPLATE, encoding='utf-8')
    
    # Create prompts directory (empty — user places overrides here)
    (series_dir / 'prompts').mkdir()
    
    # Initialize glossary database
    init_glossary_db(series_dir / 'glossary.db')
    
    # Create volume-01 scaffold
    vol1 = series_dir / 'volume-01'
    (vol1 / 'source').mkdir(parents=True)
    (vol1 / 'output').mkdir()
    
    print(f"✅ Серия '{args.name}' создана успешно!")
    print(f"""
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
