# PLAN: Исправления по аудиту ANALISE.md

Источник: аудит проекта от 2026-03-21 (ANALISE.md), верифицирован вручную.
Из 26 issues: 21 подтверждён, 3 частично валидны, 1 невалиден, 1 подтверждён (L-01).

## Ограничения

- **Все тесты должны проходить** после каждой задачи (`pytest`).
- **НЕ трогать**: `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`.
- Каждая задача — один `pytest` прогон в конце. Если тесты падают — чинить в рамках задачи.
- Номера строк указаны приблизительно — ориентируйся на контекст кода, не на номера.

## Цикл выполнения

Для каждой задачи:
1. Прочитай файлы, указанные в задаче.
2. Внеси изменения.
3. Запусти `pytest`. Если падает — исправь. Если не падает — поставь `[x]` и переходи к следующей.

---

## Фаза 1 — Критические баги (порча/потеря данных)

### BUG-1: Off-by-one в global proofreading (C-04)

**Файл:** `src/book_translator/proofreader.py`

**Проблема:** `apply_diffs()` использует `chunk_index` из LLM как индекс массива (0-based), но chunk_index в БД начинается с 1. LLM видит "Chunk 1:", возвращает `chunk_index: 1`, proofreader берёт `updated_chunks[1]` — это ВТОРОЙ элемент, не первый. Диффы применяются к неправильным чанкам.

**Действие:**
1. В `apply_diffs()` заменить прямую индексацию `updated_chunks[chunk_idx]` на поиск по полю `chunk_index`:
```python
# Вместо:
chunk = updated_chunks[chunk_idx]

# Сделать:
matching = [c for c in updated_chunks if c['chunk_index'] == chunk_idx]
if not matching:
    system_logger.warning(f"Chunk with chunk_index={chunk_idx} not found")
    continue
chunk = matching[0]
# Обновить оригинал в списке:
idx_in_list = updated_chunks.index(chunk)
updated_chunks[idx_in_list] = chunk
```
2. Убрать проверку `chunk_idx >= len(updated_chunks)` — она больше не нужна, поиск по значению сам покажет отсутствие.
3. Добавить тест в `tests/test_proofreader.py`:
   - Чанки с `chunk_index` = 1, 2, 3 (1-based). Дифф с `chunk_index: 1`. Убедиться что патч применяется к чанку с `chunk_index == 1`, а не ко второму элементу массива.

**Проверка:** `pytest`

- [x] BUG-1

---

### BUG-2: Заменить add_chunk на update_chunk_status для обновления статусов (C-02, C-03, C-08)

**Файлы:** `src/book_translator/orchestrator.py`, `src/book_translator/db.py`

**Проблема:** `_run_single_worker()` и `--resume` логика используют `db.add_chunk()` (INSERT OR REPLACE) для изменения статуса чанка. Это перезаписывает всю строку, включая `content_source` и `content_target`. Потенциальная потеря данных. Функция `db.update_chunk_status()` уже существует, но не используется.

**Действие:**
1. В `_run_single_worker()` заменить ВСЕ вызовы `db.add_chunk()` для обновления статуса на `db.update_chunk_status()`:
   - Установка `*_in_progress` (строка ~61)
   - Установка `*_done` (строки ~97-101)
   - Установка `*_failed` (строка ~107)
   - **ИСКЛЮЧЕНИЕ:** Вызовы `add_chunk` где записывается `content_target` (результат перевода) — оставить `add_chunk`, т.к. нужно обновить и контент и статус. Для этого случая создать `db.update_chunk_content()`:
     ```python
     def update_chunk_content(db_path, chapter_name, chunk_index, content_target, status):
         with connection(db_path) as conn:
             conn.execute(
                 'UPDATE chunks SET content_target = ?, status = ? WHERE chapter_name = ? AND chunk_index = ?',
                 (content_target, status, chapter_name, chunk_index),
             )
             conn.commit()
     ```
