# АУДИТ ПРОЕКТА BOOK-TRANSLATOR

Дата: 2026-03-21
Аудитор: Antigravity (Deep Analysis Mode)

---

## 1. 🔴 CRITICAL — НЕМЕДЛЕННО ИСПРАВИТЬ

---

### C-01. Race condition: SQLite-записи из параллельных потоков без транзакционной защиты

**Файл:** `db.py` — все операции `add_chunk`, `update_chunk_status`, `add_term`

**Проблема:** Каждая операция записи открывает отдельное соединение (`connection()` → `sqlite3.connect()`). При 50 параллельных воркерах все пишут в одну `chunks.db` одновременно. SQLite WAL допускает параллельное чтение, но запись — строго один writer. При высокой нагрузке будет `sqlite3.OperationalError: database is locked`.

**Почему опасно:**
- При 50 потоках — гарантированные коллизии по записи.
- `add_chunk` используется для обновления статуса — если статус не записался, чанк потеряется или останется в `_in_progress` навсегда.
- Нет retry на `database is locked`.
- Каждый вызов `add_chunk` открывает и закрывает соединение — нет пулинга.

**Где проявится:** `_run_single_worker` (строки 61, 97-101, 107) — вызывается из 50 потоков одновременно.

**Как воспроизвести:** Запустите перевод главы с 20+ чанками и `max_concurrent=50`.

**Как исправить:**
1. Использовать connection pooling: один connection на процесс, защищённый `threading.Lock`.
2. Добавить `sqlite3.connect(..., timeout=30)` для ожидания разблокировки.
3. Обернуть критические обновления в `BEGIN IMMEDIATE` транзакции.

---

### C-02. `add_chunk` с `INSERT OR REPLACE` уничтожает данные при любом обновлении статуса

**Файл:** `db.py:188-206`, `orchestrator.py:61,97-101,107,350,402,436,495`

**Проблема:** `INSERT OR REPLACE` при наличии UNIQUE constraint удаляет существующую строку и вставляет новую. Это означает:
- `id` (AUTOINCREMENT) меняется при каждом обновлении.
- Если кто-то держит старый `id` — он становится недействительным.
- Если при вызове `add_chunk` для обновления статуса не передать `content_source`/`content_target` корректно — данные перезапишутся пустыми.

**Почему опасно:** В `_run_single_worker` (строка 107 — обработка ошибки) используется `add_chunk` для установки статуса `failed`, передавая `content_target=chunk['content_target']`. Если `chunk['content_target']` был `None` до перевода, а перевод частично прошёл — результат перевода теряется.

**Как исправить:** Для обновления статуса использовать `UPDATE`, а не `INSERT OR REPLACE`. Функция `update_chunk_status` уже существует (строка 236), но не используется в orchestrator! Все вызовы `add_chunk` для обновления статуса — это баг.

---

### C-03. `_run_single_worker` устанавливает статус `in_progress` через `add_chunk`, перезаписывая `content_source`

**Файл:** `orchestrator.py:61`

**Проблема:** Строка 61:
```python
db.add_chunk(config.chunks_db, config.chapter_name, chunk_index, 
             content_source=chunk['content_source'], content_target=chunk['content_target'], 
             status=f"{step_name}_in_progress")
```
Это `INSERT OR REPLACE` — создаёт новую строку с новым `id`. Если два потока обрабатывают один и тот же чанк (маловероятно, но при таймауте и retry — возможно), один поток может перезаписать результат другого.

**Дополнительный риск:** На этапе `reading` (proofreading) `content_target` — это переведённый текст. Если `chunk['content_target']` передан из кеша потока и за это время другой поток уже обновил его — перезапись.

---

### C-04. Глобальная вычитка (`_run_global_proofreading`) использует `chunk_index` из LLM, а не из БД

**Файл:** `proofreader.py:28`, `orchestrator.py:494`

**Проблема:** В `proofreader.apply_diffs` индекс чанка берётся из JSON, возвращённого LLM:
```python
chunk_idx = diff.get("chunk_index")
...
chunk = updated_chunks[chunk_idx]
```
LLM получает чанки в формате `Chunk {chunk['chunk_index']}:` (строка 128 orchestrator.py). Но `chunk_index` в БД начинается с 1 (из `chapter_splitter.py:19` — `chunk_num = 1`), а индексация `updated_chunks[chunk_idx]` — с 0.

