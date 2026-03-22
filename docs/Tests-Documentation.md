# Tests Documentation

Документ покрывает каждый тестовый файл и каждый тест-кейс из `tests/`.

## `tests/__init__.py`

- Назначение: marker package.
- Тестов нет.

## `tests/test_cli.py`

### `test_parser_init`

- Что проверяет: `init` парсится, default языки `ja -> ru`.
- Зачем нужен: фиксирует контракт CLI по умолчанию.
- Какой баг ловит: случайное изменение defaults или имени positional аргумента.
- Не покрыто: исполнение `run_init`.

### `test_parser_translate`

- Проверяет: `translate` принимает путь файла и флаг `--debug`.
- Ловит баг: потеря positional `chapter_file` или rename флага.

### `test_parser_glossary_export`

- Проверяет: `glossary export --output`.

### `test_parser_glossary_import`

- Проверяет: `glossary import <file>`.

### `test_parser_glossary_list`

- Проверяет: `glossary list`.

### `test_parser_status`

- Проверяет: `status` как отдельная команда.

### `test_parser_no_command_fails`

- Проверяет: отсутствие subcommand вызывает `SystemExit`.
- Ловит баг: случайное снятие `required=True`.

### `test_parser_translate_resume_force`

- Проверяет: одновременно парсятся `--resume` и `--force`.

### `test_translate_defaults`

- Проверяет: флаги `debug/resume/force` по умолчанию `False`.

## `tests/test_init_cmd.py`

### `test_init_creates_full_structure`

- Проверяет: `run_init()` создаёт весь scaffold серии.
- Баг: неполный bootstrap проекта.

### `test_init_toml_is_valid`

- Проверяет: созданный TOML читается и содержит ожидаемые значения.

### `test_init_existing_dir_fails`

- Проверяет: повторная инициализация в существующий каталог запрещена.

### `test_init_glossary_db_initialized`

- Проверяет: `glossary.db` создаётся с `user_version == 1`.

### `test_init_world_info_not_empty`

- Проверяет: шаблон `world_info.md` не пустой.

### `test_init_style_guide_not_empty`

- Проверяет: `style_guide.md` не пустой.

### `test_init_toml_splitter_defaults`

- Проверяет: defaults блока `[splitter]`.

### `test_init_glossary_table_exists`

- Проверяет: в `glossary.db` реально существует таблица `glossary`.

### `test_init_series_dir_uses_cwd`

- Проверяет: серия создаётся относительно `cwd`, а не расположения скрипта.

### `test_init_prompts_dir_is_empty`

- Проверяет: `prompts/` создаётся пустым, без auto-copy prompts.

## `tests/test_discovery.py`

### `make_toml`

- Helper, не тест.

### `TestFindSeriesRoot.test_finds_from_root`

- Проверяет: корень серии определяется, если marker лежит в текущем каталоге.

### `test_finds_from_depth_1`

- Проверяет: поиск работает из `volume-01/`.

### `test_finds_from_depth_2`

- Проверяет: поиск работает из `volume-01/source/`.

### `test_finds_from_depth_3`

- Проверяет: поиск работает из произвольной глубины.

### `test_raises_when_not_found`

- Проверяет: выбрасывается `FileNotFoundError`.

### `test_raises_contains_init_hint`

- Проверяет: сообщение об ошибке содержит подсказку `book-translator init`.

### `test_first_found_wins_not_nested`

- Проверяет: при вложенных сериях побеждает ближайший marker.
- Ловит баг: ошибочный подъём к внешнему корню.

### `TestLoadSeriesConfig.*`

- `test_loads_minimal_config`: минимальный TOML загружается.
- `test_applies_default_source_lang`: default `source_lang`.
- `test_applies_default_target_lang`: default `target_lang`.
- `test_applies_default_model`: default model.
- `test_applies_default_splitter`: defaults splitter.
- `test_applies_default_workers`: default `max_concurrent`.
- `test_user_overrides_source_lang`: override `source_lang`.
- `test_user_overrides_model`: override model.
- `test_user_overrides_workers`: override worker count.
- `test_raises_missing_series_section`: требуется `[series]`.
- `test_raises_missing_series_name`: требуется `series.name`.
- `test_raises_missing_toml_file`: отсутствующий TOML даёт `FileNotFoundError`.