2. В `--resume` блоке (~строки 344-350) заменить `db.add_chunk()` на `db.update_chunk_status()`.
3. Добавить тест: вставить чанк через `add_chunk`, затем вызвать `update_chunk_status` — убедиться что `content_target` не изменился.

**Проверка:** `pytest`

- [x] BUG-2

---

### BUG-3: --force должен удалять записи главы, а не весь chunks.db (C-06)

**Файл:** `src/book_translator/orchestrator.py`, `src/book_translator/db.py`

**Проблема:** `--force` делает `chunks_db.unlink()` — удаляет ВСЮ базу тома. Если в томе несколько глав, состояние всех глав теряется.

**Действие:**
1. В `db.py` добавить функцию:
```python
def clear_chapter(db_path: Path, chapter_name: str) -> None:
    """Delete all chunks and chapter_state for a specific chapter."""
    with connection(db_path) as conn:
        conn.execute('DELETE FROM chunks WHERE chapter_name = ?', (chapter_name,))
        conn.execute('DELETE FROM chapter_state WHERE chapter_name = ?', (chapter_name,))
        conn.commit()
```
2. В `orchestrator.py` заменить блок `--force` (~строки 279-285):
```python
# Вместо:
if chunks_db.exists():
    chunks_db.unlink()
db.init_chunks_db(chunks_db)

# Сделать:
db.init_chunks_db(chunks_db)  # ensure DB exists
db.clear_chapter(chunks_db, chapter_name)
```
3. Добавить тест: создать 2 главы, `clear_chapter` на одну — убедиться что вторая осталась.

**Проверка:** `pytest`

- [x] BUG-3

---

### BUG-4: Двойной подсчёт reading_done в status_cmd (M-04)

**Файл:** `src/book_translator/commands/status_cmd.py`

**Проблема:** Строки ~78-81: `endswith('_done')` уже включает `reading_done`, но есть ещё `or c['status'] == 'reading_done'`.

**Действие:** Убрать дублирующее условие:
```python
done = sum(1 for c in chunks if c['status'].endswith('_done'))
```

**Проверка:** `pytest`

- [x] BUG-4

---

### TERM-1: Переработка промпта и pipeline сбора терминов

**Файлы:**
- `src/book_translator/default_prompts.py` — переписать `TERM_DISCOVERY_PROMPT`
- `prompts/term_discovery.txt` — синхронизировать с `default_prompts.py`
- `src/book_translator/term_collector.py` — упростить парсинг
- `tests/test_term_collector.py` — обновить тесты

**Проблема (4 подпроблемы):**

**A. Избыточная категоризация.** Промпт требует от LLM сортировать термины в 3 категории: `characters`, `terminology`, `expressions`. В БД глоссария нет поля category — хранится плоская строка `(source_term, target_term, comment)`. LLM тратит токены на бесполезную категоризацию. `collect_terms_from_responses` итерирует двухуровневую вложенность, пересобирает `final_structure` по категориям — и затем категория выбрасывается при записи в TSV/DB.

**B. Стилистическое несоответствие.** `TERM_DISCOVERY_PROMPT` написан на русском, остальные 3 промпта (`TRANSLATION`, `PROOFREADING`, `GLOBAL_PROOFREADING`) — на английском.

**C. Comment не ограничен.** Формулировка "краткое описание и контекст появления" расплывчата — LLM может генерировать длинные описания. Нужно явно ограничить: одно предложение, макс. ~15 слов. Сюда можно вместить полезное из бывших полей (пол, роль, принадлежность) — но коротко.

**D. Код завязан на категории.** `collect_terms_from_responses`, `save_approved_terms`, `approve_via_tsv`, `_EXPECTED_CATEGORIES` — всё построено вокруг трёхуровневой структуры, которая не нужна.

**Действие:**

