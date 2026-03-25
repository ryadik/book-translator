# Codebase Reference

Документ перечисляет каждый файл из `src/book_translator` и связанные статические ресурсы. Для каждой функции указан фактический контракт.

## `src/book_translator/__init__.py`

- Назначение: маркер Python-пакета.
- Публичные символы: отсутствуют.
- Side effects: отсутствуют.

## `src/book_translator/exceptions.py`

### `TranslationLockedError`

- Где: `exceptions.py`
- Что делает: доменное исключение для конфликта lock-файла главы.
- Бросается:
  - `_acquire_chapter_lock()` при живом процессе-владельце lock.
- Кем перехватывается:
  - `commands.translate_cmd._translate_file()`
  - `orchestrator.run_translation_process()` пробрасывает дальше без преобразования.

## `src/book_translator/cli.py`

### `build_parser() -> argparse.ArgumentParser`

- Что делает: создаёт корневой CLI parser и все подкоманды.
- Вход: отсутствует.
- Выход: объект `ArgumentParser`.
- Side effects: нет.
- Ошибки: явных нет.
- Зависимости: `argparse`.
- Используется: `main()`, тесты CLI.

### `main() -> None`

- Что делает: парсит CLI-аргументы и диспетчеризует команду.
- Вход: `sys.argv`.
- Выход: `None`.
- Side effects:
  - импортирует соответствующий модуль команды лениво;
  - вызывает `run_init`, `run_translate`, `run_translate_all`, `run_glossary`, `run_status`.
- Ошибки:
  - ошибки парсинга `argparse` завершают процесс;
  - любые исключения команд управляются уже внутри команд.

## `src/book_translator/commands/__init__.py`

- Назначение: namespace package для подкоманд.
- Содержимое: пустой файл.

## `src/book_translator/commands/init_cmd.py`

### Константы

- `TOML_TEMPLATE`: шаблон `book-translator.toml`.
- `WORLD_INFO_TEMPLATE`: шаблон `world_info.md`.
- `STYLE_GUIDE_TEMPLATE`: fallback style guide при отсутствии bundled-файла.

### `_find_bundled_style_guide(source_lang: str, target_lang: str) -> Path | None`

- Что делает: ищет bundled style guide сначала по имени `<source>_<target>.md`, затем `default.md`.
- Вход:
  - `source_lang`: код исходного языка.
  - `target_lang`: код целевого языка.
- Выход:
  - `Path` к существующему bundled-файлу;
  - `None`, если файл не удалось резолвить.
- Side effects: нет.
- Ошибки:
  - внутренние `TypeError`/`FileNotFoundError` подавляются и логируются в debug.
- Зависимости: `importlib.resources`, `Path`.

### `run_init(args) -> None`

- Что делает: создаёт новую серию в текущей директории.
- Вход:
  - `args.name`
  - `args.source_lang`
  - `args.target_lang`
- Выход: `None`.
- Side effects:
  - создаёт каталог серии относительно `cwd`;
  - пишет TOML и markdown-файлы;
  - создаёт `prompts/`, `volume-01/source`, `volume-01/output`;
  - инициализирует `glossary.db`;
  - печатает инструкцию пользователю.
- Ошибки:
  - `SystemExit(1)` если директория уже существует;
  - файловые ошибки не перехватываются локально.
- Идемпотентность: нет, повторный запуск на ту же директорию запрещён.

## `src/book_translator/commands/translate_cmd.py`

### `run_translate(args) -> None`

- Что делает: находит корень серии и маршрутизирует перевод файла или каталога.
- Вход:
  - `args.chapter_file`
  - флаги translate-команды.
- Выход: `None`.
- Side effects:
  - резолвит путь относительно `cwd`;
  - вызывает `_translate_directory()` или `_translate_file()`;
  - печатает ошибки.
- Ошибки:
  - `SystemExit(1)` для отсутствующего пути.

### `_translate_file(series_root: Path, chapter_path: Path, args) -> None`

- Что делает: нормализует флаги docx/epub/stage/dry-run и вызывает оркестратор для одной главы.
- Вход:
  - `series_root`
  - `chapter_path`
  - `args.debug`, `args.resume`, `args.force`, `args.docx`, `args.no_docx`, `args.epub`, `args.no_epub`, `args.stage`, `args.dry_run`
