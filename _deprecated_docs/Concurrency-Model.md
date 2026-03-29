# Concurrency Model

## Реальная модель исполнения

Текущая реализация использует:

- `ThreadPoolExecutor` для конкурентного запуска задач по чанкам;
- один общий `RateLimiter`;
- один subprocess `gemini` на один worker-вызов;
- один lock-файл на главу.

`ASSUMPTION`: термин "multiprocessing" в описании проекта относится к множеству внешних процессов `gemini`, а не к Python `multiprocessing`.

## Где используется конкурентность

| Участок | Механизм |
| --- | --- |
| discovery | `ThreadPoolExecutor(max_workers=max_concurrent)` |
| translation | `ThreadPoolExecutor(max_workers=max_concurrent)` |
| proofreading | `ThreadPoolExecutor(max_workers=max_concurrent)` |
| global proofreading | без пула, один вызов |

## Ограничение RPS

`RateLimiter`:

- thread-safe;
- вычисляет минимальный интервал `1 / max_rps`;
- обновляет `last_call_time` под lock;
- sleep выполняет вне lock, чтобы другие потоки могли планировать свой слот.

Следствие:

- subprocess-вызовы сериализуются по времени старта;
- число worker threads может быть большим, но фактическая частота вызова `gemini` ограничивается `max_rps`.

## Как избегаются конфликты

### Между независимыми главами

- отдельные lock-файлы на главу;
- отдельные записи `chapter_name` в `chunks.db`.

### Между worker-ами одной главы

- каждый worker обновляет только свой `(chapter_name, chunk_index)`;
- общий rate limiter защищает внешний API от burst;
- SQLite WAL лучше переносит параллельные операции чтения/записи.

## Где возможны race conditions

| Риск | Почему возможен | Текущая защита |
| --- | --- | --- |
| два запуска одной главы | параллельный старт из двух shell-сессий | lock-файл + проверка PID |
| потеря lock чужого run | старый run может удалить новый lock | `_release_chapter_lock()` проверяет `run_id` |
| гонка на статус чанка | два worker не должны трогать один и тот же chunk | оркестратор не создаёт дубликатов задач |
| массовое продвижение стадии при неожиданных статусах | часть чанков могла упасть | `promote_chapter_stage()` валидирует все статусы атомарно |

## Остаточные риски

- Thread pool и SQLite работают в одном процессе; внезапное убийство процесса оставит `*_in_progress` статусы, которые затем лечатся через `--resume`.
- Проверка PID через `os.kill(pid, 0)` не гарантирует, что PID по-прежнему принадлежит именно `book-translator`.
- В `run_translate_all()` тома и главы обрабатываются последовательно, поэтому межтомной параллельности нет.