1. **Промпт** — переписать `TERM_DISCOVERY_PROMPT` на английском (как остальные промпты). Целевой формат вывода от LLM — **плоский JSON-массив**:
```json
[
  {"source": "キリト", "target": "Кирито", "comment": "male, protagonist, swordsman"},
  {"source": "ソードスキル", "target": "Навык меча", "comment": "combat technique activated by the game system"}
]
```
Никаких категорий, никаких `term_id` ключей. Пустой результат: `[]`.
Ограничение на comment: "one sentence, max 15 words. For characters: gender + role. For terms/places: brief definition."

2. **`prompts/term_discovery.txt`** — синхронизировать содержимое с `default_prompts.py`.

3. **`collect_terms_from_responses`** — переписать:
   - Принимать и плоский массив `[{source, target, comment}, ...]` (новый формат)
   - И старый формат с категориями `{characters: {...}, terminology: {...}}` (backward compat для кешированных ответов)
   - Удалить `_EXPECTED_CATEGORIES`
   - Возвращать `list[dict]` вместо `dict[str, dict]` — плоский список `[{term_source, term_target, comment}, ...]`

4. **`save_approved_terms`** — упростить: принимает `list[dict]` вместо вложенного dict с категориями. Fallback-цепочки упрощаются: `source` → `term_source` → `term_jp`, `target` → `term_target` → `term_ru`.

5. **`approve_via_tsv`** — аналогично упростить.

6. **Обновить вызывающий код в `orchestrator.py`** (~строки 390-395): адаптировать под новый формат возврата `collect_terms_from_responses`. Проверка `if any(new_terms.values())` заменяется на `if new_terms`.

7. **Тесты** — обновить `tests/test_term_collector.py`:
   - Тест нового формата (плоский массив)
   - Тест backward compat (старый формат с категориями)
   - Тест пустого массива `[]`
   - Тесты `save_approved_terms` и `approve_via_tsv` с новым форматом

**Проверка:** `pytest`. `grep -c 'characters.*terminology.*expressions' src/book_translator/term_collector.py` → 0.

- [x] TERM-1

---

## Фаза 2 — Устойчивость (concurrency, error handling)

### ROB-1: Добавить timeout к sqlite3.connect (C-01)

**Файл:** `src/book_translator/db.py`

**Проблема:** `sqlite3.connect()` без explicit timeout. При 50 параллельных потоках запись может подвисать.

**Действие:** В `connection()` добавить `timeout=30`:
```python
conn = sqlite3.connect(str(db_path), timeout=30)
```

**Проверка:** `pytest`

- [x] ROB-1

---

### ROB-2: Lock с проверкой PID (C-05)

**Файл:** `src/book_translator/orchestrator.py`

**Проблема:** Lock проверяется только по наличию файла. Если процесс упал — lock навсегда. Нет проверки что PID жив.

**Действие:**
1. Добавить приватную функцию:
```python
def _is_pid_alive(pid: int) -> bool:
    """Check if process with given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False
```
2. В блоке проверки lock (~строка 273) добавить PID-проверку:
```python
if lock_file.exists() and not resume:
    try:
        pid = int(lock_file.read_text().strip())
        if _is_pid_alive(pid):
            raise TranslationLockedError(...)
        else:
            system_logger.warning(f"[Orchestrator] Stale lock (PID {pid} мёртв). Удаляю lock.")
            lock_file.unlink()
    except (ValueError, OSError):
        lock_file.unlink()
```

**Проверка:** `pytest`

- [x] ROB-2

---

### ROB-3: Привязка JSON-кеша discovery к имени главы (H-01, H-02)

**Файл:** `src/book_translator/orchestrator.py`

**Проблема:** JSON-файлы в кеше именуются `chunk_{index}.json` без привязки к главе. При обработке нескольких глав одного тома — коллизия имён и смешивание терминов.

