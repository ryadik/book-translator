# Error Handling and Retry

## Категории ошибок

### Временные ошибки

Считаются временными только:

- `subprocess.CalledProcessError`
- `subprocess.TimeoutExpired`

Именно на них `tenacity` делает retry внутри `llm_runner.run_gemini()`.

### Фатальные ошибки

- невалидный JSON от LLM для discovery/global proofreading;
- пустой stdout;
- ошибка записи cache/output;
- отсутствие TTY при необходимости подтверждать термины;
- несогласованность статусов при `promote_chapter_stage()`;
- попытка сборки главы не из `reading_done`.

## Стратегия retry

Параметры берутся из конфигурации:

- `retry.max_attempts`
- `retry.wait_min_seconds`
- `retry.wait_max_seconds`

Тип ожидания:

- `wait_exponential(multiplier=1, min=wait_min, max=wait_max)`

Поведение:

1. `run_gemini()` вызывает subprocess.
2. При `CalledProcessError` или `TimeoutExpired` ошибка логируется.
3. `tenacity` повторяет вызов до исчерпания лимита.
4. Если попытки закончились, исключение поднимается выше.
5. `_run_single_worker()` перехватывает исключение и переводит чанк в `*_failed`.

## Обработка ошибок по слоям

### Worker layer

`_run_single_worker()`:

- сначала ставит `*_in_progress`;
- при любом исключении логирует `critical`;
- выставляет `*_failed`;
- возвращает `False`.

### Stage layer

`_run_workers_pooled()`:

- собирает результаты future-ов;
- если хотя бы один worker вернул `False` или кинул исключение, возвращает `False`.

### Pipeline layer

`run_translation_process()`:

- при провале этапа вызывает `_reset_in_progress_to_failed()` и завершает run без дальнейших этапов;
- `TranslationLockedError` пробрасывается наружу;
- все прочие исключения логируются как критические и пробрасываются;
- `finally` всегда пытается снять lock.

## Идемпотентность и повторный запуск

| Операция | Идемпотентность |
| --- | --- |
| `init_glossary_db()` | да |
| `init_chunks_db()` | да |
| `ensure_volume_dirs()` | да |
| `add_term()` | условно да, через `REPLACE` |
| `add_chunk()` | условно да, через `REPLACE` |
| `--resume` | да, если уже известно, какие чанки были в progress/failed |
| `--force` | нет, это разрушающий reset состояния главы |

## Что считать дефектом документации/эксплуатации

- неизвестный статус чанка;
- незадокументированный prompt placeholder;
- неучтённый side effect записи в файл/БД;
- несоответствие между `chapter_state` и фактическими chunk statuses;
- запуск discovery в неинтерактивной среде без заранее заполненного глоссария.