**Результат:** Если LLM вернёт `chunk_index: 1` (первый чанк по данным из промпта), патч применится ко второму чанку в списке. Систематическая ошибка «на один».

**Почему опасно:** Исправления глобальной вычитки применяются к НЕПРАВИЛЬНЫМ чанкам. Текст испорчен молча.

**Как воспроизвести:** Переведите главу из 3+ чанков, проверьте, к какому чанку применяется первый diff.

**Как исправить:** Привязка по `chunk_index` из данных, а не по индексу в массиве. Искать чанк по `chunk_index == diff['chunk_index']`.

---

### C-05. Lock-файл не защищает от конкурентного запуска для РАЗНЫХ глав одного тома

**Файл:** `orchestrator.py:271-277`

**Проблема:** Lock-файл один на весь volume: `.state/.lock`. Но `chunks.db` — тоже один на весь volume. Если одновременно запустить перевод двух разных глав одного тома:
- Оба процесса пишут в одну `chunks.db`.
- Lock проверяется только по наличию файла (нет проверки PID живого процесса).
- Если процесс упал, lock не удалён → нельзя продолжить без `--resume`.

**Как исправить:**
1. При проверке lock — проверять, жив ли PID, записанный в lock-файле (`os.kill(pid, 0)`).
2. Либо использовать `fcntl.flock()` для advisory locking.

---

### C-06. `--force` удаляет `chunks.db`, но не проверяет `chapter_name`

**Файл:** `orchestrator.py:279-285`

**Проблема:** `--force` делает `chunks_db.unlink()` — удаляет ВСЮ базу для тома. Если в томе несколько глав, `--force` на одной главе уничтожает состояние ВСЕХ глав тома.

**Как исправить:** `--force` должен удалять только записи конкретной главы (`DELETE FROM chunks WHERE chapter_name = ?`, `DELETE FROM chapter_state WHERE chapter_name = ?`), а не всю БД.

---

### C-07. Контекст `previous_context` для translation статичен — не обновляется после перевода предыдущих чанков

**Файл:** `orchestrator.py:416-419`

**Проблема:** Контексты вычисляются ДО начала параллельного перевода:
```python
all_chunks = db.get_chunks(chunks_db, chapter_name)
contexts = {}
for i, chunk in enumerate(all_chunks):
    if i > 0:
        contexts[chunk['chunk_index']] = all_chunks[i-1]['content_source']
```
`content_source` — это ИСХОДНЫЙ текст, не перевод предыдущего чанка. Комментарий в проекте говорит о «скользящем окне», но передаётся исходный текст предыдущего чанка, а не его перевод.

Для proofreading (строка 453) передаётся `content_target`, что корректнее, но тоже берётся из снимка ДО начала вычитки. Если чанки обрабатываются параллельно, `content_target` предыдущего чанка может быть ещё старым.

**Почему опасно:** Потеря контекста перевода между чанками. LLM не видит, как переведён предыдущий фрагмент, и может использовать другие имена/стиль.

**Как исправить:** Для чанков, зависящих от контекста — обрабатывать последовательно, а не параллельно. Или хотя бы фиксировать: для перевода передавать `content_source` предыдущего чанка осознанно, а для proofreading — `content_target` уже вычитанного предыдущего чанка (последовательно).

---

### C-08. `resume` переводит `_failed` → `_pending` через `add_chunk` с `INSERT OR REPLACE`

**Файл:** `orchestrator.py:344-350`

**Проблема:** При `--resume`:
```python
new_status = chunk['status'].replace('_in_progress', '_pending').replace('_failed', '_pending')
db.add_chunk(chunks_db, chapter_name, chunk['chunk_index'], 
             content_source=chunk['content_source'], content_target=chunk['content_target'], 
             status=new_status)
```
1. `str.replace` вызывается последовательно — если статус `discovery_in_progress_failed` (нестандартный, но возможный при баге) — получим `discovery_pending_pending`.
2. `add_chunk` — `INSERT OR REPLACE` — перезаписывает всю строку, включая `content_target`. Если чанк был частично переведён (на этапе translation), `content_target` из старого снимка может быть устаревшим.