### `TestConfigValidation.*`

- `test_invalid_source_lang_raises`: плохой код языка source.
- `test_invalid_target_lang_raises`: плохой код языка target.
- `test_uppercase_lang_code_raises`: uppercase запрещён.
- `test_valid_lang_codes_pass`: корректные коды проходят.
- `test_negative_chunk_size_raises`: отрицательный chunk size запрещён.
- `test_zero_max_part_chars_raises`: ноль для `max_part_chars` запрещён.
- `test_float_chunk_size_raises`: float для chunk size запрещён.
- `test_zero_max_concurrent_raises`: worker count > 0.
- `test_over_limit_max_concurrent_raises`: upper bound 200.
- `test_valid_max_concurrent_boundary`: граничное значение 1 работает.
- `test_zero_max_attempts_raises`: retry attempts > 0.
- `test_eleven_max_attempts_raises`: attempts <= 10.
- `test_valid_max_attempts`: корректный retry count.
- `test_negative_worker_timeout_raises`: timeout > 0.
- `test_zero_proofreading_timeout_raises`: proofreading timeout > 0.
- `test_valid_float_timeout_passes`: float timeout разрешён.

Покрытие файла:

- Хорошо покрыты defaults и validation.
- Не покрыты комбинации конфликтующих, но формально валидных параметров.

## `tests/test_path_resolver.py`

### `TestResolveVolumeFromChapter.*`

- `test_valid_path_returns_volume_and_chapter`: happy path.
- `test_stem_strips_extension`: `chapter_name` берётся как `stem`.
- `test_relative_path_resolved_from_series_root`: relative path support.
- `test_invalid_no_source_dir_raises`: требуется сегмент `source`.
- `test_invalid_flat_path_raises`: путь в корне серии недопустим.
- `test_path_outside_series_root_raises`: файл вне серии запрещён.
- `test_too_deep_path_raises`: лишняя вложенность запрещена.

### `TestGetSeriesPaths.*`

- Проверяет:
  - `glossary.db` всегда на уровне серии;
  - `root.resolve()`;
  - `None` при отсутствии контекстных файлов;
  - чтение series-level world/style;
  - приоритет volume-level override;
  - fallback к series-level;
  - отсутствие volume override без `volume_name`.

### `TestGetVolumePaths.*`

- Проверяет корректное построение путей и отсутствие side effect создания директорий.

### `TestEnsureVolumeDirs.*`

- Проверяет создание всех нужных директорий и идемпотентность.

### `TestResolvePrompt.*`

- Проверяет:
  - приоритет series override;
  - fallback to bundled;
  - `FileNotFoundError` при отсутствии;
  - работа с пустым `prompts/`.

## `tests/test_db.py`

### `TestGlossaryInit.*`

- `test_creates_glossary_table`: таблица создаётся.
- `test_sets_schema_version`: версия схемы фиксируется.
- `test_idempotent_does_not_drop_data`: повторная инициализация не теряет данные.
- `test_creates_parent_dirs`: parent dirs создаются автоматически.

### `TestChunksInit.*`

- `test_creates_chunks_table`: таблица `chunks`.
- `test_sets_schema_version`: схема `chunks.db`.
- `test_idempotent`: повторный init не удаляет записи.

### `TestGlossaryOperations.*`

- `test_add_and_get_term`: basic insert/read.
- `test_get_terms_ordered_alphabetically`: сортировка.
- `test_add_term_upsert_updates_translation`: upsert semantics.
- `test_add_term_with_comment`: сохранение comment.
- `test_add_term_different_lang_pair`: разные языковые пары изолированы.
- `test_get_terms_filters_by_lang_pair`: default filter `ja -> ru`.

### `TestChunkOperations.*`

- `test_add_and_get_chunk`: базовая вставка чанка.
- `test_composite_key_prevents_collision`: `(chapter_name, chunk_index)` уникален.
- `test_get_chunks_ordered_by_index`: порядок по индексу.
- `test_get_chunks_only_returns_requested_chapter`: фильтрация по главе.
- `test_add_chunk_upsert`: upsert статуса чанка.
- `test_get_all_chapters`: выборка уникальных глав.
- `test_update_chunk_status`: обновление статуса.
- `test_update_chunk_status_preserves_content`: status update не трогает контент.
- `test_update_chunk_content`: обновление перевода и статуса.
- `test_get_empty_chapter_returns_empty_list`: пустой результат без ошибок.
- `test_clear_chapter_removes_only_target_chapter`: точечная очистка главы.