**Действие:**
1. При записи JSON (~строка 88) добавить prefix главы:
```python
safe_chapter = config.chapter_name.replace('/', '_').replace('\\', '_')
output_path = config.volume_paths.cache_dir / f"{safe_chapter}_chunk_{chunk_index}{output_suffix}"
```
2. При чтении JSON (~строка 387) фильтровать по имени главы:
```python
safe_chapter = chapter_name.replace('/', '_').replace('\\', '_')
for json_file in volume_paths.cache_dir.glob(f"{safe_chapter}_chunk_*.json"):
```
3. Добавить тест: два "chapter_name" → файлы не пересекаются.

**Проверка:** `pytest`

- [x] ROB-3

---

### ROB-4: Сброс in_progress при провале этапа (H-05)

**Файл:** `src/book_translator/orchestrator.py`

**Проблема:** Если этап завершается с ошибками (return), чанки в статусе `*_in_progress` остаются зависшими. Следующий запуск без `--resume` не может их обработать.

**Действие:** Перед `return` на провале каждого этапа (discovery/translation/proofreading) — сбросить `_in_progress` в `_failed`:
```python
if not success:
    # Reset any in_progress chunks to failed
    chunks = db.get_chunks(chunks_db, chapter_name)
    for chunk in chunks:
        if chunk['status'].endswith('_in_progress'):
            new_status = chunk['status'].replace('_in_progress', '_failed')
            db.update_chunk_status(chunks_db, chapter_name, chunk['chunk_index'], new_status)
    system_logger.error("[Orchestrator] Этап завершился с ошибками.")
    return
```
Повторить для всех трёх мест (discovery ~382, translation ~428, proofreading ~462). Вынести в приватную функцию `_reset_in_progress_to_failed()`.

**Проверка:** `pytest`

- [x] ROB-4

---

### ROB-5: translate-all: не падать на заблокированном томе (H-07)

**Файл:** `src/book_translator/commands/translate_cmd.py`

**Проблема:** `_translate_file` при `TranslationLockedError` делает `SystemExit(1)`. В цикле `translate-all` это убивает весь процесс.

**Действие:**
1. В `_translate_file` заменить `raise SystemExit(1)` на `return False` (или `raise` самого `TranslationLockedError`).
2. В `_translate_directory` обернуть вызов `_translate_file` в try/except:
```python
try:
    _translate_file(series_root, source_file, args)
except TranslationLockedError as e:
    print(f"\n🔒 {e}")
    continue
```
3. Убедиться что одиночный `translate` по-прежнему завершается с ошибкой (SystemExit для CLI).

**Проверка:** `pytest`

- [x] ROB-5

---

## Фаза 3 — Performance & Safety

### PERF-1: Rate limiter — sleep вне lock (H-03)

**Файл:** `src/book_translator/rate_limiter.py`

**Проблема:** `time.sleep(wait_time)` выполняется внутри `with self.lock`. Все 50 потоков ждут пока один спит.

**Действие:** Вычислять wait_time под lock-ом, спать ВНЕ:
```python
def __enter__(self):
    with self.lock:
        current_time = time.monotonic()
        elapsed = current_time - self.last_call_time
        wait_time = self.min_interval - elapsed
        if wait_time > 0:
            self.last_call_time = current_time + wait_time
        else:
            self.last_call_time = current_time
    if wait_time > 0:
        time.sleep(wait_time)
    return self
```

**Проверка:** `pytest`

- [x] PERF-1

---

### SAFE-1: Передача промпта через stdin вместо CLI аргумента (H-04)

**Файл:** `src/book_translator/llm_runner.py`

**Проблема:** Промпт передаётся как CLI аргумент (`-p prompt`). При большом промпте (50+ КБ) может превысить ARG_MAX. Также промпт виден в `ps aux`.

