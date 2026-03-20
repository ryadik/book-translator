# PLAN.md — Мультиязычный рефакторинг book-translator

> **Цель:** Сделать `book-translator` способным переводить с **любого** исходного языка на **русский** (any→ru), подготовив инфраструктуру для будущего расширения до any→any.

---

## ИНСТРУКЦИЯ ДЛЯ МОДЕЛИ

**Ты — инженер атомной станции.** Каждое изменение, которое ты вносишь, проходит через процесс абсолютной верификации. Ошибка в промпте — это ошибка, которая размножится на сотни LLM-вызовов и испортит перевод целой книги. Действуй с соответствующей ответственностью.

### Цикл работы

1. **Прочитай этот файл целиком.** Найди первую задачу со статусом `[ ]` (не начата).
2. **Отметь задачу как начатую:** замени `[ ]` на `[-]`.
3. **Прочитай ВСЕ файлы**, перечисленные в задаче. Не правь файл, который не читал.
4. **Выполни изменения** строго по описанию. Не добавляй ничего сверх описанного — никаких "заодно поправлю", никаких рефакторингов по соседству.
5. **Проверь критерии приёмки** — каждый пункт. Если критерий требует `grep` или `pytest` — выполни команду и убедись в результате.
6. **Отметь задачу как выполненную:** замени `[-]` на `[x]`.
7. **Перейди к следующей задаче.** Повтори цикл.

### Правила

- **Одна задача за раз.** Не забегай вперёд. Не группируй задачи.
- **Файлы-оверрайды и бандлированные промпты — синхронизированы.** Если задача затрагивает промпт, правь и `default_prompts.py`, и соответствующий файл в `prompts/`. Они должны быть идентичны по содержимому (за исключением обёртки `r"""..."""` в Python).
- **Не ломай существующие тесты.** После каждой задачи запусти `pytest` и убедись, что всё зелёное.
- **Не трогай файлы, не указанные в задаче.**
- **Комментируй только код (Python), не промпты.** В промптах каждый символ — это токен для LLM.

### Контекст архитектуры

Плейсхолдеры в промптах подставляются через `.replace()` в `orchestrator.py`. Промпты хранятся:
- **Бандлированные:** `src/book_translator/default_prompts.py` (4 константы: `TRANSLATION_PROMPT`, `PROOFREADING_PROMPT`, `GLOBAL_PROOFREADING_PROMPT`, `TERM_DISCOVERY_PROMPT`)
- **Оверрайды:** `prompts/translation.txt`, `prompts/proofreading.txt`, `prompts/global_proofreading.txt`, `prompts/term_discovery.txt`

Языковая пара берётся из `book-translator.toml`: `[series] source_lang = "ja"`, `target_lang = "ru"` и передаётся через `orchestrator.py`.

---

## ЗАДАЧИ

### Фаза 1: Инфраструктура

#### [x] LANG-1: Создать модуль `languages.py` с маппингом языков и типографическими правилами

**Цель:** Создать единый источник правды для языко-зависимых данных: названия языков и типографические правила (ANCHOR D).

**Файлы:**
- **Создать:** `src/book_translator/languages.py`

**Что сделать:**

1. Создать файл `src/book_translator/languages.py` со следующим содержимым:

```python
"""
Language-specific data for book-translator.

Centralizes all language-dependent information:
- Language names (for prompt parametrization)
- Typography rules per target language (extracted from prompt ANCHOR D)
"""

# ISO 639-1 → language name in English (used in LLM prompts)
LANGUAGE_NAMES: dict[str, str] = {
    'ja': 'Japanese',
    'en': 'English',
    'zh': 'Chinese',
    'ko': 'Korean',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'pt': 'Portuguese',
    'it': 'Italian',
    'ar': 'Arabic',
    'ru': 'Russian',
}

# Target-language-specific typography rules.
# These are injected into translation/proofreading prompts via {typography_rules}.
# Currently only Russian is defined — add other target languages here as needed.
TYPOGRAPHY_RULES: dict[str, str] = {
    'ru': r"""### [ANCHOR D: BINARY TEXT PHYSICS & TYPOGRAPHY]

**CRITICAL ALGORITHM.** The text always exists in one of two states:
- State [SOUND]: Text spoken by a character.
- State [SILENCE]: Text narrated by the author.

Segment every sentence. Determine what is spoken and what is authorial explanation.

#### TRIGGER OPERATOR `─` (U+2500)

The symbol `─` (U+2500) is the sole separator between states [SOUND] and [SILENCE]. Inside paragraphs and sentences – AS WELL.
*   Place `─` **every time** the source of the text changes within a paragraph (speech started, speech interrupted by author, speech resumed).
*   Every new speech segment must launch with `─`, in a new paragraph.
*   *Rule:* If a Character speaks, and then the Author narrates – `─` must stand between them.

#### INTERRUPTION LOGIC

If speech cuts off mid-word or on a pause:
*   Mark interrupted phrases, sudden cut-offs, or trailing offs with an ellipsis `…`.
*   If a character's speech is broken into multiple paragraphs, each paragraph (except the first) requires starting with `─ … [text]`.
*   **Speech Cut-off:** Marked by an ellipsis `…`; continuation of the interrupted phrase after a pause/remark always starts with `─ …`.
    *   *Example:* `─ Я не… ─ он запнулся. ─ …не знаю.`

#### STATE [SOUND] (Speech Rules)

*   Every new speech segment must launch with `─`, in a new paragraph.
*   **Quotation Marks:** Strictly forbidden for framing speech.
*   **Internal Objects:** Thoughts/inscriptions inside speech are highlighted with `«...»`.
*   **Internal Dash:** Use `–` (En-dash) **only** for pauses within a ***continuous*** flow of speech by one character.
    *   *Prohibition:* Never use `–` or `—` to separate author's words.

#### FORMATTING STANDARDS (Special Symbols)

*   **Thoughts, Quotes, Inscriptions, and Titles:** Strictly guillemets (chevrons) `«...»`. Nested – `«„..."»`.
*   **Internal Dash:** If it is not a boundary between Sound and Silence – use **ONLY** the en-dash (`–`).
    *   *Rule:* The em-dash (`—`) is forbidden everywhere.