- Выход: `None`.
- Side effects: вызывает `orchestrator.run_translation_process()`.
- Ошибки:
  - `TranslationLockedError` преобразуется в `SystemExit(1)` с печатью сообщения;
  - любое другое исключение преобразуется в `SystemExit(1)` как критическая ошибка.

### `run_translate_all(args) -> None`

- Что делает: перечисляет все тома серии и запускает перевод всех глав.
- Вход: флаги translate-all.
- Выход: `None`.
- Side effects:
  - читает директории серии;
  - печатает найденные тома;
  - последовательно вызывает `_translate_directory()`.
- Ошибки:
  - `SystemExit(1)` при отсутствии томов.

### `_translate_directory(series_root: Path, source_dir: Path, args) -> None`

- Что делает: находит все `.txt` в `source_dir`, сортирует и запускает перевод каждого.
- Вход:
  - `series_root`
  - `source_dir`
  - `args`
- Выход: `None`.
- Side effects:
  - печать списка файлов и прогресса;
  - вызывает `_translate_file()` для каждого `.txt`;
  - при `SystemExit(1)` от конкретной главы с lock-проблемой печатает "Пропуск" и идёт дальше.
- Ошибки:
  - `SystemExit(1)` если в каталоге нет `.txt`.

## `src/book_translator/commands/glossary_cmd.py`

### `run_glossary(args) -> None`

- Что делает: управляет глобальным глоссарием текущей серии.
- Вход:
  - `args.glossary_command`
  - `args.output` или `args.file`
- Выход: `None`.
- Side effects:
  - ищет корень серии;
  - читает конфиг;
  - экспортирует TSV в stdout или файл;
  - импортирует TSV в `glossary.db`;
  - печатает список терминов в stdout.
- Ошибки:
  - `SystemExit(1)` при отсутствии импортируемого файла.

## `src/book_translator/commands/status_cmd.py`

### `run_status(args) -> None`

- Что делает: выводит детальный статус серии и томов через Rich.
- Вход: формально `args`, фактически не используется.
- Выход: `None`.
- Side effects:
  - читает конфиг, глоссарий, `chunks.db`;
  - печатает rich-таблицы.
- Особенности:
  - `Done` считает только чанки со статусом `reading_done`;
  - если БД тома отсутствует, том считается "не начат".

## `src/book_translator/discovery.py`

### `MARKER_FILE`

- Значение: `book-translator.toml`.

### `find_series_root(start_dir: Path | None = None) -> Path`

- Что делает: поднимается вверх по каталогам до первого найденного `book-translator.toml`.
- Вход:
  - `start_dir`: стартовая директория; при `None` используется `Path.cwd()`.
- Выход: абсолютный `Path` корня серии.
- Side effects: нет.
- Ошибки:
  - `FileNotFoundError`, если marker не найден до корня ФС.
- Идемпотентность: да.

### `load_series_config(series_root: Path) -> dict`

- Что делает: читает TOML, применяет defaults, валидирует значения.
- Вход: `series_root`.
- Выход: словарь конфигурации.
- Side effects: файловое чтение.
- Ошибки:
  - `FileNotFoundError` при отсутствии TOML;
  - `ValueError` при отсутствии `[series]`, `series.name` или неверных значениях.
- Зависимости: `tomllib`, `_validate_config()`.

### `_validate_config(config: dict) -> None`

- Что делает: валидирует merged config.
- Проверяет:
  - язык как `[a-z]{2}`;
  - положительность и типы splitter/timeouts;
  - диапазоны `max_concurrent`, `max_rps`, `max_attempts`.
- Ошибки: `ValueError` на первом нарушении.

## `src/book_translator/path_resolver.py`

### `SeriesPaths`

- Поля:
  - `root`
  - `glossary_db`
  - `world_info`
  - `style_guide`

### `VolumePaths`

- Поля:
  - `volume_dir`
  - `source_dir`
  - `output_dir`
  - `state_dir`
  - `chunks_db`
  - `logs_dir`
  - `cache_dir`

### `resolve_volume_from_chapter(series_root: Path, chapter_path: Path) -> tuple`