### `TestChapterState.*`

- `test_get_stage_default_is_none`: стартовое состояние.
- `test_set_and_get_stage`: запись stage.
- `test_set_stage_overwrites`: upsert chapter_state.
- `test_set_stage_different_chapters_isolated`: изоляция глав.
- `test_reset_chapter_stage`: rollback stage + chunk status.
- `test_clear_chapter_state_only_removes_stage`: данные чанков сохраняются.
- `test_get_chunk_status_counts`: агрегирование статусов.
- `test_promote_chapter_stage_updates_statuses_atomically`: happy path promotion.
- `test_promote_chapter_stage_rejects_unexpected_statuses`: защита от неконсистентных статусов.

Непокрыто:

- миграция legacy схемы `chunks v1 -> v2`;
- поведение `batch_update_chunks_content`.

## `tests/test_chapter_splitter.py`

- `test_split_basic`: базовое деление по пустым строкам.
- `test_split_returns_id_and_text_only`: контракт структуры чанка.
- `test_split_scene_marker`: сцена `---` является точкой разрыва.
- `test_split_dialogue_not_broken_before`: blank line перед диалогом не используется как граница.
- `test_split_single_chunk_short_file`: короткий файл остаётся одним чанком.
- `test_split_ids_are_sequential`: ID последовательны.
- `test_split_respects_min_chunk_size_on_natural_break`: слишком маленький хвост не отделяется.
- `test_split_merges_small_trailing_chunk_when_safe`: маленький финальный хвост приклеивается к предыдущему чанку.

Непокрыто:

- обработка маркера `[]`;
- поведение на бинарных/не-UTF8 файлах;
- экстремально большие файлы.

## `tests/test_term_collector.py`

- `test_collect_new_flat_array_format`: новый JSON format list.
- `test_collect_deduplicates_by_source`: дедупликация по `source`.
- `test_collect_skips_empty_strings`: пустые ответы пропускаются.
- `test_collect_empty_array_returns_empty`: `[]` корректно означает "нет терминов".
- `test_collect_empty_input_returns_empty`: пустой список входов.
- `test_collect_wrapper_with_empty_response_skipped`: wrapper с пустым `response` не ломает batch.
- `test_collect_backward_compat_old_category_format`: legacy format по-прежнему понимается.

Непокрыто:

- `approve_via_tsv()`;
- конфликтующие переводы одного source.

## `tests/test_glossary_manager.py`

- `test_export_tsv`: экспорт в TSV со строками и header.
- `test_import_tsv`: импорт из TSV.
- `test_import_tsv_skips_malformed`: malformed lines игнорируются.
- `test_export_import_roundtrip`: roundtrip экспорт/импорт сохраняет данные.
- `test_generate_approval_tsv`: буфер утверждения создаётся.
- `test_export_empty_glossary`: экспорт пустого глоссария всё равно пишет header.
- `test_import_empty_file`: пустой файл даёт 0 импортов.
- `test_export_tsv_stdout_default`: default output = stdout.
- `test_import_tsv_with_comment`: сохранение comment.
- `test_generate_approval_tsv_mixed_keys`: поддержка legacy/new keys.

Непокрыто:

- ошибки файловой системы;
- экранирование табов и переводов строк внутри полей.

## `tests/test_utils.py`

### `TestStripCodeFence.*`

- Проверяют снятие ` ```json `, ` ``` `, сохранение plain JSON и trim whitespace.

### `TestParseLlmJson.*`

- `test_plain_json_dict`: обычный dict JSON.
- `test_plain_json_list`: обычный list JSON.
- `test_with_json_code_fence`: fenced dict.
- `test_with_plain_code_fence`: generic fence.
- `test_gemini_cli_wrapper_dict`: wrapper `{"response": "..."}`
- `test_gemini_cli_wrapper_with_fence`: fenced inner JSON.
- `test_invalid_raises_value_error`: непарсибельный ответ падает.
- `test_empty_object`: `{}` допустим.
- `test_empty_list`: `[]` допустим.

### `TestParseLlmJsonWrapper.*`

