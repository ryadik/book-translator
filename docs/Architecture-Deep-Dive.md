# Architecture Deep Dive

## Архитектурный стиль

Система построена как CLI-оркестратор с дисковым состоянием. Главные свойства:

- stateless worker-вызовы к внешнему `gemini`;
- stateful оркестрация через SQLite;
- файловая изоляция по серии и по тому;
- возобновление через чтение текущих статусов из БД;
- конкурентное исполнение чанков через thread pool.

## Поток данных

### 1. Discovery root

`commands/*` вызывают `discovery.find_series_root()`, который поднимается вверх по директориям до `book-translator.toml`.

### 2. Config loading

`discovery.load_series_config()`:

- читает TOML;
- проставляет defaults;
- валидирует значения;
- возвращает merged dict.

### 3. Path resolution

`path_resolver` строит:

- `SeriesPaths` для глобального контекста;
- `VolumePaths` для тома и его `.state`.

### 4. Runtime bootstrap

`run_translation_process()`:

- настраивает логи;
- инициализирует `chunks.db`;
- создаёт `RateLimiter`;
- берёт lock на главу.

### 5. Chunk lifecycle

```text
splitter -> add_chunk(..., discovery_pending)
discovery worker -> discovery_in_progress -> discovery_done / discovery_failed
promotion -> translation_pending
translation worker -> translation_in_progress -> translation_done / translation_failed
promotion -> reading_pending
proofreading worker -> reading_in_progress -> reading_done / reading_failed
global proofreading -> batch_update_chunks_content(..., reading_done)
promotion -> complete
assembly -> output text/docx/epub
```

## Взаимодействие этапов

### Discovery

- берёт `content_source`;
- ожидает JSON;
- сохраняет сырые ответы в cache-файлы;
- собирает термины;
- проводит ручное утверждение через TSV;
- только затем продвигает главу в `translation`.

### Translation

- берёт `content_source`;
- использует `previous_context` из предыдущего исходного чанка;
- записывает ответ в `content_target`;
- при полном успехе массово переводит статусы в `reading_pending`.

### Proofreading

- берёт `content_target` как входной текст;
- использует `previous_context` из предыдущего переведённого чанка;
- результат снова записывает в `content_target`.

### Global proofreading

- не работает по чанкам параллельно;
- агрегирует все чанки в один prompt;
- получает список diffs;
- применяет только однозначные правки.

## Источники контекста prompt

| Источник | Discovery | Translation | Proofreading | Global proofreading |
| --- | --- | --- | --- | --- |
| `text` | `content_source` | `content_source` | `content_target` | агрегированный список чанков |
| `glossary` | да | да | да | да |
| `style_guide` | да | да | да | да |
| `world_info` | да | да | да | нет в явной подстановке глобальной вычитки |
| `previous_context` | пусто | предыдущий `content_source` | предыдущий `content_target` | нет |
| `typography_rules` | да | да | да | нет |
| языковые имена | да | да | да | только `target_lang_name` |

## Жизненный цикл lock-файла

1. Путь вычисляется как `.state/.lock.<safe_chapter_name>`.
2. В файл записываются `pid`, `chapter_name`, `run_id`.
3. Если файл уже существует:
   - при живом PID выбрасывается `TranslationLockedError`;
   - при мёртвом PID файл удаляется и попытка повторяется.
4. В `finally` lock удаляется только если `run_id` совпадает.

## Фактическая схема SQLite

См. отдельную страницу [Database](Database.md). Ключевой момент: система использует две БД, а не одну:

- `glossary.db` на уровне серии;
- `chunks.db` на уровне тома.

## Bundled data

- `default_prompts.PROMPTS` загружает 4 prompt template файла из `src/book_translator/data/prompts/`.
- `commands.init_cmd._find_bundled_style_guide()` подбирает стиль по языковой паре из `src/book_translator/data/style_guides/`.

## Наблюдаемые расхождения с проектным описанием

- Текущая реализация не использует Python `multiprocessing`.
- TUI ограничен progress bar и rich-таблицами; интерактивное редактирование терминов вынесено в внешний TSV.
- В коде нет отдельного API-сервера; "API" здесь означает CLI + внутренний Python API.