- Что делает: извлекает `(volume_name, chapter_name)` из пути главы.
- Ограничения:
  - путь обязан соответствовать шаблону `{volume}/source/{chapter}.txt`;
  - файл обязан находиться внутри `series_root`.
- Ошибки:
  - `ValueError` при несоответствии шаблону или выходе за пределы серии.

### `get_series_paths(series_root: Path, volume_name: str | None = None) -> SeriesPaths`

- Что делает: резолвит глобальные пути и volume-level override для `world_info.md` и `style_guide.md`.
- Приоритет:
  1. `series_root/volume_name/world_info.md` или `style_guide.md`
  2. `series_root/world_info.md` или `style_guide.md`
  3. `None`

### `get_volume_paths(series_root: Path, volume_name: str) -> VolumePaths`

- Что делает: строит все пути тома без создания директорий.
- Side effects: нет.

### `ensure_volume_dirs(volume_paths: VolumePaths) -> None`

- Что делает: создаёт `source`, `output`, `.state`, `.state/logs`, `.state/cache`.
- Идемпотентность: да.

### `resolve_prompt(series_root: Path, prompt_name: str, bundled_prompts: dict[str, str]) -> str`

- Что делает: выбирает prompt override из `series_root/prompts/` или fallback из bundled dict.
- Ошибки:
  - `FileNotFoundError`, если prompt нет ни в override, ни в bundled dict.

## `src/book_translator/languages.py`

### `LANGUAGE_NAMES`

- Справочник ISO 639-1 -> английское имя языка для prompt.

### `TYPOGRAPHY_RULES`

- Справочник target language -> строка с типографическими правилами.
- В текущем коде подробно заполнен только `ru`.

### `get_language_name(code: str) -> str`

- Что делает: возвращает человекочитаемое имя языка или сам код при отсутствии в справочнике.

### `get_typography_rules(target_lang: str) -> str`

- Что делает: возвращает правила типографики или пустую строку.

## `src/book_translator/default_prompts.py`

### `_load(name: str) -> str`

- Что делает: читает bundled prompt из `data/prompts/<name>.txt`.
- Side effects: файловое чтение package resource.

### `PROMPTS`

- Содержит:
  - `translation`
  - `term_discovery`
  - `proofreading`
  - `global_proofreading`

## `src/book_translator/logger.py`

### `JsonFormatter.format(self, record) -> str`

- Что делает: сериализует лог-запись в JSON.
- Включает:
  - `timestamp`
  - `level`
  - `name`
  - `message`
  - `exc_info` при наличии traceback.

### `setup_loggers(log_dir: str, debug_mode: bool) -> None`

- Что делает: перенастраивает `system_logger`, `input_logger`, `output_logger`.
- Side effects:
  - очищает существующие handlers;
  - всегда добавляет Rich console handler;
  - в debug-режиме создаёт `system_output.log`, `workers_input.log`, `workers_output.log`.
- Риски:
  - повторный вызов перезаписывает file handlers;
  - при `debug_mode=False` input/output логи намеренно подавляются.

## `src/book_translator/tui.py`

### `console`

- Общий объект `rich.console.Console`.

### `create_progress() -> Progress`

- Что делает: возвращает стандартный progress bar с spinner/bar/progress/time columns.

## `src/book_translator/rate_limiter.py`

### `RateLimiter.__init__(self, max_rps: float)`

- Что делает: инициализирует limiter.
- Ошибки:
  - `ValueError`, если `max_rps <= 0`.

### `RateLimiter.__enter__(self)`

- Что делает: резервирует следующий слот запуска.
- Side effects:
  - может усыпить текущий поток на рассчитанное время.

### `RateLimiter.__exit__(...) -> None`

- Что делает: ничего.

## `src/book_translator/utils.py`

### `strip_code_fence(text: str) -> str`

- Что делает: убирает outer markdown fence вида ```json ... ``` или ``` ... ```.
- Ограничения:
  - убирает только внешний fence, не пытается парсить вложенные.

### `parse_llm_json(raw: str) -> Any`

- Что делает: извлекает JSON из stdout `gemini`.
- Поддерживает:
  - чистый JSON;
  - fenced JSON;
  - wrapper `{"response": "..."}`;
  - слегка повреждённый JSON через `json_repair`.