**Как исправить:** Использовать `update_chunk_status` вместо `add_chunk`.

---

## 2. 🟠 HIGH RISK

---

### H-01. Кеш JSON-файлов discovery не привязан к главе — утечка терминов между главами

**Файл:** `orchestrator.py:387-388`

**Проблема:**
```python
for json_file in volume_paths.cache_dir.glob("*.json"):
    raw_responses.append(json_file.read_text(encoding='utf-8'))
```
`cache_dir` — это `.state/cache/`. Glob `*.json` берёт ВСЕ JSON из кеша, включая файлы от предыдущих запусков или от других глав. Файлы не удаляются после обработки и не привязаны к имени главы.

**Результат:** При повторном запуске или обработке второй главы — термины от первой главы смешаются с терминами второй.

**Как исправить:** Именовать JSON файлы с привязкой к `chapter_name` (напр., `{chapter_name}_chunk_{idx}.json`) или очищать кеш перед discovery.

---

### H-02. `_run_single_worker` пишет JSON в cache_dir, но только при `output_suffix == ".json"`

**Файл:** `orchestrator.py:87-92`

**Проблема:** Для discovery запись JSON идёт в `cache_dir / f"chunk_{chunk_index}.json"`. Имя файла — только `chunk_index`, без привязки к главе. При обработке нескольких глав файлы перезапишут друг друга (или вообще не перезапишут, если из другого запуска).

---

### H-03. `RateLimiter.__enter__` спит под LOCK-ом — блокирует все потоки

**Файл:** `rate_limiter.py:19-29`

**Проблема:**
```python
def __enter__(self):
    with self.lock:
        ...
        time.sleep(wait_time)
        self.last_call_time = time.monotonic()
    return self
```
`time.sleep(wait_time)` вызывается внутри `with self.lock`. Это означает, что пока один поток спит (макс. 0.5 сек при 2 RPS), ВСЕ остальные потоки блокированы на `self.lock`. С 50 потоками это приводит к 25-секундной очереди только для прохода через rate limiter.

**Почему опасно:** Фактический RPS будет значительно ниже 2 из-за сериализации через lock. При retry + rate limiter — потоки могут стоять в очереди минуты.

**Как исправить:**
```python
def __enter__(self):
    with self.lock:
        current_time = time.monotonic()
        elapsed = current_time - self.last_call_time
        wait_time = self.min_interval - elapsed
        self.last_call_time = max(current_time, self.last_call_time) + self.min_interval
    if wait_time > 0:
        time.sleep(wait_time)
    return self
```
Вычислять время ожидания под lock-ом, но спать ВНЕ lock-а.

---

### H-04. `run_gemini` формирует команду с промптом через аргумент командной строки

**Файл:** `llm_runner.py:53`

**Проблема:**
```python
command = ['gemini', '-m', model_name, '-p', prompt, '--output-format', output_format]
```
Промпт передаётся как аргумент CLI. Промпт включает весь текст чанка + глоссарий + style_guide + world_info. На большых главах это может быть 50+ КБ текста в одном аргументе.

**Почему опасно:**
1. Большинство ОС имеют лимит `ARG_MAX` (macOS: ~262144 байт). Промпт с большим глоссарием + длинным чанком может превысить лимит → `OSError: [Errno 7] Argument list too long`.
2. Промпт виден в `ps aux` — утечка данных.
3. Экранирование символов — если текст содержит спецсимволы, subprocess может некорректно передать их.

**Как исправить:** Передавать промпт через stdin:
```python
result = subprocess.run(command, input=prompt, ...)
```

---

### H-05. При ошибке этапа — `return` без reset, lock остаётся

**Файл:** `orchestrator.py:382-383, 428-429, 462-463`

**Проблема:** Если этап discovery/translation/proofreading завершается с ошибками, orchestrator делает `return`:
```python
if not success:
    system_logger.error("...")
    return
```
Но `return` попадает в `finally`, который удаляет lock. Это нормально. Однако чанки, которые в `_in_progress`, остаются в этом статусе навсегда — при следующем запуске БЕЗ `--resume` они не будут обработаны.