- `test_wrapper_with_valid_inner_json`: inner dict.
- `test_wrapper_with_code_fenced_inner_json`: inner fenced dict.
- `test_wrapper_with_empty_response_raises`: пустой `response`.
- `test_wrapper_with_whitespace_response_raises`: пробельный `response`.
- `test_wrapper_with_invalid_inner_json_raises`: сломанный inner JSON.

Непокрыто:

- успешная ветка `json_repair`.

## `tests/test_rate_limiter.py`

### `worker`

- Helper для теста concurrent access.

### `test_rate_limiter`

- Проверяет: 10 вызовов при `2 RPS` занимают не менее `4.5s`.
- Зачем нужен: регрессия на thread-safe pacing.
- Непокрыто:
  - `ValueError` для `max_rps <= 0`;
  - поведение при очень высоком RPS.

## `tests/test_default_prompts.py`

- `test_all_four_prompts_exist`: все 4 prompt template загружены.
- `test_prompts_are_non_trivial`: prompts не пустые и достаточно большие.
- `test_translation_has_required_placeholders`: translation placeholders.
- `test_term_discovery_has_required_placeholders`: discovery placeholders.
- `test_prompts_dict_has_four_entries`: точное число entries.

Непокрыто:

- placeholders proofreading/global proofreading;
- корректность конкретного prompt-текста.

## `tests/test_proofreader.py`

- `test_apply_diffs_exact_match`: корректное применение diff и отсутствие мутации исходного списка.
- `test_apply_diffs_1based_index_not_off_by_one`: регрессия на 1-based `chunk_index`.
- `test_apply_diffs_zero_matches`: правка пропускается при отсутствии строки.
- `test_apply_diffs_multiple_matches`: правка пропускается при неоднозначном совпадении.
- `test_apply_diffs_invalid_index`: неверный индекс или тип индекса.
- `test_apply_diffs_missing_keys`: защита от неполных diff-объектов.
- `test_apply_diffs_multiple_diffs_same_chunk`: последовательное применение нескольких diff к одному чанку.

Непокрыто:

- non-string значения `find/replace`;
- очень большие chunk bodies.

## `tests/test_translate_cmd.py`

### Helpers

- `_base_args`: строит `Namespace` с default flags.
- `_make_series`: создаёт минимальную серию через `run_init`.

### `TestTranslateFileFlags.*`

- `test_no_docx_flag_passes_false`: `--no-docx -> auto_docx=False`.
- `test_docx_flag_passes_true`: `--docx -> auto_docx=True`.
- `test_no_docx_flags_passes_none`: отсутствие флагов -> `auto_docx=None`.
- `test_stage_flag_forwarded`: `--stage` проксируется как `restart_stage`.
- `test_dry_run_forwarded`: `--dry-run` проксируется.
- `test_locked_error_becomes_system_exit`: `TranslationLockedError` преобразуется в `SystemExit(1)`.

### `TestTranslateDirectory.*`

- `test_translates_all_txt_files`: все `.txt` переводятся.
- `test_ignores_non_txt_files`: `.md` и прочие игнорируются.
- `test_empty_directory_raises_system_exit`: пустой `source` запрещён.
- `test_files_processed_in_sorted_order`: детерминированный порядок файлов.

### `TestRunTranslateRouting.*`

- `test_routes_file_to_translate_file`: файл -> `_translate_file`.
- `test_routes_directory_to_translate_directory`: каталог -> `_translate_directory`.
- `test_nonexistent_path_raises_system_exit`: отсутствующий путь -> `SystemExit`.

### `TestRunTranslateAll.*`

- `test_translates_each_volume`: все тома обрабатываются.
- `test_no_volumes_raises_system_exit`: отсутствие томов -> ошибка.
- `test_volumes_processed_in_sorted_order`: детерминированный порядок томов.

Непокрыто:

- маршрутизация абсолютных vs relative путей с реальным `find_series_root`;
- флаги `--epub/--no-epub`.

## `tests/test_integration.py`