- Ошибки:
  - `ValueError`, если JSON не удаётся восстановить;
  - `ValueError`, если wrapper содержит пустой `response`.
- Side effects:
  - warning-лог при неудаче парсинга inner JSON.

### `find_tool_versions_dir() -> Path | None`

- Что делает: поднимается вверх от текущего файла в поисках `.tool-versions`.
- Используется: `llm_runner._get_subprocess_cwd()`.

## `src/book_translator/llm_runner.py`

### `_get_subprocess_cwd() -> Path | None`

- Что делает: кэширует директорию с `.tool-versions`, если она найдена.
- Использует `lru_cache(maxsize=1)`.

### `run_gemini(...) -> str`

- Что делает: запускает внешний бинарник `gemini`.
- Вход:
  - `prompt`
  - `model_name`
  - `output_format`
  - `rate_limiter`
  - `timeout`
  - `retry_attempts`
  - `retry_wait_min`
  - `retry_wait_max`
  - `worker_id`
  - `label`
- Выход: `stdout` subprocess.
- Side effects:
  - логирует prompt и output;
  - запускает subprocess;
  - передаёт prompt через stdin;
  - может менять `cwd` subprocess на каталог с `.tool-versions`.
- Ошибки:
  - `CalledProcessError`;
  - `TimeoutExpired`.
- Retry:
  - `tenacity.retry` на перечисленные ошибки.

## `src/book_translator/chapter_splitter.py`

### `split_chapter_intelligently(chapter_file_path, target_chars=3000, max_part_chars=5000, min_chunk_size=1) -> list[dict]`

- Что делает: разбивает главу на чанки по эвристикам blank line/scene marker/dialogue safety.
- Вход:
  - `chapter_file_path`: путь к главе;
  - `target_chars`: целевой размер чанка;
  - `max_part_chars`: жёсткий верхний предел;
  - `min_chunk_size`: минимальный размер чанка.
- Выход:
  - список `{"id": int, "text": str}`.
- Side effects:
  - читает файл;
  - пишет логи.
- Ошибки:
  - файловые ошибки чтения;
  - явных доменных исключений нет.
- Идемпотентность: да при неизменном файле и параметрах.
- Риски:
  - эвристики понимают только ограниченный набор сцен-маркеров и диалогового старта (`「`, `『`).

## `src/book_translator/glossary_manager.py`

### `export_tsv(db_path: Path, output: TextIO = None, source_lang='ja', target_lang='ru') -> int`

- Что делает: пишет глоссарий в TSV.
- Side effects:
  - запись в `output` или stdout.
- Выход:
  - число экспортированных терминов.

### `import_tsv(db_path: Path, tsv_path: Path, source_lang='ja', target_lang='ru') -> int`

- Что делает: читает TSV и upsert-ит термины в БД.
- Игнорирует:
  - строки `#...`;
  - пустые строки;
  - строки с < 2 колонками;
  - строки без source/target после trim.
- Выход: число импортированных строк.

### `generate_approval_tsv(terms: list[dict], output_path: Path) -> None`

- Что делает: генерирует TSV-буфер для ручного утверждения.
- Поддерживает ключи:
  - новые: `term_source`, `term_target`
  - legacy: `term_jp`, `term_ru`

## `src/book_translator/term_collector.py`

### `_parse_terms_from_data(data: Any) -> list[dict]`

- Что делает: нормализует parsed JSON в плоский список терминов.
- Поддерживает:
  - новый формат `[{source, target, comment}]`;
  - legacy dict categories `characters`, `terminology`, `expressions`.
- Выход:
  - список dict с ключами `source`, `target`, `comment`.

### `collect_terms_from_responses(raw_responses: list[str]) -> list[dict]`

- Что делает: парсит все discovery-ответы и дедуплицирует термины по `source`.
- Side effects:
  - warning/info логи.
- Ошибки:
  - собственные исключения подавляются, проблемный ответ просто пропускается.
- Риск:
  - дедупликация только по `source`; разные переводы одного source теряются.

