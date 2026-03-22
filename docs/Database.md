# Database

## Обзор

Система использует две независимые SQLite БД.

| БД | Путь | Область | Версия схемы |
| --- | --- | --- | --- |
| `glossary.db` | `series_root/glossary.db` | вся серия | `1` |
| `chunks.db` | `volume-XX/.state/chunks.db` | один том | `2` |

Обе БД открываются через `db.connection()` c:

- `timeout=30`
- `row_factory = sqlite3.Row`
- `PRAGMA foreign_keys = ON`
- `PRAGMA journal_mode = WAL` для реального файла

## Схема `glossary.db`

### Таблица `glossary`

| Колонка | Тип | Null | Default | Значение |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | no | autoincrement | surrogate key |
| `term_source` | `TEXT` | no | none | термин в исходном языке |
| `term_target` | `TEXT` | no | none | утверждённый перевод |
| `source_lang` | `TEXT` | no | `'ja'` | ISO 639-1 исходного языка |
| `target_lang` | `TEXT` | no | `'ru'` | ISO 639-1 целевого языка |
| `comment` | `TEXT` | yes | `''` | комментарий к термину |
| `created_at` | `TEXT` | yes | `datetime('now')` | метка создания записи |

### Ограничения

- `UNIQUE(term_source, source_lang, target_lang)`

### Жизненный цикл записи

1. `init_glossary_db()` создаёт таблицу.
2. `add_term()` использует `INSERT OR REPLACE`.
3. `get_terms()` читает термины по языковой паре.
4. `import_tsv()` может массово пополнять БД.

### Консистентность

- одна комбинация исходного термина и языковой пары всегда хранится как одна запись;
- `REPLACE` означает полную замену строки, а не merge отдельных полей.

## Схема `chunks.db`

### Таблица `chunks`

| Колонка | Тип | Null | Default | Значение |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | no | autoincrement | surrogate key |
| `chapter_name` | `TEXT` | no | none | stem файла главы |
| `chunk_index` | `INTEGER` | no | none | индекс чанка |
| `content_source` | `TEXT` | yes | none | исходный текст чанка |
| `content_target` | `TEXT` | yes | none | перевод или результат вычитки |
| `status` | `TEXT` | no | `discovery_pending` | текущий статус чанка |
| `updated_at` | `TEXT` | yes | `datetime('now')` | последняя модификация |

### Ограничения

- `UNIQUE(chapter_name, chunk_index)`

### Таблица `chapter_state`

| Колонка | Тип | Null | Default | Значение |
| --- | --- | --- | --- | --- |
| `chapter_name` | `TEXT` | no | none | первичный ключ главы |
| `pipeline_stage` | `TEXT` | yes | none | текущий этап pipeline |
| `updated_at` | `TEXT` | yes | `datetime('now')` | последняя модификация |

## Статусы чанков

| Статус | Кто устанавливает | Смысл |
| --- | --- | --- |
| `discovery_pending` | chunking/reset/resume | чанк ждёт discovery |
| `discovery_in_progress` | `_run_single_worker` | сейчас выполняется discovery |
| `discovery_done` | `_run_single_worker` | discovery успешно завершён |
| `discovery_failed` | `_run_single_worker` | discovery не завершился |
| `translation_pending` | `promote_chapter_stage`/reset/resume | ждёт перевода |
| `translation_in_progress` | `_run_single_worker` | сейчас переводится |
| `translation_done` | `_run_single_worker` | перевод получен и сохранён |
| `translation_failed` | `_run_single_worker` | перевод не завершился |
| `reading_pending` | `promote_chapter_stage`/reset/resume | ждёт вычитки |
| `reading_in_progress` | `_run_single_worker` | сейчас вычитывается |
| `reading_done` | `_run_single_worker` или global proofreading | локальная/глобальная вычитка завершена |
| `reading_failed` | `_run_single_worker` | локальная вычитка не завершилась |

## Жизненный цикл записи `chunks`

1. `add_chunk()` вставляет чанк после splitter.
2. `update_chunk_status()` меняет только статус.
3. `update_chunk_content()` меняет перевод и статус.
4. `batch_update_chunks_content()` массово обновляет несколько чанков после global proofreading.
5. `clear_chapter()` удаляет все чанки главы.

## Жизненный цикл записи `chapter_state`

1. до начала pipeline запись может отсутствовать;
2. `promote_chapter_stage()` или `set_chapter_stage()` создаёт/обновляет запись;
3. `reset_chapter_stage()` откатывает этап и синхронно меняет статусы чанков;
4. `clear_chapter_state()` удаляет только запись о стадии.

## Атомарность

- `promote_chapter_stage()` проверяет, что все статусы главы входят в ожидаемое множество;
- затем при необходимости массово меняет статусы;
- затем обновляет `chapter_state`;
- всё это происходит в одной SQLite-транзакции.

## Потенциальные риски консистентности

- `INSERT OR REPLACE` в `add_term()` и `add_chunk()` создаёт новую строку с новым `id`; если внешний код когда-нибудь начнёт ссылаться на `id`, поведение будет неочевидным.
- Нет отдельного enum-constraint для `status` и `pipeline_stage`; допустимые значения гарантируются только кодом Python.
- `batch_update_chunks_content()` не проверяет существование чанка до обновления.