**Почему опасно:** Stage не откатывается. Чанки зависли в `_in_progress`. Без `--resume` система считает, что перевод заблокирован.

---

### H-06. `init_glossary_db` не вызывается перед операциями с глоссарием в orchestrator

**Файл:** `orchestrator.py:266,371`

**Проблема:** `glossary_db = series_root / 'glossary.db'` — путь устанавливается. Затем вызывается `db.get_terms(glossary_db, ...)`. Но `init_glossary_db` не вызывается нигде в orchestrator. Если glossary.db не существует (удалён, или серия создана вручную без `init`):
```
sqlite3.OperationalError: no such table: glossary
```

**Как исправить:** Вызывать `db.init_glossary_db(glossary_db)` перед первым обращением.

---

### H-07. `translate-all` не обрабатывает `TranslationLockedError` — crash на первом заблокированном томе

**Файл:** `commands/translate_cmd.py:106-108`

**Проблема:** `_translate_directory` вызывает `_translate_file`, который ловит `TranslationLockedError`. Но если одна глава заблокирована, `SystemExit(1)` убивает весь процесс `translate-all`. Остальные главы/тома не обрабатываются.

**Как исправить:** Ловить `SystemExit` или `TranslationLockedError` в цикле `_translate_directory` и продолжать.

---

### H-08. `translate-all` не передаёт `--stage` — невозможно перезапустить этап для всех глав

**Файл:** `cli.py:42-52`, `commands/translate_cmd.py:69-91`

**Проблема:** Парсер `translate-all` не имеет параметра `--stage`. `run_translate_all` не передаёт `restart_stage` в `_translate_file`. Нет способа перезапустить конкретный этап для серии.

---

## 3. 🟡 MEDIUM

---

### M-01. `chapter_splitter.py` записывает файлы на диск, хотя они нигде не используются

**Файл:** `chapter_splitter.py:36-39`

**Проблема:** `split_chapter_intelligently` записывает каждый чанк в файл `chunk_{num}.txt` в `output_dir`. Но `orchestrator.py` использует только возвращаемые данные `chunks_data` — записывает текст в БД, а файлы никогда не читает.

**Результат:** Засорение диска бесполезными файлами в `cache/temp_split/`.

**Как исправить:** Убрать запись файлов. Возвращать только данные через return.

---

### M-02. `chapter_splitter.py:21` — `previous_text` используется для `context`, но `context` нигде не используется

**Файл:** `chapter_splitter.py:21,32-33`

**Проблема:** `chunks_data.append({"id": ..., "text": ..., "context": previous_text})`. Поле `context` не используется ни в `orchestrator.py`, ни где-либо ещё. Мёртвый код.

---

### M-03. Нет валидации `pipeline_stage` при записи — можно записать мусор

**Файл:** `db.py:274-291`

**Проблема:** `set_chapter_stage` принимает любую строку как `stage`. Нет enum-a, нет валидации. Опечатка типа `set_chapter_stage(db, ch, "translaton")` молча пройдёт и сломает весь pipeline.

**Как исправить:** Определить `VALID_STAGES = frozenset(...)` и проверять при записи.

---

### M-04. `status_cmd.py:78-81` — двойной подсчёт `reading_done`

**Файл:** `commands/status_cmd.py:78-81`

**Проблема:**
```python
done = sum(
    1 for c in chunks
    if c['status'].endswith('_done') or c['status'] == 'reading_done'
)
```
`reading_done` **уже** подходит под `endswith('_done')`. Второе условие избыточно.

---

### M-05. `logger.py` — `setup_loggers` очищает ВСЕ хендлеры, включая дефолтный stdout

**Файл:** `logger.py:37-39`

**Проблема:** При вызове `setup_loggers` все хендлеры очищаются. Дефолтный `JsonFormatter` `StreamHandler` удаляется. Если `debug_mode=False`, для `input_logger` и `output_logger` ставится `NullHandler`, но `system_logger` получает только `RichHandler`.

В режиме без setup (например, при импорте модуля без вызова `setup_loggers`) логгер пишет JSON в stdout. После setup — Rich-формат в console. Непоследовательность форматов.

---