### `approve_via_tsv(terms: list[dict], tsv_path: Path, glossary_db_path: Path, source_lang='ja', target_lang='ru')`

- Что делает: пишет TSV, ждёт редактирования пользователем и импортирует утверждённые термины.
- Side effects:
  - создаёт TSV-файл;
  - печатает инструкции;
  - блокируется на `input()`;
  - пишет в `glossary.db`.
- Ошибки:
  - `RuntimeError`, если stdin не TTY.
- Идемпотентность: частично; повторный импорт использует upsert.

## `src/book_translator/proofreader.py`

### `apply_diffs(chunks: list[dict[str, str | int]], diffs: list[dict[str, str | int]]) -> tuple[list[dict[str, str | int]], int, int]`

- Что делает: применяет список текстовых замен к chunk list по `chunk_index`.
- Условия применения diff:
  - есть `chunk_index`, `find`, `replace`;
  - `chunk_index` имеет тип `int`;
  - существует соответствующий чанк;
  - `find` встречается ровно один раз.
- Выход:
  - обновлённая копия списка чанков;
  - `applied_count`;
  - `skipped_count`.
- Side effects: нет, кроме логирования.
- Идемпотентность:
  - не гарантируется, если вызывать повторно на уже изменённом тексте.

## `src/book_translator/db.py`

### Константы

- `GLOSSARY_SCHEMA_VERSION = 1`
- `CHUNKS_SCHEMA_VERSION = 2`
- `VALID_STAGES = {'discovery', 'translation', 'proofreading', 'global_proofreading', 'complete'}`

### `connection(db_path: Path)`

- Что делает: context manager для SQLite connection в WAL mode.
- Side effects:
  - открывает и закрывает connection.

### `init_glossary_db(db_path: Path) -> None`

- Что делает: создаёт схему `glossary.db`, если `user_version == 0`.
- Идемпотентность: да.

### `init_chunks_db(db_path: Path) -> None`

- Что делает: создаёт/мигрирует схему `chunks.db` до версии 2.
- Идемпотентность: да.

### `add_term(...) -> None`

- Что делает: upsert термина.
- Side effects: запись в БД.

### `get_terms(...) -> list[dict[str, Any]]`

- Что делает: возвращает список терминов по языковой паре, отсортированный по `term_source`.

### `add_chunk(...) -> None`

- Что делает: upsert чанка.
- Риск:
  - `REPLACE` может перетирать существующие поля целиком.

### `get_chunks(db_path: Path, chapter_name: str) -> list[dict[str, Any]]`

- Что делает: возвращает все чанки главы по возрастанию `chunk_index`.

### `get_all_chapters(db_path: Path) -> list[str]`

- Что делает: возвращает все уникальные `chapter_name`.

### `update_chunk_status(...) -> None`

- Что делает: меняет только `status` и `updated_at`.

### `update_chunk_content(...) -> None`

- Что делает: меняет `content_target`, `status`, `updated_at`.

### `batch_update_chunks_content(db_path: Path, chapter_name: str, updates: list[dict]) -> None`

- Что делает: массово обновляет `content_target` и `status` нескольких чанков в одной транзакции.
- Ожидает ключи:
  - `chunk_index`
  - `content_target`
  - `status`

### `clear_chapter(db_path: Path, chapter_name: str) -> None`

- Что делает: удаляет все чанки и stage главы.

### `clear_chapter_state(db_path: Path, chapter_name: str) -> None`

- Что делает: удаляет только `chapter_state`.

### `get_chunk_status_counts(db_path: Path, chapter_name: str) -> dict[str, int]`

- Что делает: возвращает `status -> count`.

### `set_chapter_stage(db_path: Path, chapter_name: str, stage: str) -> None`

- Что делает: upsert текущего этапа главы.
- Ошибки: `ValueError` при неизвестном этапе.

### `get_chapter_stage(db_path: Path, chapter_name: str) -> str | None`

- Что делает: возвращает этап или `None`.

### `reset_chapter_stage(db_path: Path, chapter_name: str, to_stage: str, chunk_status: str) -> None`

- Что делает: массово выставляет всем чанкам один статус и записывает stage.
- Side effects: изменяет все чанки главы.