**Действие:**
1. Убрать `-p` из команды, передать промпт через stdin:
```python
command = ['gemini', '-m', model_name, '--output-format', output_format]
result = subprocess.run(
    command,
    input=prompt,
    capture_output=True,
    text=True,
    timeout=timeout,
    cwd=_SUBPROCESS_CWD,
)
```
2. **ВАЖНО:** Проверь документацию gemini-cli — поддерживает ли он чтение из stdin. Если нет, альтернатива — записать промпт во временный файл и передать через `-f`:
```python
import tempfile
with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
    f.write(prompt)
    f.flush()
    command = ['gemini', '-m', model_name, '-f', f.name, '--output-format', output_format]
    ...
os.unlink(f.name)
```
Если ни stdin ни -f не поддерживаются — пропустить эту задачу и оставить комментарий.

**Проверка:** `pytest`

- [x] SAFE-1

---

### SAFE-2: Lazy import для python-docx (M-07)

**Файл:** `src/book_translator/convert_to_docx.py`

**Проблема:** `from docx import Document` на уровне модуля. Если python-docx не установлен — crash при импорте модуля, даже если конвертация не нужна.

**Действие:** Перенести import внутрь функции (аналогично `convert_to_epub.py`):
```python
def convert_txt_to_docx(...):
    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx is required for DOCX conversion. Install: pip install python-docx")
    ...
```

**Проверка:** `pytest`

- [x] SAFE-2

---

## Фаза 4 — CLI

### CLI-1: Добавить --stage в translate-all (H-08)

**Файлы:** `src/book_translator/cli.py`, `src/book_translator/commands/translate_cmd.py`

**Проблема:** `translate-all` не принимает `--stage`, хотя downstream код его поддерживает.

**Действие:**
1. В `cli.py` добавить `--stage` к парсеру `translate-all` (скопировать из `translate`):
```python
all_parser.add_argument(
    '--stage',
    choices=['discovery', 'translation', 'proofreading', 'global_proofreading'],
    default=None,
    help='Принудительно перезапустить с указанного этапа'
)
```

**Проверка:** `pytest` + `book-translator translate-all --help` показывает `--stage`.

- [x] CLI-1

---

## Фаза 5 — Cleanup

### CLEAN-1: Убрать бесполезные записи на диск из chapter_splitter (M-01, M-02)

**Файл:** `src/book_translator/chapter_splitter.py`

**Проблема:** `split_chapter_intelligently()` записывает файлы `chunk_{num}.txt` на диск — они нигде не читаются. Поле `context` в возвращаемых данных — не используется.

**Действие:**
1. Удалить запись файлов (~строки 36-39).
2. Удалить поле `context` из возвращаемого dict (~строки 29-33).
3. Удалить параметр `output_dir` из сигнатуры функции, если он используется только для записи.
4. Обновить вызывающий код в `orchestrator.py` — убрать передачу `output_dir`.
5. Удалить `import sys` (L-03).

**Проверка:** `pytest`

- [x] CLEAN-1

---

### CLEAN-2: Валидация pipeline_stage (M-03)

**Файл:** `src/book_translator/db.py`

**Проблема:** `set_chapter_stage()` принимает любую строку.

**Действие:** Добавить валидацию:
```python
VALID_STAGES = frozenset({
    'discovery', 'translation', 'proofreading', 'global_proofreading', 'done'
})

def set_chapter_stage(db_path, chapter_name, stage):
    if stage not in VALID_STAGES:
        raise ValueError(f"Invalid pipeline stage: {stage!r}. Valid: {VALID_STAGES}")
    ...
```

**Проверка:** `pytest`

- [x] CLEAN-2

---

### CLEAN-3: Удалить неиспользуемые функции и код (L-01, M-09)

**Файлы:**
- `src/book_translator/default_prompts.py` — удалить `get_prompt()` (~строка 371-385)
- `src/book_translator/discovery.py` — удалить fallback на `tomli` (Python 3.11+ гарантирует `tomllib`)

**Проверка:** `pytest`