*   **Indirect Speech (Fallback):** If unsure whether it is direct speech or a thought — use indirect speech (author's text) without quotation marks and without operators.

#### NON-STANDARD COMMS (Special Formats)

If the source contains **exotic communication** (telepathy, chat messages, AI voice, system notifications) highlighted by the author with **special graphic markers** (italics without quotes; brackets `[]`, `{}`, `<>`; etc.), then:
*   **Preserve Markers:** DO NOT CHANGE brackets or styles to dashes/quotes. Keep the framing as in the original.
*   **No Attribution:** DO NOT ADD quotation marks to such structures if they were not in the original, and do not use the speech operator `─` (since this is not spoken aloud).
*   **Translate Content:** Text inside markers is translated into {target_lang_name}.

#### CONTROL LOGIC

Before placing ANY dash, check the State on the Left and Right:

1. [SOUND]   <-> [SILENCE] : Use `─` (Operator). (Boundary switch).
2. [SILENCE] <-> [SOUND]   : Use `─` (Operator). (Boundary switch).
3. [SOUND]   <-> [SOUND]   : Use `–` (En-dash). (Internal pause in speech).
4. [SILENCE] <-> [SILENCE] : Use `–` (En-dash). (Internal pause in narration).

*Avoid the construction `, –` for internal pauses. Rephrase the sentence if necessary to use only the En-dash (`–`) without a preceding comma, or use alternative punctuation.*""",
}


def get_language_name(code: str) -> str:
    """Get human-readable language name for an ISO 639-1 code.

    Returns the code itself if not found in the mapping.
    """
    return LANGUAGE_NAMES.get(code, code)


def get_typography_rules(target_lang: str) -> str:
    """Get typography rules for the target language.

    Returns empty string if no rules defined for the given language.
    """
    return TYPOGRAPHY_RULES.get(target_lang, '')
```

**Обрати внимание:** Текст ANCHOR D в `TYPOGRAPHY_RULES['ru']` содержит **один** плейсхолдер `{target_lang_name}` (в секции NON-STANDARD COMMS: "translated into {target_lang_name}"). Это **не ошибка** — он будет подставлен в `orchestrator.py` после основной подстановки `{typography_rules}`.

**Критерии приёмки:**
- [ ] Файл `src/book_translator/languages.py` существует
- [ ] `from book_translator.languages import get_language_name, get_typography_rules` работает без ошибок
- [ ] `get_language_name('ja')` возвращает `'Japanese'`
- [ ] `get_typography_rules('ru')` возвращает строку, содержащую `ANCHOR D`
- [ ] `get_typography_rules('en')` возвращает пустую строку
- [ ] `pytest` проходит

---

### Фаза 2: Рефакторинг промптов

#### [x] LANG-2: Извлечь ANCHOR D из промптов, заменить на `{typography_rules}`

**Цель:** Устранить дублирование ANCHOR D (~57 строк, скопированных идентично в 2 промптах) и подготовить для подстановки языко-зависимых правил.

**Файлы:**
- `src/book_translator/default_prompts.py` — `TRANSLATION_PROMPT` и `PROOFREADING_PROMPT`
- `prompts/translation.txt`
- `prompts/proofreading.txt`
- `src/book_translator/orchestrator.py` — `_run_single_worker()`

**Что сделать:**

1. **В `TRANSLATION_PROMPT`** (и `prompts/translation.txt`): заменить весь блок ANCHOR D (от `### [ANCHOR D: BINARY TEXT PHYSICS & TYPOGRAPHY]` до конца секции перед `---` на строке 121) **одним плейсхолдером**:
   ```
   {typography_rules}
   ```
   То есть строки 65-121 (включительно, 57 строк) заменяются на одну строку `{typography_rules}`.

2. **В `PROOFREADING_PROMPT`** (и `prompts/proofreading.txt`): точно такая же замена — весь блок ANCHOR D (строки 317-371) заменяется на `{typography_rules}`.

3. **В `orchestrator.py`**, функция `_run_single_worker()`, строка 74 — добавить `.replace('{typography_rules}', typography_rules_str)` в цепочку подстановок:
   ```python
   final_prompt = prompt_template.replace('{text}', chunk_content).replace('{glossary}', glossary_str).replace('{style_guide}', style_guide_str).replace('{previous_context}', previous_context).replace('{world_info}', world_info_str).replace('{typography_rules}', typography_rules_str)
   ```

4. **В `_run_single_worker()`**: добавить параметр `typography_rules_str: str = ""` (после `world_info_str`).

5. **В `_run_workers_pooled()`**: добавить параметр `typography_rules_str: str = ""` и пробросить его в `_run_single_worker()`.

6. **В `_run_global_proofreading()`**: НЕ трогать — у global_proofreading свои компактные типографические правила в самом промпте.

7. **В `run_translation_process()`**:
   - Добавить импорт: `from book_translator.languages import get_typography_rules, get_language_name`
   - После строки 285 (`target_lang = ...`) добавить:
     ```python
     typography_rules = get_typography_rules(target_lang)
     ```
   - Передать `typography_rules_str=typography_rules` во все вызовы `_run_workers_pooled()` (этапы discovery, translation, proofreading). На этапе discovery `typography_rules` не используется промптом (в TERM_DISCOVERY нет `{typography_rules}`), но подстановка безвредна — `.replace()` на отсутствующий плейсхолдер ничего не делает.

**Критерии приёмки:**
- [ ] В `TRANSLATION_PROMPT` нет текста `ANCHOR D` — есть плейсхолдер `{typography_rules}`
- [ ] В `PROOFREADING_PROMPT` нет текста `ANCHOR D` — есть плейсхолдер `{typography_rules}`
- [ ] `grep -c "typography_rules" src/book_translator/default_prompts.py` возвращает 2
- [ ] `grep -c "typography_rules" src/book_translator/orchestrator.py` — не менее 5 (параметр + подстановка + передача)
- [ ] `prompts/translation.txt` и `prompts/proofreading.txt` синхронизированы с `default_prompts.py`
- [ ] `pytest` проходит

---

#### [x] LANG-3: Параметризовать названия языков в промптах (`{target_lang_name}`, `{source_lang_name}`)

**Цель:** Заменить все хардкоженные упоминания "Russian" и "source language" на плейсхолдеры, чтобы промпты работали с любой языковой парой.

**Файлы:**
- `src/book_translator/default_prompts.py` — все 4 промпта
- `prompts/translation.txt`
- `prompts/proofreading.txt`
- `prompts/global_proofreading.txt`
- `prompts/term_discovery.txt`
- `src/book_translator/orchestrator.py`

**Что сделать:**

##### A. `TRANSLATION_PROMPT` (и `prompts/translation.txt`)

Заменить следующие строки (номера строк приблизительные — ориентируйся на контекст):

1. Заголовок (строка 14):
   - `# SYSTEM PROTOCOL: RUSSIAN LITERARY ADAPTATION` → `# SYSTEM PROTOCOL: {target_lang_name_upper} LITERARY ADAPTATION`
   **ВАЖНО:** Вместо использования нового плейсхолдера `{target_lang_name_upper}`, просто замени на нейтральную формулировку:
   - `# SYSTEM PROTOCOL: LITERARY ADAPTATION` → оставить без языка в заголовке
   **РЕШЕНИЕ:** Заменить на `# SYSTEM PROTOCOL: LITERARY ADAPTATION ({target_lang_name})`

2. Keywords (строка 17):
   - `Russian_Literary_Syntax` → `{target_lang_name}_Literary_Syntax` — **НЕТ**, keywords — это priming-токены, не плейсхолдеры. Заменить:
   - `Russian_Literary_Syntax` → `Literary_Syntax`

3. Core Objective (строки 20-21):
   - `"professional literary translator for whom Russian is the native language"` → `"professional literary translator for whom {target_lang_name} is the native language"`
   - `"transform the source text into Russian text"` → `"transform the source text into {target_lang_name} text"`
   - `"reads as if it were originally created by a Russian author"` → `"reads as if it were originally created by a native {target_lang_name} author"`
   - `"for a general Russian reader"` → `"for a general {target_lang_name}-speaking reader"`

4. ANCHOR A (строка 48):
   - `"the Russian version must contain"` → `"the {target_lang_name} version must contain"`

5. ANCHOR B (строки 51-55):
   - `"Russian literary norm"` → `"{target_lang_name} literary norm"`
   - `"Reconstruct the text as a native speaker would"` — оставить как есть (generic)
   - `"understandable to a Russian reader"` → `"understandable to a {target_lang_name}-speaking reader"`
   - `"not turning it into Russia"` → `"not transposing cultural realities"` (нейтральная формулировка)
   - **ВАЖНО:** Строка `"A Russian author with deep knowledge of the culture is clearly describing a foreign world"` → `"A native {target_lang_name} author with deep knowledge of the source culture is clearly describing a foreign world"`

6. ANCHOR C (строка 60):
   - `"correct Russian syntax"` → `"correct {target_lang_name} syntax"`

7. TASK (строка 125):
   - `"Translate the following Source Fragment into Russian"` → `"Translate the following Source Fragment into {target_lang_name}"`

8. OUTPUT FILTERS — TYPOGRAPHY LOGIC (строки 156-157):
   - `"Do not use quotation marks for spoken speech"` — оставить (это будет дублировать typography_rules, но это guardrail)

9. OUTPUT INSTRUCTION (строка 165):
   - `"Provide the Russian version stream"` → `"Provide the {target_lang_name} version stream"`

##### B. `PROOFREADING_PROMPT` (и `prompts/proofreading.txt`)

1. Заголовок:
   - `# SYSTEM PROTOCOL: RUSSIAN LITERARY PROOFREADING & POLISHING` → `# SYSTEM PROTOCOL: LITERARY PROOFREADING & POLISHING ({target_lang_name})`

2. Keywords:
   - `Russian_Literary_Syntax` → `Literary_Syntax`

3. Core Objective (строка 277-278):
   - `"professional literary editor for whom Russian is the native language"` → `"professional literary editor for whom {target_lang_name} is the native language"`
   - `"an existing Russian translation"` → `"an existing {target_lang_name} translation"`
   - `"master of Russian literature"` → `"master of {target_lang_name} literature"`

4. ANCHOR C (строка 311-312):
   - `"correct Russian syntax"` → `"correct {target_lang_name} syntax"`
   - `"The resulting Russian text"` → `"The resulting {target_lang_name} text"`

5. TASK (строка 376):
   - `"Proofread and polish the following Russian text"` → `"Proofread and polish the following {target_lang_name} text"`

6. OUTPUT INSTRUCTION (строка 415):
   - `"Provide the polished Russian version"` → `"Provide the polished {target_lang_name} version"`

##### C. `GLOBAL_PROOFREADING_PROMPT` (и `prompts/global_proofreading.txt`)

1. Строка 418:
   - `"expert Russian literary editor"` → `"expert {target_lang_name} literary editor"`
   - `"translated text"` — оставить как есть

##### D. `TERM_DISCOVERY_PROMPT` (и `prompts/term_discovery.txt`)

Пока **НЕ** трогать — этот промпт будет полностью переработан в LANG-4.

##### E. `orchestrator.py`

В функции `_run_single_worker()`, в цепочку `.replace()` на строке 74 добавить:
```python
.replace('{target_lang_name}', target_lang_name).replace('{source_lang_name}', source_lang_name)
```

Параметры `target_lang_name: str = "Russian"` и `source_lang_name: str = "Japanese"` добавить в сигнатуры:
- `_run_single_worker()`
- `_run_workers_pooled()`
- `_run_global_proofreading()` (только `target_lang_name`)

В `run_translation_process()` вычислить:
```python
target_lang_name = get_language_name(target_lang)
source_lang_name = get_language_name(source_lang)
```
И передать во все вызовы `_run_workers_pooled()` и `_run_global_proofreading()`.

Для `_run_global_proofreading()` — добавить `.replace('{target_lang_name}', target_lang_name)` в подстановку промпта (строка ~147-150).

**Критерии приёмки:**
- [ ] `grep -c "Russian" src/book_translator/default_prompts.py` — ровно 0
- [ ] `grep -c "{target_lang_name}" src/book_translator/default_prompts.py` — не менее 10
- [ ] `grep -c "target_lang_name" src/book_translator/orchestrator.py` — не менее 5
- [ ] Все 4 файла `prompts/*.txt` синхронизированы
- [ ] `pytest` проходит

---

#### [x] LANG-4: Сделать TERM_DISCOVERY_PROMPT языко-нейтральным

**Цель:** Промпт discovery должен работать с любым исходным языком. Заменить хардкод "ru"/"jp" в JSON-ключах на "source"/"target"/"romanization", убрать японо-специфичные примеры.

**Файлы:**
- `src/book_translator/default_prompts.py` — `TERM_DISCOVERY_PROMPT`
- `prompts/term_discovery.txt`

**Что сделать:**

1. **Добавить плейсхолдеры.** В начало секции I добавить контекст:
   ```
   **0. Контекст:**
   Ты анализируешь текст на **{source_lang_name}** языке. Термины будут переведены на **{target_lang_name}** язык.
   ```

2. **Секция II — ПРИНЦИПЫ АНАЛИЗА.** Заменить японо-специфичные примеры на универсальные:

   Текущие примеры:
   ```
   *   **Имена и фамилии:** `アイズ・ヴァレンシュタイン` (Айз Валенштайн), `アリア` (Ариа).
   *   **Уникальные названия мест:** `氷結の牢獄` (Ледяная тюрьма).
   ```
   Заменить на:
   ```
   *   **Имена и фамилии:** Имена персонажей на языке оригинала с транскрипцией/переводом.
   *   **Уникальные названия мест:** Названия локаций, специфичные для мира произведения.
   *   **Названия предметов, навыков, рас:** Если они уникальны для мира.
   ```

   Текущие примеры игнорирования:
   ```
   *   **Звукоподражания и ономатопея:** `ルンパカ` (rumpaka), `ぴちゃぴちゃ` (пича-пича), `アハハ` (ахаха). Это шум, а не термины.
   *   **Междометия и выкрики:** `えいや！` (эйя!).
   *   **Общеупотребительные слова:** `冒険者` (авантюрист), `剣` (меч), `魔法` (магия), `姉妹` (сестры), `怪物` (монстр). Не добавляй их, даже если они написаны катаканой.
   ```
   Заменить на:
   ```
   *   **Звукоподражания и ономатопея:** Любые звукоподражания на языке оригинала. Это шум, а не термины.
   *   **Междометия и выкрики:** Эмоциональные восклицания без семантической нагрузки.
   *   **Общеупотребительные слова:** Слова типа «авантюрист», «меч», «магия», «сёстры», «монстр». Они описывают мир, но не являются уникальными терминами, требующими фиксации.
   ```

3. **Секция III — РАБОЧИЙ ПРОЦЕСС.** Заменить ключи в инструкции:
   - `"Заполни `name` (с `ru`, `jp`, `romaji`)"` → `"Заполни `name` (с `source`, `target`, `romanization`)"`
   - `"Поле `romaji` критически важно для создания ID"` → `"Поле `romanization` критически важно для создания ID"`

4. **Секция V — ФОРМАТ ВЫВОДА.** Полностью переписать JSON-пример:

   ```json
   {
     "characters": {
       "example_character_id": {
         "name": {
           "source": "Имя на языке оригинала",
           "target": "Перевод/транскрипция имени",
           "romanization": "Romanized form"
         },
         "aliases": [],
         "description": "Краткое описание персонажа на основе текста.",
         "context": "В какой ситуации этот персонаж появляется в анализируемом фрагменте.",
         "characteristics": {
           "gender": "М/Ж/Неизвестно",
           "affiliation": "Принадлежность к группе/организации",
           "level": null,
           "race": "Раса персонажа"
         }
       }
     },
     "terminology": {},
     "expressions": {}
   }
   ```

**Критерии приёмки:**
- [ ] `grep -c '"jp"' src/book_translator/default_prompts.py` — 0 (в промпте TERM_DISCOVERY нет ключа "jp")
- [ ] `grep -c '"ru"' src/book_translator/default_prompts.py` — 0 (в промпте нет ключа "ru")
- [ ] `grep "{source_lang_name}" src/book_translator/default_prompts.py` — не менее 1
- [ ] `grep "{target_lang_name}" src/book_translator/default_prompts.py` — не менее 1 (внутри TERM_DISCOVERY)
- [ ] JSON-пример в промпте использует ключи `"source"`, `"target"`, `"romanization"`
- [ ] `prompts/term_discovery.txt` синхронизирован
- [ ] `pytest` проходит

---

### Фаза 3: Рефакторинг Python-кода

#### [x] LANG-5: Рефакторинг `term_collector.py` — динамические ключи вместо "ru"/"jp"

**Цель:** Код должен работать с новыми ключами `"source"`/`"target"`/`"romanization"` из JSON-ответов LLM, сохраняя обратную совместимость со старым форматом.

**Файлы:**
- `src/book_translator/term_collector.py`

**Что сделать:**

1. **Функция `_edit_term()` (строка 42).** Заменить:
   ```python
   for key in ["ru", "jp", "romaji"]:
       new_val = input(f"  name.{key} (Enter, чтобы оставить '{term_data['name'].get(key, '')}'): ").strip()
       if new_val: term_data['name'][key] = new_val
   ```
   на:
   ```python
   for key in ["source", "target", "romanization"]:
       new_val = input(f"  name.{key} (Enter, чтобы оставить '{term_data['name'].get(key, '')}'): ").strip()
       if new_val: term_data['name'][key] = new_val
   ```

2. **Функция `present_for_confirmation()` (строки 80-81).** Заменить:
   ```python
   jp_name = term_data.get('name', {}).get('jp') or term_data.get('term_jp', 'N/A')
   ru_name = term_data.get('name', {}).get('ru') or term_data.get('term_ru', 'N/A')
   system_logger.info(f"...\n  JP: {jp_name}\n  RU: {ru_name}\n...")
   ```
   на:
   ```python
   source_name = term_data.get('name', {}).get('source') or term_data.get('term_source', 'N/A')
   target_name = term_data.get('name', {}).get('target') or term_data.get('term_target', 'N/A')
   system_logger.info(f"...\n  Source: {source_name}\n  Target: {target_name}\n...")
   ```

3. **Функция `update_glossary_file()` (строки 122-123).** Заменить:
   ```python
   term_jp = term_data.get("name", {}).get("jp", "")
   term_ru = term_data.get("name", {}).get("ru", "")
   if term_jp and term_ru:
       db.add_term(db_path, term_jp, term_ru, source_lang, target_lang)
   ```
   на:
   ```python
   term_source = term_data.get("name", {}).get("source", "")
   term_target = term_data.get("name", {}).get("target", "")
   if term_source and term_target:
       db.add_term(db_path, term_source, term_target, source_lang, target_lang)
   ```

4. **Функция `save_approved_terms()` (строки 165-170).** Заменить цепочку fallback:
   ```python
   term_source = term_data.get('name', {}).get('jp') or \
                 term_data.get('term_jp') or \
                 term_data.get('term_source') or \
                 term_id
   term_target = term_data.get('name', {}).get('ru') or \
                 term_data.get('term_ru') or \
                 term_data.get('term_target', '')
   ```
   на (новые ключи первыми, старые — fallback):
   ```python
   term_source = term_data.get('name', {}).get('source') or \
                 term_data.get('name', {}).get('jp') or \
                 term_data.get('term_source') or \
                 term_data.get('term_jp') or \
                 term_id
   term_target = term_data.get('name', {}).get('target') or \
                 term_data.get('name', {}).get('ru') or \
                 term_data.get('term_target') or \
                 term_data.get('term_ru', '')
   ```

5. **Функция `approve_via_tsv()` (строки 190-195).** Точно такая же замена fallback-цепочки, как в пункте 4:
   ```python
   term_source = term_data.get('name', {}).get('source') or \
                 term_data.get('name', {}).get('jp') or \
                 term_data.get('term_source') or \
                 term_data.get('term_jp') or \
                 term_id
   term_target = term_data.get('name', {}).get('target') or \
                 term_data.get('name', {}).get('ru') or \
                 term_data.get('term_target') or \
                 term_data.get('term_ru', '')
   ```

**Критерии приёмки:**
- [ ] `grep -n "get('jp')" src/book_translator/term_collector.py` — 0 прямых обращений (только в fallback-цепочках `save_approved_terms` и `approve_via_tsv`)
  Уточнение: в fallback-цепочках `get('jp')` допустим, но в `_edit_term` и `present_for_confirmation` — 0
- [ ] Основные ключи доступа — `'source'`, `'target'`, `'romanization'`
- [ ] `pytest` проходит

---

#### [x] LANG-6: Рефакторинг `glossary_manager.py` — убрать `term_jp`/`term_ru` хардкод

**Цель:** `glossary_manager.py` должен использовать `term_source`/`term_target` как основные ключи, сохраняя fallback для обратной совместимости.

**Файлы:**
- `src/book_translator/glossary_manager.py`

**Что сделать:**

В функции `generate_approval_tsv()` (строки 66-67), заменить:
```python
source = term.get('term_jp', term.get('term_source', ''))
target = term.get('term_ru', term.get('term_target', ''))
```
на (приоритет новым ключам):
```python
source = term.get('term_source') or term.get('term_jp', '')
target = term.get('term_target') or term.get('term_ru', '')
```

**Критерии приёмки:**
- [ ] `grep "'term_jp'" src/book_translator/glossary_manager.py` — только в fallback-позиции
- [ ] `grep "'term_source'" src/book_translator/glossary_manager.py` — присутствует
- [ ] `pytest` проходит

---

#### [x] LANG-7: Параметризовать язык в `convert_to_epub.py`

**Цель:** EPUB должен использовать правильный языковой код, а не хардкоженный `'ru'`.

**Файлы:**
- `src/book_translator/convert_to_epub.py`

**Что сделать:**

1. Добавить параметр `language: str = 'ru'` в функцию `convert_txt_to_epub()`:
   ```python
   def convert_txt_to_epub(
       input_file: Path,
       output_file: Path,
       title: str,
       author: str = '',
       language: str = 'ru',
   ) -> None:
   ```

2. Заменить хардкоженные значения:
   - Строка 51: `book.set_language('ru')` → `book.set_language(language)`
   - Строка 73: `lang='ru'` → `lang=language`

**Критерии приёмки:**
- [ ] `grep "'ru'" src/book_translator/convert_to_epub.py` — только в значении по умолчанию параметра `language='ru'`
- [ ] `pytest` проходит

---

### Фаза 4: Стайлгайды

#### [x] LANG-8: Создать бандлированные стайлгайды для популярных языковых пар

**Цель:** При `init` пользователь получает готовый стайлгайд для своей языковой пары, а не пустой шаблон.

**Файлы:**
- **Переименовать/переместить:** `data/style_guide.md` → `data/style_guides/ja_ru.md`
- **Создать:** `data/style_guides/en_ru.md`
- **Создать:** `data/style_guides/zh_ru.md`
- **Создать:** `data/style_guides/ko_ru.md`
- **Создать:** `data/style_guides/default.md`

**Что сделать:**

1. **Создать директорию** `data/style_guides/`.

2. **Переместить** `data/style_guide.md` → `data/style_guides/ja_ru.md` (содержимое без изменений).

3. **Создать `data/style_guides/en_ru.md`:**
   ```markdown
   ## 1. ОСОБЕННОСТИ АНГЛИЙСКОГО ЯЗЫКА И ИХ АДАПТАЦИЯ

   ### 1.1. Пунктуация
   *   **Прямая речь `"..."`:** Передавать с помощью оператора звука `─` (U+2500) и прямой речи.
       *   `"Hello," he said.` -> `─ Привет, ─ сказал он.`
   *   **Мысли, названия `'...'` или курсив:** Передавать с помощью кавычек-«ёлочек» (`«...»`).
       *   `He was known as 'The Rookie'.` -> `Его называли «Новобранцем».`
   *   **Многоточие `...`:** Заменять на стандартное русское многоточие (`...`), один символ `…` или три точки.
   *   **Длинное тире `—` (em-dash):** В русском тексте em-dash запрещён. Для границ речи использовать оператор `─` (U+2500), для пауз — тире `–` (en-dash).

   ### 1.2. Перевод имен и названий
   *   **Транскрипция:** Английские имена транскрибируются по стандартным правилам русской практической транскрипции.
       *   `Arthur` → `Артур`, `William` → `Уильям`, `Catherine` → `Кэтрин`.
   *   **Говорящие имена:** Если имя несёт смысловую нагрузку (Shadowblade, Ironforge), решение о транскрипции vs. переводе принимается на основе глоссария и контекста.
   *   **Приоритет глоссария:** Если имя есть в глоссарии, использовать глоссарную форму.

   ---

   ## 2. СТИЛЕВОЙ ГАЙД И ПРАВИЛА

   ### 2.1. Общие правила
   *   **Литературность:** Перевод должен быть художественным, а не дословным.
   *   **Чистота языка:** Текст должен быть на чистом русском языке без неоправданных англицизмов.
   *   **Тире в диалогах:** Использовать оператор звука (`─`, U+2500).
   *   **Буква «ё»:** Обязательно использовать.
   *   **Изображения:** Ключевую фразу `--- :11image11 ---` оставлять без изменений.

   ### 2.2. Обращения
   *   **Mr./Mrs./Ms.:** Адаптировать как «господин/госпожа» или опускать в зависимости от контекста и степени формальности.
   *   **Sir/Ma'am:** «Сэр/мэм» в фэнтези; «господин/госпожа» в реалистичном сеттинге.
   *   **Титулы (Lord, King, Captain):** Переводить стандартными русскими эквивалентами: лорд, король, капитан.

   ### 2.3. Структура текста
   *   **Формирование абзацев:** Объединять связанные предложения в логичные абзацы по нормам русской литературы.
   *   **Художественная адаптация:** Избегать дословного подстрочника. Использовать синонимы и сложные конструкции.
   *   **Плавность повествования:** Соединять короткие предложения в длинные и плавные.
   ```

4. **Создать `data/style_guides/zh_ru.md`:**
   ```markdown
   ## 1. ОСОБЕННОСТИ КИТАЙСКОГО ЯЗЫКА И ИХ АДАПТАЦИЯ

   ### 1.1. Пунктуация
   *   **Прямая речь `「...」` или `"..."`:** Передавать с помощью оператора звука `─` (U+2500).
   *   **Книжные кавычки `『...』` или `'...'`:** Передавать кавычками-«ёлочками» (`«...»`).
   *   **Китайское многоточие `……` (шесть точек):** Заменять на стандартное русское многоточие (`...`).
   *   **Разделительная точка `·`:** Используется в китайских именах между фамилией и именем. В транскрипции ставить пробел или точку по контексту.

   ### 1.2. Перевод имен и названий
   *   **Транскрипция:** Китайские имена транскрибируются по системе Палладия.
       *   `张伟` → `Чжан Вэй`, `李明` → `Ли Мин`, `王` → `Ван`.
   *   **Порядок имён:** В китайском сначала фамилия, потом имя. Сохранять китайский порядок: Чжан Вэй (не Вэй Чжан).
   *   **Приоритет глоссария:** Если имя есть в глоссарии, использовать глоссарную форму.

   ---

   ## 2. СТИЛЕВОЙ ГАЙД И ПРАВИЛА

   ### 2.1. Общие правила
   *   **Литературность:** Перевод должен быть художественным.
   *   **Тире в диалогах:** Использовать оператор звука (`─`, U+2500).
   *   **Буква «ё»:** Обязательно использовать.
   *   **Изображения:** Ключевую фразу `--- :11image11 ---` оставлять без изменений.

   ### 2.2. Единицы измерения и реалии
   *   **Чэн (丈), чи (尺), ли (里):** Оставлять как «чжан», «чи», «ли» или переводить в метрическую систему — в зависимости от сеттинга и глоссария.
   *   **Титулы:** Переводить стандартными русскими эквивалентами, если в глоссарии нет особого варианта.

   ### 2.3. Структура текста
   *   **Формирование абзацев:** Объединять предложения в логичные абзацы.
   *   **Художественная адаптация:** Избегать дословного подстрочника.
   ```

5. **Создать `data/style_guides/ko_ru.md`:**
   ```markdown
   ## 1. ОСОБЕННОСТИ КОРЕЙСКОГО ЯЗЫКА И ИХ АДАПТАЦИЯ

   ### 1.1. Пунктуация
   *   **Прямая речь `"..."`:** Передавать с помощью оператора звука `─` (U+2500).
   *   **Мысли, названия `'...'`:** Передавать кавычками-«ёлочками» (`«...»`).
   *   **Многоточие:** Заменять на стандартное русское многоточие (`...`).

   ### 1.2. Перевод имен и названий
   *   **Транскрипция:** Корейские имена транскрибируются по системе Концевича.
       *   `김` → `Ким`, `이` → `Ли`, `박` → `Пак`, `정` → `Чон`.
   *   **Порядок имён:** В корейском сначала фамилия, потом имя. Сохранять корейский порядок.
   *   **Приоритет глоссария:** Если имя есть в глоссарии, использовать глоссарную форму.

   ---

   ## 2. СТИЛЕВОЙ ГАЙД И ПРАВИЛА

   ### 2.1. Общие правила
   *   **Литературность:** Перевод должен быть художественным.
   *   **Тире в диалогах:** Использовать оператор звука (`─`, U+2500).
   *   **Буква «ё»:** Обязательно использовать.
   *   **Изображения:** Ключевую фразу `--- :11image11 ---` оставлять без изменений.

   ### 2.2. Обращения и речевой этикет
   *   **Именные суффиксы (-시, хонорифики):** Корейская система вежливости сложная. Адаптировать через «Вы/ты», «господин/госпожа», или опускать по контексту.
   *   **Уровни речи (존댓말/반말):** Передавать через выбор «Вы» vs. «ты» и общий тон фразы.

   ### 2.3. Структура текста
   *   **Формирование абзацев:** Объединять предложения в логичные абзацы.
   *   **Художественная адаптация:** Избегать дословного подстрочника.
   ```

6. **Создать `data/style_guides/default.md`** (универсальный шаблон для неизвестных пар):
   ```markdown
   ## Стайлгайд перевода

   Этот файл — шаблон стайлгайда. Заполните его правилами, специфичными для вашей языковой пары.

   ### 1. Пунктуация
   *   Опишите, как адаптировать пунктуацию исходного языка.
   *   **Тире в диалогах:** Использовать оператор звука (`─`, U+2500).

   ### 2. Перевод имён и названий
   *   Укажите систему транскрипции для имён из исходного языка.
   *   **Приоритет глоссария:** Если имя есть в глоссарии, использовать глоссарную форму.

   ### 3. Общие правила
   *   **Литературность:** Перевод должен быть художественным, а не дословным.
   *   **Буква «ё»:** Обязательно использовать.

   ### 4. Структура текста
   *   Объединять предложения в логичные абзацы.
   *   Избегать дословного подстрочника.
   ```

7. **Удалить** `data/style_guide.md` (заменён на `data/style_guides/ja_ru.md`).

**Критерии приёмки:**
- [ ] Директория `data/style_guides/` существует с файлами: `ja_ru.md`, `en_ru.md`, `zh_ru.md`, `ko_ru.md`, `default.md`
- [ ] Содержимое `data/style_guides/ja_ru.md` идентично бывшему `data/style_guide.md`
- [ ] Файл `data/style_guide.md` больше не существует
- [ ] `pytest` проходит

---

#### [x] LANG-9: Обновить `init` команду — копировать правильный стайлгайд при инициализации

**Цель:** При `book-translator init` копировать бандлированный стайлгайд для выбранной языковой пары.

**Файлы:**
- `src/book_translator/commands/init_cmd.py`

**Что сделать:**

1. **Добавить импорт** в начало файла:
   ```python
   import shutil
   ```

2. **Добавить функцию** для поиска бандлированного стайлгайда:
   ```python
   def _find_bundled_style_guide(source_lang: str, target_lang: str) -> Path | None:
       """Find bundled style guide for the given language pair."""
       style_guides_dir = Path(__file__).parent.parent.parent.parent / 'data' / 'style_guides'
       # Try exact match first: ja_ru.md
       exact = style_guides_dir / f'{source_lang}_{target_lang}.md'
       if exact.is_file():
           return exact
       # Fall back to default
       default = style_guides_dir / 'default.md'
       if default.is_file():
           return default
       return None
   ```

   **ВАЖНО:** Путь `Path(__file__).parent.parent.parent.parent / 'data'` ведёт из `src/book_translator/commands/init_cmd.py` → `src/book_translator/commands` → `src/book_translator` → `src` → корень пакета. Это работает в dev-установке (`pip install -e .`). Для продакшена нужен `importlib.resources`, но на данном этапе — `Path(__file__)` достаточно.

   **Альтернативный подход (надёжнее):** Использовать `importlib.resources`:
   ```python
   from importlib.resources import files as _resource_files

   def _find_bundled_style_guide(source_lang: str, target_lang: str) -> Path | None:
       """Find bundled style guide for the given language pair."""
       try:
           style_guides_dir = Path(str(_resource_files('book_translator'))) / '..' / '..' / 'data' / 'style_guides'
           style_guides_dir = style_guides_dir.resolve()
       except Exception:
           style_guides_dir = Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'style_guides'
       exact = style_guides_dir / f'{source_lang}_{target_lang}.md'
       if exact.is_file():
           return exact
       default = style_guides_dir / 'default.md'
       if default.is_file():
           return default
       return None
   ```

   **РЕШЕНИЕ:** Используй простой вариант с `Path(__file__)` — это editable install, он работает. Путь проверяй `assert`.

3. **Обновить `STYLE_GUIDE_TEMPLATE`** — сделать его запасным вариантом (на случай, если бандл не найден):
   ```python
   STYLE_GUIDE_TEMPLATE = '''# Стайлгайд перевода

   ## Общие правила
   - Литературный перевод, не дословный
   - Использовать оператор звука (`─`, U+2500) для диалогов
   - Обязательно использовать букву «ё»
   '''
   ```

4. **В `run_init()`** (строка 64), заменить:
   ```python
   (series_dir / 'style_guide.md').write_text(STYLE_GUIDE_TEMPLATE, encoding='utf-8')
   ```
   на:
   ```python
   bundled_guide = _find_bundled_style_guide(args.source_lang, args.target_lang)
   if bundled_guide:
       shutil.copy2(bundled_guide, series_dir / 'style_guide.md')
   else:
       (series_dir / 'style_guide.md').write_text(STYLE_GUIDE_TEMPLATE, encoding='utf-8')
   ```

**Критерии приёмки:**
- [ ] `book-translator init "test" --source-lang ja --target-lang ru` создаёт `style_guide.md` с содержимым из `data/style_guides/ja_ru.md`
- [ ] `book-translator init "test2" --source-lang en --target-lang ru` создаёт `style_guide.md` с содержимым из `data/style_guides/en_ru.md`
- [ ] `book-translator init "test3" --source-lang xx --target-lang ru` создаёт `style_guide.md` с содержимым из `data/style_guides/default.md` (или `STYLE_GUIDE_TEMPLATE` если бандл не найден)
- [ ] `pytest` проходит
- [ ] После тестирования — удалить созданные тестовые директории

---

#### [x] LANG-10: Создать шаблон-промпт для генерации кастомного стайлгайда

**Цель:** Пользователь, работающий с нестандартной языковой парой, должен иметь шаблон промпта для генерации стайлгайда через LLM.

**Файлы:**
- **Создать:** `docs/style_guide_prompt_template.md`

**Что сделать:**

Создать файл `docs/style_guide_prompt_template.md`:

```markdown
# Шаблон промпта для генерации стайлгайда

Используйте этот промпт с любой LLM (ChatGPT, Claude, Gemini) для генерации стайлгайда под вашу языковую пару.

## Промпт

```
Ты — эксперт по переводу с [ИСХОДНЫЙ ЯЗЫК] на русский язык.

Создай подробный стайлгайд для художественного перевода с [ИСХОДНЫЙ ЯЗЫК] на русский. Стайлгайд будет использоваться LLM-моделью при автоматическом переводе книг.

Структура стайлгайда:

## 1. ОСОБЕННОСТИ [ИСХОДНЫЙ ЯЗЫК] ЯЗЫКА И ИХ АДАПТАЦИЯ

### 1.1. Пунктуация
- Как адаптировать знаки прямой речи (кавычки, тире, скобки) из [ИСХОДНЫЙ ЯЗЫК] в русский формат
- Прямая речь в русском оформляется оператором звука `─` (U+2500), НЕ кавычками
- Мысли и названия — кавычки-«ёлочки» (`«...»`)
- Многоточие — стандартное русское (`...`)
- Как обрабатывать специфичные знаки препинания [ИСХОДНЫЙ ЯЗЫК]

### 1.2. Перевод имён и названий
- Какую систему транскрипции использовать для имён
- Порядок имени/фамилии
- Как обрабатывать «говорящие» имена
- Приоритет глоссария над транскрипцией

## 2. СТИЛЕВОЙ ГАЙД И ПРАВИЛА

### 2.1. Общие правила
- Художественный перевод, не дословный
- Тире в диалогах: оператор звука (`─`, U+2500)
- Буква «ё» обязательна
- Ключевую фразу `--- :11image11 ---` оставлять без изменений

### 2.2. Обращения и речевой этикет
- Как адаптировать формы вежливости [ИСХОДНЫЙ ЯЗЫК]
- Титулы и почётные обращения

### 2.3. Структура текста
- Объединение предложений в абзацы по нормам русской литературы
- Художественная адаптация

Приведи конкретные примеры для каждого пункта, используя формат:
`[пример на ИСХОДНЫЙ ЯЗЫК]` -> `[результат на русском]`
```

## Как использовать

1. Замените `[ИСХОДНЫЙ ЯЗЫК]` на нужный язык (например, «тайский», «турецкий»)
2. Выполните промпт в LLM
3. Сохраните результат в `style_guide.md` в корне вашей серии
4. При необходимости отредактируйте под ваши нужды
```

**Критерии приёмки:**
- [ ] Файл `docs/style_guide_prompt_template.md` существует
- [ ] Содержит промпт-шаблон с плейсхолдером `[ИСХОДНЫЙ ЯЗЫК]`
- [ ] Содержит инструкцию по использованию

---

### Фаза 5: Верификация

#### [x] LANG-11: Финальная верификация и grep-проверки

**Цель:** Убедиться, что все хардкоженные языковые зависимости устранены.

**Файлы:** все изменённые файлы

**Что сделать:**

Выполнить следующие проверки:

1. **Grep по "Russian" в промптах:**
   ```bash
   grep -rn "Russian" src/book_translator/default_prompts.py prompts/
   ```
   Ожидаемый результат: **0 вхождений**.

2. **Grep по хардкоженным "jp"/"ru" ключам в JSON-контексте term_collector:**
   ```bash
   grep -n "get('jp')\|get(\"jp\")" src/book_translator/term_collector.py
   ```
   Ожидаемый результат: только в fallback-цепочках `save_approved_terms` и `approve_via_tsv` (2 файловых позиции, для обратной совместимости).

3. **Grep по старому style_guide.md:**
   ```bash
   ls data/style_guide.md 2>/dev/null
   ```
   Ожидаемый результат: файл не существует.

4. **Grep по новым плейсхолдерам:**
   ```bash
   grep -c "{target_lang_name}" src/book_translator/default_prompts.py
   grep -c "{typography_rules}" src/book_translator/default_prompts.py
   grep -c "{source_lang_name}" src/book_translator/default_prompts.py
   ```
   Ожидаемый результат: `{target_lang_name}` ≥ 10, `{typography_rules}` = 2, `{source_lang_name}` ≥ 1.

5. **Полный прогон тестов:**
   ```bash
   pytest -v
   ```
   Ожидаемый результат: все тесты проходят.

6. **Проверка синхронизации промптов:**
   Визуально убедиться, что содержимое `prompts/translation.txt` совпадает с `TRANSLATION_PROMPT` (без обёртки `r"""..."""`). То же для остальных 3 промптов.

**Критерии приёмки:**
- [ ] Все 6 проверок пройдены
- [ ] `pytest` проходит
- [ ] Промпты синхронизированы

---

## ИТОГО

| # | ID | Фаза | Статус | Описание |
|---|---|---|---|---|
| 1 | LANG-1 | Инфраструктура | [x] | Создать `languages.py` |
| 2 | LANG-2 | Промпты | [x] | Извлечь ANCHOR D → `{typography_rules}` |
| 3 | LANG-3 | Промпты | [x] | Параметризовать "Russian" → `{target_lang_name}` |
| 4 | LANG-4 | Промпты | [x] | Сделать TERM_DISCOVERY языко-нейтральным |
| 5 | LANG-5 | Python-код | [x] | Рефакторинг `term_collector.py` |
| 6 | LANG-6 | Python-код | [x] | Рефакторинг `glossary_manager.py` |
| 7 | LANG-7 | Python-код | [x] | Параметризовать `convert_to_epub.py` |
| 8 | LANG-8 | Стайлгайды | [x] | Бандлированные стайлгайды |
| 9 | LANG-9 | Стайлгайды | [x] | Обновить `init` команду |
| 10 | LANG-10 | Документация | [x] | Шаблон для кастомного стайлгайда |
| 11 | LANG-11 | Верификация | [x] | Финальные grep-проверки и тесты |
