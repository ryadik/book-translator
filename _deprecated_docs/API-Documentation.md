# API Documentation

## 4.1 CLI API

### `book-translator init`

**Синтаксис**

```bash
book-translator init <name> [--source-lang <code>] [--target-lang <code>]
```

| Параметр | Тип | Default | Описание |
| --- | --- | --- | --- |
| `name` | `str` | нет | имя директории серии и `series.name` |
| `--source-lang` | `str` | `ja` | исходный язык |
| `--target-lang` | `str` | `ru` | целевой язык |

**Side effects**

- создаёт новую директорию серии относительно `cwd`;
- пишет `book-translator.toml`, `world_info.md`, `style_guide.md`;
- создаёт `prompts/`, `volume-01/source`, `volume-01/output`;
- инициализирует `glossary.db`.

**Ошибки**

- `SystemExit(1)`, если директория уже существует.

### `book-translator translate`

**Синтаксис**

```bash
book-translator translate <chapter_file_or_source_dir> [flags]
```

| Флаг | Тип | Default | Описание |
| --- | --- | --- | --- |
| `chapter_file` | `str` | нет | путь к главе или каталогу `source/` |
| `--debug` | flag | `False` | включает запись debug-логов в `.state/logs` |
| `--resume` | flag | `False` | переводит failed/in_progress обратно в pending |
| `--force` | flag | `False` | очищает состояние главы и артефакты |
| `--dry-run` | flag | `False` | печатает план без вызовов `gemini` |
| `--stage` | enum | `None` | принудительный reset на этап |
| `--docx` | flag | `False` | авто-конвертация в `.docx` |
| `--no-docx` | flag | `False` | запрет конвертации в `.docx` |
| `--epub` | flag | `False` | авто-конвертация в `.epub` |
| `--no-epub` | flag | `False` | запрет конвертации в `.epub` |

**Маршрутизация**

- если путь указывает на файл, вызывается `_translate_file()`;
- если путь указывает на директорию, вызывается `_translate_directory()`;
- если путь не существует, процесс завершается с `SystemExit(1)`.

### `book-translator translate-all`

**Синтаксис**

```bash
book-translator translate-all [flags]
```

Флаги совпадают с `translate`, кроме отсутствия positional path.

**Поведение**

- находит все поддиректории серии, содержащие `source/`;
- сортирует их по имени;
- для каждого тома вызывает `_translate_directory(series_root, volume/source, args)`.

**Ошибка**

- `SystemExit(1)`, если не найден ни один том.

### `book-translator glossary export`

```bash
book-translator glossary export [--output <path>]
```

| Параметр | Тип | Default | Описание |
| --- | --- | --- | --- |
| `--output`, `-o` | `str | None` | `None` | путь для TSV; при `None` печать в stdout |

### `book-translator glossary import`

```bash
book-translator glossary import <file>
```

| Параметр | Тип | Default | Описание |
| --- | --- | --- | --- |
| `file` | `str` | нет | путь к TSV |

### `book-translator glossary list`

Печатает все термины текущей языковой пары.

### `book-translator status`

Показывает:

- серию, языки, модель;
- число терминов в глоссарии;
- по каждому тому таблицу с главами, этапом, количеством done, total и failed.

## 4.2 Internal API

### Модули уровня CLI

| Модуль | Назначение | Основные зависимости | Побочные эффекты |
| --- | --- | --- | --- |
| `cli.py` | парсер и диспетчер подкоманд | `argparse`, `commands.*` | импортирует и вызывает команды |
| `commands/init_cmd.py` | создание серии | `discovery`, `db` | создаёт каталоги и файлы |
| `commands/translate_cmd.py` | маршрутизация translate/translate-all | `find_series_root`, `orchestrator` | печать в stdout/stderr, `SystemExit` |
| `commands/glossary_cmd.py` | экспорт/импорт/просмотр глоссария | `glossary_manager`, `db` | файловый I/O TSV |
| `commands/status_cmd.py` | rich-таблица статуса | `db`, `rich` | печать в консоль |

### Модули уровня pipeline

| Модуль | Назначение | Основные зависимости | Побочные эффекты |
| --- | --- | --- | --- |
| `orchestrator.py` | сквозной pipeline главы | почти все остальные модули | БД, файлы, subprocess, интерактивный ввод |
| `llm_runner.py` | надёжный запуск `gemini` | `subprocess`, `tenacity`, `RateLimiter` | запускает внешний процесс |
| `chapter_splitter.py` | разбиение главы на чанки | `re`, logger | читает файл главы |
| `term_collector.py` | сбор и утверждение новых терминов | `parse_llm_json`, `glossary_manager` | пишет TSV, требует TTY |
| `proofreader.py` | применение JSON diff | `copy` | не пишет на диск сам по себе |

### Модули инфраструктуры

| Модуль | Назначение |
| --- | --- |
| `db.py` | слой SQLite |
| `discovery.py` | поиск корня серии и загрузка конфигурации |
| `path_resolver.py` | централизованная адресация путей |
| `languages.py` | имена языков и типографические правила |
| `glossary_manager.py` | TSV import/export |
| `logger.py` | rich/json логирование |
| `rate_limiter.py` | thread-safe ограничение RPS |
| `utils.py` | JSON parsing и поиск `.tool-versions` |
| `default_prompts.py` | загрузка bundled prompts |
| `convert_to_docx.py` | TXT -> DOCX |
| `convert_to_epub.py` | TXT -> EPUB |
| `tui.py` | общий `Console` и progress builder |
| `exceptions.py` | доменные исключения |

Подробные контракты всех файлов и функций см. в [Codebase Reference](Codebase-Reference.md).