- `create_series`: helper.
- `test_full_init_to_status_flow`: `init -> glossary import -> status`.
- `test_walk_up_from_subdirectory`: интеграция `init` + `find_series_root` из `source/`.
- `test_walk_up_from_volume_dir`: то же из `volume-01/`.
- `test_no_series_root_error`: ошибка вне серии.
- `test_glossary_export_import_roundtrip`: данные реально переживают экспорт/редактирование/импорт.
- `test_volume_context_override`: томовой `world_info.md` перекрывает series-level.
- `test_glossary_list_command`: `glossary list` выполняется без исключения.
- `test_init_creates_valid_series_root`: серия после init пригодна для discovery/load config.
- `test_glossary_export_to_file`: `glossary export --output` пишет файл.

Непокрыто:

- полный pipeline с реальным `gemini`;
- checkpoint/resume на уровне интеграции.

## `tests/test_orchestrator.py`

### Structural/signature tests

- `test_run_translation_process_signature`: базовые параметры main entrypoint.
- `test_run_translation_process_default_args`: defaults `debug/resume/force`.
- `test_orchestrator_no_task_manager`: защитный тест после рефакторинга.
- `test_orchestrator_no_config_module`: защита от возврата старого config API.
- `test_orchestrator_has_discovery_import`: модуль discovery действительно импортирован.
- `test_orchestrator_has_path_resolver_import`: path_resolver импортирован.
- `test_orchestrator_has_default_prompts_import`: default_prompts импортирован.
- `test_orchestrator_uses_pathlib`: нет `os.path.join`.
- `test_orchestrator_no_hardcoded_prompts_open`: нет хардкода prompt paths.
- `test_orchestrator_no_hardcoded_style_guide`: нет старого хардкода style guide.
- `test_orchestrator_uses_content_source_not_content_jp`: регрессия на старые имена полей.
- `test_orchestrator_uses_content_target_not_content_ru`: регрессия на старые имена полей.

### Integration-style mocked pipeline

- `test_run_translation_process_lock_file_created`: lock удаляется даже после ошибки.
- `test_run_translation_process_chunks_db_created`: `chunks.db` создаётся до pipeline.
- `test_run_translation_process_chunks_added_to_db`: splitter output сохраняется в БД.
- `test_run_translation_process_exits_on_lock`: живой lock останавливает процесс.
- `test_run_translation_process_resume_also_respects_live_lock`: `--resume` не обходит lock.
- `test_run_translation_process_user_cancel`: отмена пользователя во время term confirmation аварийно останавливает run.
- `test_run_translation_process_output_file_created`: при `complete` и `reading_done` собирается итоговый файл.

### New parameter behavior

- `test_run_translation_process_signature_has_new_params`: наличие `auto_docx`, `restart_stage`, `dry_run`.
- `test_dry_run_makes_no_subprocess_calls`: `dry_run` не вызывает `subprocess.run`.
- `test_dry_run_returns_none`: `dry_run` не падает.
- `test_resume_with_empty_db_still_creates_chunks`: пустая БД при `resume` заново чанкится.
- `test_restart_stage_resets_db_state`: reset stage не оставляет систему без чанков.
- `test_global_proofreading_failure_does_not_mark_complete`: провал global proofreading не ставит `complete`.
- `test_auto_docx_false_skips_conversion`: нет DOCX конвертации.
- `test_auto_epub_false_skips_conversion`: нет EPUB конвертации.
- `test_auto_epub_true_calls_conversion`: EPUB конвертация вызывается с ожидаемым `title`.
- `test_run_translation_process_signature_has_auto_epub`: наличие `auto_epub`.
- `test_run_single_worker_signature`: старые flat-params удалены, используется `WorkerConfig`.
- `test_run_workers_pooled_signature`: то же для pooled runner.
- `test_global_proofreading_uses_configured_retry_values`: retry/timeouts пробрасываются в `run_gemini()`.

Непокрыто:

- успешный end-to-end discovery/translation/proofreading с реальным обновлением статусов без monkeypatch;
- `--force` cleanup;
- поведение `_release_chapter_lock()` при чужом `run_id`;
- прямые тесты `_run_single_worker()`.

## Итог по покрытию

Хорошо покрыты:

- CLI parsing;
- discovery/config/path resolution;
- SQLite слой;
- splitter, proofreader, utils;
- маршрутизация translate-команд;
- структурные свойства orchestrator после рефакторинга.

Слабо покрыты:

- реальные subprocess-вызовы `gemini`;
- интерактивные ветки с TSV подтверждением и вопросами DOCX/EPUB;
- bundled prompt semantics;
- негативные сценарии файловой системы и частичной порчи БД.