### `promote_chapter_stage(db_path: Path, chapter_name: str, next_stage: str, expected_statuses: set[str], status_mapping: dict[str, str] | None = None) -> None`

- Что делает: атомарно проверяет статусы, опционально ремапит их и продвигает главу.
- Ошибки:
  - `ValueError` при неверном `next_stage`;
  - `RuntimeError`, если чанков нет;
  - `RuntimeError`, если найден неожиданный статус.

## `src/book_translator/convert_to_docx.py`

### `convert_txt_to_docx(input_file: str | Path, output_file: str | Path) -> None`

- Что делает: конвертирует текстовый файл в DOCX.
- Логика:
  - читает весь текст;
  - нормализует 2+ переводов строк в двойной;
  - делит по пустым абзацам;
  - создаёт justified paragraphs.
- Ошибки:
  - `FileNotFoundError` при отсутствии input;
  - `OSError` при проблемах чтения/сохранения;
  - `ImportError` при отсутствии `python-docx`.

## `src/book_translator/convert_to_epub.py`

### `_EBOOKLIB_AVAILABLE`

- Флаг доступности пакета `ebooklib`.

### `convert_txt_to_epub(input_file: Path, output_file: Path, title: str, author: str = '', language: str = 'ru') -> None`

- Что делает: конвертирует текстовый файл в EPUB.
- Логика:
  - читает input;
  - делит текст на абзацы по двойному переводу строк;
  - строит один XHTML chapter;
  - пишет `.epub`.
- Side effects:
  - печатает сообщение об успехе.
- Ошибки:
  - `ImportError`;
  - `FileNotFoundError`.

## `src/book_translator/orchestrator.py`

### Вспомогательные функции

#### `_safe_chapter_name(chapter_name: str) -> str`