### M-06. `utils.parse_llm_json` — `json_repair` может молча вернуть невалидные данные

**Файл:** `utils.py:60-64`

**Проблема:** `json_repair.repair_json(text)` возвращает строку, которую затем парсят через `json.loads`. Но `json_repair` может «починить» JSON неправильно — добавить/убрать скобки, изменить значения. Нет валидации результата.

**Почему опасно:** Для шага discovery — LLM вернул слегка битый JSON, json_repair «починил» его, но потерял часть терминов. Для global_proofreading — патчи могут быть невалидными.

---

### M-07. `convert_to_docx.py` — top-level import `from docx import Document` — crash при отсутствии python-docx

**Файл:** `convert_to_docx.py:4-6`

**Проблема:** `from docx import Document` — на уровне модуля. Если python-docx не установлен, `import book_translator.convert_to_docx` вызовет `ImportError` при загрузке модуля. Orchestrator импортирует `convert_to_docx` на строке 15 — crash при старте, даже если конвертация не нужна.

В отличие от `convert_to_epub.py` (где `_EBOOKLIB_AVAILABLE` проверяется), `convert_to_docx` не имеет graceful fallback.

**Как воспроизвести:** `pip uninstall python-docx && book-translator translate ...`

**Как исправить:** Lazy import внутри функции `convert_txt_to_docx`, аналогично `convert_to_epub.py`.

---

### M-08. `_find_bundled_style_guide` — хрупкий путь через `parent.parent.parent.parent`

**Файл:** `commands/init_cmd.py:52`

**Проблема:**
```python
style_guides_dir = Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'style_guides'
```
Четыре уровня `parent` от `commands/init_cmd.py` → `commands/` → `book_translator/` → `src/` → корень проекта. Если структура проекта изменится или пакет установлен через pip (в site-packages) — путь не найдётся. Молча вернёт `None`, style guide не скопируется.

---

### M-09. `discovery.py` — при `tomllib = None` ошибка проявится только при вызове функции

**Файл:** `discovery.py:10-16`

**Проблема:** Если нет ни `tomllib`, ни `tomli`, `tomllib` устанавливается в `None`. Ошибка произойдёт только при вызове `find_series_root()` или `load_series_config()`. Пользователь увидит `ImportError` без контекста.

Кроме того, Python 3.11+ всегда имеет `tomllib`. Проект требует 3.11+ → fallback на `tomli` мёртвый код.

---

### M-10. `_SUBPROCESS_CWD = find_tool_versions_dir()` — вызывается при ИМПОРТЕ модуля

**Файл:** `llm_runner.py:17`

**Проблема:** `find_tool_versions_dir()` выполняется при первом импорте `llm_runner`. Это обход файловой системы (`Path(__file__).resolve().parents`) для поиска `.tool-versions`. Если файл не найден — `cwd=None` для subprocess. Побочный эффект при импорте, нарушающий тестируемость и предсказуемость.

---

## 4. 🔵 LOW / CLEANUP

---

### L-01. `default_prompts.get_prompt()` — не используется нигде

**Файл:** `default_prompts.py:371-385`

Функция `get_prompt()` не вызывается ни в одном модуле. Используется только `PROMPTS` напрямую через `path_resolver.resolve_prompt()`.

---

### L-02. `data/` и `docs/` — не исследованы, но `data/style_guides/` используется в `init_cmd`

Директория `data/` может содержать style guides. Убедиться, что содержимое актуально.

---

### L-03. Неиспользуемый импорт `sys` в `chapter_splitter.py`

**Файл:** `chapter_splitter.py:3`

`import sys` — не используется.

---

### L-04. Дублирование логики извлечения терминов в `term_collector.py`

**Файл:** `term_collector.py:61-87,96-117`

Функции `save_approved_terms` и `approve_via_tsv` содержат идентичную логику извлечения `term_source`, `term_target`, `comment` из данных терминов. Скопирована дословно. Нужно вынести в приватную функцию.

---

### L-05. `ANALISE.md` — предыдущий анализ, возможно устаревший файл

**Файл:** `ANALISE.md` (17729 байт)

Результат предыдущего аудита. Проверить актуальность, удалить если заменён данным отчётом.

---

