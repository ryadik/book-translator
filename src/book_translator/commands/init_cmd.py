import logging
import shutil
from importlib import resources
from pathlib import Path

_logger = logging.getLogger(__name__)

from book_translator.discovery import MARKER_FILE
from book_translator.db import init_glossary_db

TOML_TEMPLATE_GEMINI = '''[series]
name = "{name}"
source_lang = "{source_lang}"
target_lang = "{target_lang}"

# LLM backend: "gemini" (cloud) or "ollama" (local)
[llm]
backend = "gemini"

# Gemini model configuration
[gemini_cli]
model = "gemini-2.5-pro"

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

TOML_TEMPLATE_OLLAMA = '''[series]
name = "{name}"
source_lang = "{source_lang}"
target_lang = "{target_lang}"

# LLM backend: "ollama" (local inference via Ollama server)
[llm]
backend = "ollama"
ollama_url = "http://localhost:11434"

# Model for each pipeline stage — swap for other Ollama models as needed
[llm.models]
discovery = "qwen3:8b"             # fast model for term extraction
translation = "qwen3:30b-a3b"     # quality model for literary translation
proofreading = "qwen3:30b-a3b"    # quality model for per-chunk polish
global_proofreading = "qwen3:14b" # model for chapter-wide consistency pass

# Generation options (applied to all stages unless overridden below)
[llm.options]
temperature = 0.3
num_ctx = 8192  # context window; increase if prompts + glossary + text exceed this
think = false   # Qwen3 extended thinking; false = faster, no hidden reasoning tokens

# Per-stage temperature overrides
[llm.options.stage_temperature]
discovery = 0.1          # low temp for deterministic JSON extraction
translation = 0.4        # higher temp for creative literary output
proofreading = 0.3       # moderate temp for stylistic refinement
global_proofreading = 0.1 # low temp for consistent JSON diffs

[retry]
max_attempts = 3
wait_min_seconds = 4
wait_max_seconds = 10

[splitter]
target_chunk_size = 600
max_part_chars = 800
min_chunk_size = 300

# Ollama: low concurrency (local hardware), no external API rate limit
[workers]
max_concurrent = 3
max_rps = 100.0
'''

# Keep the old name as alias for backward compat
TOML_TEMPLATE = TOML_TEMPLATE_GEMINI

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
    backend = getattr(args, 'backend', 'gemini')
    template = TOML_TEMPLATE_OLLAMA if backend == 'ollama' else TOML_TEMPLATE_GEMINI
    toml_content = template.format(
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
    
    success(f"✅ Серия '{args.name}' создана успешно! (backend: {backend})")
    ollama_hint = (
        "\n  ⚠️  Ollama-шаги перед запуском:"
        "\n    1. Установите Ollama: https://ollama.com"
        "\n    2. ollama pull qwen3:8b"
        "\n    3. ollama pull qwen3:30b-a3b"
        "\n    4. ollama pull qwen3:14b"
    ) if backend == 'ollama' else ""
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
{ollama_hint}
Следующий шаг:
  1. Заполните world_info.md и style_guide.md
  2. Положите исходный текст в volume-01/source/
  3. cd {args.name} && book-translator
""")