- [x] CLEAN-3

---

### ~~CLEAN-4: Извлечь общую логику извлечения терминов (L-04)~~ — поглощена TERM-1

Дублирование fallback-цепочек в `save_approved_terms`/`approve_via_tsv` устраняется в рамках TERM-1 при переходе на плоский формат.

- [x] CLEAN-4 (skip — covered by TERM-1)

---

### CLEAN-5: Исправить хрупкий path для style_guides (M-08)

**Файл:** `src/book_translator/commands/init_cmd.py`

**Проблема:** `Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'style_guides'` — 4 уровня parent. Ломается при установке через pip.

**Действие:** Использовать `importlib.resources`:
```python
from importlib import resources

def _find_bundled_style_guide(source_lang: str, target_lang: str) -> Path | None:
    try:
        data_dir = resources.files('book_translator').parent.parent / 'data' / 'style_guides'
    except Exception:
        data_dir = Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'style_guides'
    ...
```
Или включить `data/` в package_data через `pyproject.toml` и использовать `resources.files('book_translator.data.style_guides')`.

**Проверка:** `pytest`

- [x] CLEAN-5

---

### CLEAN-6: Lazy-оценка _SUBPROCESS_CWD (M-10)

**Файл:** `src/book_translator/llm_runner.py`

**Проблема:** `_SUBPROCESS_CWD = find_tool_versions_dir()` выполняется при импорте модуля. Побочный эффект.

**Действие:** Использовать `functools.lru_cache`:
```python
from functools import lru_cache

@lru_cache(maxsize=1)
def _get_subprocess_cwd() -> str | None:
    return find_tool_versions_dir()
```
Заменить `_SUBPROCESS_CWD` на `_get_subprocess_cwd()` в вызове `subprocess.run()`.

**Проверка:** `pytest`

- [x] CLEAN-6

---

## Не включено в план (осознанно)

| ID | Причина исключения |
|---|---|
| C-07 | Дизайн-решение: sequential vs parallel перевод. Требует обсуждения архитектуры, не баг. |
| H-06 | Невалидно: `init` команда создаёт glossary.db. |
| M-05 | Logger handlers — низкий приоритет, не влияет на функциональность. |
| M-06 | json_repair — known limitation, нет лучшей альтернативы без переписки LLM-парсинга. |
| L-02 | data/ содержит style_guides, всё ок. |
| L-05 | ANALISE.md — удалить после завершения плана. |
| L-06 | Global Console — теоретический risk, Rich handle thread safety internally. |

---

## Порядок выполнения

| # | Задача | Зависимости | Риск |
|---|--------|-------------|------|
| 1 | BUG-1 | — | Высокий (off-by-one corruption) |
| 2 | BUG-2 | — | Средний (новая функция db + рефакторинг) |
| 3 | BUG-3 | BUG-2 (нужна clear_chapter в db.py) | Средний |
| 4 | BUG-4 | — | Низкий |
| 5 | TERM-1 | — | Высокий (переписка промпта + парсера + тестов) |
| 6 | ROB-1 | — | Низкий |
| 7 | ROB-2 | — | Средний |
| 8 | ROB-3 | — | Средний |
| 9 | ROB-4 | BUG-2 (update_chunk_status) | Средний |
| 10 | ROB-5 | — | Средний |
| 11 | PERF-1 | — | Низкий |
| 12 | SAFE-1 | — | Средний (зависит от gemini-cli) |
| 13 | SAFE-2 | — | Низкий |
| 14 | CLI-1 | — | Низкий |
| 15 | CLEAN-1 | — | Низкий |
| 16 | CLEAN-2 | — | Низкий |
| 17 | CLEAN-3 | — | Низкий |
| 18 | ~~CLEAN-4~~ | skip — поглощена TERM-1 | — |
| 19 | CLEAN-5 | — | Низкий |
| 20 | CLEAN-6 | — | Низкий |