### L-06. `tui.py` — минимальный модуль, но `Console` экспортируется без контроля

**Файл:** `tui.py:4`

`console = Console()` — модульная глобальная переменная. При параллельном использовании Rich Console — возможны артефакты вывода. Не критично, но следует знать.

---

## СВОДНАЯ ТАБЛИЦА

| ID    | Уровень  | Компонент             | Суть                                                  |
| ----- | -------- | --------------------- | ----------------------------------------------------- |
| C-01  | 🔴 CRITICAL | `db.py`               | SQLite writes из 50 потоков без защиты                |
| C-02  | 🔴 CRITICAL | `db.py`               | `INSERT OR REPLACE` уничтожает данные                 |
| C-03  | 🔴 CRITICAL | `orchestrator.py`     | `add_chunk` для статуса перезаписывает строку          |
| C-04  | 🔴 CRITICAL | `proofreader.py`      | Off-by-one: LLM chunk_index ≠ индекс в массиве       |
| C-05  | 🔴 CRITICAL | `orchestrator.py`     | Lock-файл не защищает от конкурентности                |
| C-06  | 🔴 CRITICAL | `orchestrator.py`     | `--force` удаляет ВСЮ БД тома                         |
| C-07  | 🔴 CRITICAL | `orchestrator.py`     | Контекст перевода — source, не перевод пред. чанка    |
| C-08  | 🔴 CRITICAL | `orchestrator.py`     | `resume` через `add_chunk` может потерять данные      |
| H-01  | 🟠 HIGH    | `orchestrator.py`     | JSON кеш discovery не привязан к главе                |
| H-02  | 🟠 HIGH    | `orchestrator.py`     | Имена JSON-файлов без prefix главы                    |
| H-03  | 🟠 HIGH    | `rate_limiter.py`     | Sleep внутри lock                                     |
| H-04  | 🟠 HIGH    | `llm_runner.py`       | Промпт через CLI аргумент — ARG_MAX                  |
| H-05  | 🟠 HIGH    | `orchestrator.py`     | Ранний return без reset статусов `_in_progress`       |
| H-06  | 🟠 HIGH    | `orchestrator.py`     | Нет `init_glossary_db` перед чтением глоссария        |
| H-07  | 🟠 HIGH    | `translate_cmd.py`    | `translate-all` crash при lock                        |
| H-08  | 🟠 HIGH    | `translate_cmd.py`    | `translate-all` нет `--stage`                         |
| M-01  | 🟡 MEDIUM  | `chapter_splitter.py` | Файлы чанков пишутся на диск зря                      |
| M-02  | 🟡 MEDIUM  | `chapter_splitter.py` | Поле `context` не используется                        |
| M-03  | 🟡 MEDIUM  | `db.py`               | Нет валидации `pipeline_stage`                        |
| M-04  | 🟡 MEDIUM  | `status_cmd.py`       | Двойной подсчёт `reading_done`                        |
| M-05  | 🟡 MEDIUM  | `logger.py`           | Непоследовательность хендлеров                        |
| M-06  | 🟡 MEDIUM  | `utils.py`            | `json_repair` может молча испортить данные            |
| M-07  | 🟡 MEDIUM  | `convert_to_docx.py`  | Top-level import убивает приложение                   |
| M-08  | 🟡 MEDIUM  | `init_cmd.py`         | Хрупкий path через 4 parent                           |
| M-09  | 🟡 MEDIUM  | `discovery.py`        | Мёртвый fallback tomli                                |
| M-10  | 🟡 MEDIUM  | `llm_runner.py`       | Побочный эффект при импорте                           |
| L-01  | 🔵 LOW     | `default_prompts.py`  | `get_prompt()` не используется                        |
| L-02  | 🔵 LOW     | корень                | Неисследованная `data/`                               |
| L-03  | 🔵 LOW     | `chapter_splitter.py` | Неиспользуемый `import sys`                           |
| L-04  | 🔵 LOW     | `term_collector.py`   | Дублирование логики извлечения                        |
| L-05  | 🔵 LOW     | корень                | Устаревший `ANALISE.md`                               |
| L-06  | 🔵 LOW     | `tui.py`              | Глобальный Console при многопоточности                |