- Заменяет `/` и `\` на `_` для безопасных имён файлов.

#### `_chapter_lock_path(volume_paths: Any, chapter_name: str) -> Path`

- Возвращает путь lock-файла главы.

#### `_read_lock_metadata(lock_file: Path) -> dict[str, Any] | None`

- Читает JSON lock-файла.
- Возвращает `None` при любой ошибке чтения/парсинга.

#### `_acquire_chapter_lock(lock_file: Path, chapter_name: str, force: bool) -> dict[str, Any]`

- Создаёт lock-файл атомарно через режим `x`.
- При `force=True` удаляет существующий lock до захвата.
- При существующем lock с живым PID выбрасывает `TranslationLockedError`.
- При мёртвом PID удаляет stale lock и повторяет попытку.

#### `_release_chapter_lock(lock_file: Path, run_id: str) -> None`

- Снимает lock только если `run_id` совпадает.
- Если lock уже чужой, логирует warning и не удаляет его.

#### `_cleanup_chapter_artifacts(volume_paths: Any, chapter_name: str) -> None`

- Удаляет:
  - `cache/<chapter>_chunk_*.json`
  - `output/<chapter>.txt`
  - `output/<chapter>.docx`
  - `output/<chapter>.epub`
  - `pending_terms_<chapter>.tsv`

#### `_reset_in_progress_to_failed(chunks_db: Path, chapter_name: str) -> None`

- Превращает все `*_in_progress` в `*_failed`.

#### `_is_pid_alive(pid: int) -> bool`

- Проверяет наличие процесса через `os.kill(pid, 0)`.

### `WorkerConfig`

- Dataclass общего конфига worker-ов.
- Поля:
  - `volume_paths`
  - `model_name`
  - `chunks_db`
  - `chapter_name`
  - `rate_limiter`
  - `output_format`
  - `glossary_str`
  - `style_guide_str`
  - `world_info_str`
  - `typography_rules_str`
  - `target_lang_name`
  - `source_lang_name`
  - `worker_timeout`
  - `retry_attempts`
  - `retry_wait_min`
  - `retry_wait_max`

### `_run_single_worker(chunk, prompt_template, step_name, config, previous_context='') -> bool`

- Что делает: выполняет один chunk-job.
- Вход:
  - `chunk`: dict чанка из БД;
  - `prompt_template`;
  - `step_name`: `discovery`, `translation`, `reading`;
  - `config`: `WorkerConfig`;
  - `previous_context`.
- Выход:
  - `True` при успехе;
  - `False` при любой ошибке.
- Side effects:
  - обновляет статус чанка;
  - вызывает `run_gemini()`;
  - при discovery пишет cache JSON;
  - при translation/reading записывает `content_target`.
- Ошибки:
  - любые внутренние исключения перехватываются локально.
- Retry:
  - делегируется `run_gemini()`.
- Идемпотентность:
  - частично; повторный запуск может перезаписать `content_target`.

### `_run_global_proofreading(...) -> tuple[list[dict[str, Any]], bool]`

- Что делает: выполняет глобальную вычитку всей главы.
- Выход:
  - список чанков после применения diff;
  - `success` flag.
- Side effects:
  - вызывает `run_gemini()`;
  - пишет логи;
  - может обновить progress bar.
- Ошибки:
  - `CalledProcessError`, `TimeoutExpired`, `ValueError`, `Exception` перехватываются и преобразуются в `(chunks, False)`.

### `_run_workers_pooled(max_workers, chunks, prompt_template, step_name, config, contexts=None)`

- Что делает: конкурентно запускает `_run_single_worker()` для списка чанков.
- Выход: `bool` общего успеха.
- Side effects:
  - создаёт progress bar;
  - запускает `ThreadPoolExecutor`.

### `_STAGE_PENDING_STATUS`

- Маппинг reset-этапа в статус чанков:
  - `discovery -> discovery_pending`
  - `translation -> translation_pending`
  - `proofreading -> reading_pending`
  - `global_proofreading -> reading_pending`

### `run_translation_process(series_root: Path, chapter_path: Path, debug=False, resume=False, force=False, auto_docx=None, auto_epub=None, restart_stage=None, dry_run=False)`

- Что делает: полный жизненный цикл перевода одной главы.
- Вход:
  - `series_root`
  - `chapter_path`
  - `debug`
  - `resume`
  - `force`
  - `auto_docx`
  - `auto_epub`
  - `restart_stage`
  - `dry_run`
- Выход:
  - `None`.
- Основные side effects:
  - загрузка конфига;
  - создание директорий тома;
  - настройка логов;
  - инициализация БД;
  - захват/освобождение lock;
  - очистка артефактов;
  - chunking;
  - запись/чтение SQLite;
  - вызовы LLM;
  - интерактивный `input()` для термов и конвертации;
  - запись итоговых файлов.
- Ошибки:
  - `TranslationLockedError` пробрасывается;
  - прочие исключения логируются как critical и пробрасываются.
- Retry:
  - опосредованно через `run_gemini()`.
- Идемпотентность:
  - `dry_run` идемпотентен;
  - `resume` частично идемпотентен;
  - `force` разрушает состояние главы.
- Потенциальные риски:
  - отсутствие TTY ломает discovery при найденных терминах;
  - interactive prompt на DOCX/EPUB делает процесс неудобным для batch automation;
  - при несогласованной БД сборка намеренно аварийно завершается.

## Статические данные `src/book_translator/data/`

### `data/prompts/*.txt`

- `translation.txt`: базовый шаблон перевода чанка.
- `term_discovery.txt`: шаблон поиска терминов.
- `proofreading.txt`: шаблон локальной вычитки чанка.
- `global_proofreading.txt`: шаблон глобальной вычитки через JSON patches.
- Загружаются модулем `default_prompts.py`.

### `data/style_guides/*.md`

- `ja_ru.md`, `ko_ru.md`, `zh_ru.md`, `en_ru.md`: bundled style guides для конкретных пар.
- `default.md`: fallback style guide.
- Используются только на этапе `init`.

## Прочие файлы корня проекта

### `docs/style_guide_prompt_template.md`

- Назначение: вспомогательный prompt для генерации кастомного style guide.
- В runtime-коде напрямую не используется.

### `README.md`

- Назначение: пользовательское описание проекта.
- Важное замечание: содержит не все актуальные детали реализации.

### `CLAUDE.md`, `CHANGELOG.md`, `pyproject.toml`

- `CLAUDE.md`: вспомогательные инструкции разработки.
- `CHANGELOG.md`: журнал изменений.
- `pyproject.toml`: packaging, dependencies, entry point `book-translator`.
