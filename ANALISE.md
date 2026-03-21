# Анализ кодовой базы book-translator

## Этап 1: Беглый анализ

### Файловая структура (корень проекта)

```
book-translator/
├── .claude/                    # Конфиг Claude Code
├── .sisyphus/                  # Стороннее состояние (gitignored)
├── __pycache__/                # ⚠ Локальный кэш в корне (не трекается git, но существует)
├── book_translator.egg-info/   # ⚠ Артефакт сборки (gitignored, не трекается)
├── data/                       # Бандлированные данные (style_guides/) + устаревшие файлы
├── docs/                       # 1 файл — шаблон style_guide
├── prompts/                    # Пользовательские промпты (4 файла + README.md)
├── src/book_translator/        # Основной код (22 модуля)
├── tests/                      # Тесты (16 файлов)
├── AGENTS.md                   # ⚠ Дубль CLAUDE.md/GEMINI.md
├── CLAUDE.md                   # ⚠ Дубль GEMINI.md
├── GEMINI.md                   # ⚠ Дубль CLAUDE.md
├── CHANGELOG.md                # ✅ Changelog
├── README.md                   # ✅ Документация
├── migrate_glossary.py         # ⚠ Одноразовый скрипт в корне
├── pyproject.toml              # ✅ Конфиг проекта
└── .tool-versions              # ✅ asdf конфиг
```

### Быстрые выводы

| Пункт | Статус |
|-------|--------|
| Структура `src/` layout | ✅ Корректно |
| Entry point в `pyproject.toml` | ✅ Корректно |
| Тесты покрывают основные модули | ✅ Покрытие нормальное |
| `__pycache__` в корне | ⚠ Локальный мусор (gitignored, не трекается) |
| `book_translator.egg-info/` | ⚠ Локальный артефакт (gitignored, не трекается) |
| Три дублирующих файла конфигурации агентов | ❌ Дублирование |
| Устаревшие файлы в `data/` | ❌ Мусор (3 устаревших файла рядом с актуальными) |
| Одноразовый скрипт `migrate_glossary.py` в корне | ❌ Мусор |

---

## Этап 2: Подробный анализ

### 2.1. Мёртвый код и неиспользуемые модули

#### `config.py` (23 строки) — бесполезная обёртка
```python
def load_config(series_root=None):
    if series_root is None:
        series_root = find_series_root()
    return _load_series_config(series_root)
```
**Проблема:** Этот модуль нигде не импортируется (ни в `src/`, ни в `tests/`). Он просто оборачивает `discovery.load_series_config()`.
**Решение:** Удалить `config.py`.

---

#### `main.py` (4 строки) — дубль entry point
```python
from book_translator.cli import main
if __name__ == '__main__':
    main()
```
**Проблема:** Entry point уже задан в `pyproject.toml` как `book_translator.cli:main`. Файл `main.py` не нужен.
**Решение:** Удалить `main.py`.

---

#### `diff_viewer.py` (84 строки) — не интегрирован
**Проблема:** Модуль реализует интерактивный просмотр правок вычитки (`show_proofreading_diffs()`), но нигде не импортируется и не вызывается в проекте. Вероятно, был создан для будущей функциональности, но не подключён.
**Решение:** Либо интегрировать в pipeline вычитки (этап 3.5 в `orchestrator.py`), либо удалить до востребования.

---

#### Мёртвые функции в `term_collector.py`

| Функция | Строки | Статус |
|---------|--------|--------|
| `collect_and_deduplicate_terms()` | 12–40 | Устаревшая. В production используется `collect_terms_from_responses()`. Вызывается только из тестов (`test_term_collector.py`). |
| `_edit_term()` | 42–66 | Устаревшая. Была частью интерактивного workflow, заменённого TSV-подходом. Вызывается только из `present_for_confirmation()` (строка 112), которая сама устаревшая. |
| `present_for_confirmation()` | 68–114 | Устаревшая. Заменена на `approve_via_tsv()`. Вызывается только из тестов. В `test_orchestrator.py` мокается через `@patch`, но сам orchestrator эту функцию больше не вызывает — т.е. моки бесполезны и тестируют несуществующий flow. |
| `update_glossary_file()` | 116–126 | Устаревшая. Заменена на `save_approved_terms()`. Вызывается только из тестов. |

**Решение:** Удалить все четыре функции. Обновить `test_term_collector.py` (удалить тесты). Обновить `test_orchestrator.py` (удалить бесполезные моки `present_for_confirmation`).

---

#### `convert_to_epub.py` — не подключён к CLI
**Проблема:** Модуль есть, но нет CLI-команды для EPUB-конвертации (в отличие от docx, который интегрирован в orchestrator.py). Модуль нигде не импортируется.
**Решение:** Добавить `--epub` флаг в CLI и подключить в orchestrator по аналогии с docx, или удалить модуль.

---

### 2.2. Монолитный `orchestrator.py` (570 строк)

Это самый большой и самый проблемный файл проекта.

**Проблемы:**
1. **God Object:** Файл содержит ВСЮ бизнес-логику pipeline: разбивку, discovery, перевод, вычитку, глобальную вычитку, финальную сборку, конвертацию.
2. **Огромная функция `run_translation_process()`** — 290+ строк с 4 вложенными этапами и hardcoded-логикой.
3. **Огромные списки параметров** — `_run_single_worker()` принимает 22 аргумента (строки 41–63), `_run_workers_pooled()` — 23 аргумента (строки 192–215). Это явный code smell.
4. **Дублирование:** Загрузка глоссария (`db.get_terms()` → `json.dumps()`) повторяется 4 раза.
5. **`_find_tool_versions_dir()`** — утилита для asdf, не имеющая отношения к оркестрации. Должна быть в `utils.py`.

**Решение:**
- Извлечь вызов `gemini-cli` в отдельный модуль `llm_runner.py` (или `gemini_runner.py`).
- Объединить параметры в dataclass (например, `WorkerConfig`).
- Извлечь сборку итогового файла в отдельную функцию/модуль.
- Вынести `_find_tool_versions_dir()` в `utils.py`.

---

### 2.3. Проблемы стиля кода

#### Устаревшие типы из `typing`
По convention проекта (Python 3.11+), нужно использовать `str | None` вместо `Optional[str]` и `dict`/`list` вместо `Dict`/`List`.

| Файл | Проблема |
|------|----------|
| `orchestrator.py` | `Dict`, `Any`, `List`, `Optional` из `typing` |
| `db.py` | `List`, `Dict`, `Optional`, `Any` из `typing` |
| `term_collector.py` | `Dict`, `Any`, `List`, `Optional` из `typing` |
| `glossary_manager.py` | `List`, `Dict`, `TextIO` из `typing` |
| `discovery.py` | `Optional` из `typing` |
| `config.py` | `Optional` из `typing` (если файл не удалён) |
| `path_resolver.py` | `Optional`, `Dict` из `typing` |
| `diff_viewer.py` | `Any` из `typing` (если файл не удалён) |
| `utils.py` | `Any` из `typing` |

**Решение:** Заменить на встроенные типы Python 3.11+. `TextIO` можно оставить — это не имеет встроенного аналога. `Any` из `typing` тоже оставить — встроенного аналога нет (до Python 3.12 где `type` statement).

---

#### `convert_to_docx.py` — использует `sys.exit()` в библиотечном коде
**Проблема:** Функция `convert_txt_to_docx()` вызывает `sys.exit(1)` при ошибках (5 вызовов: строки 15, 23, 63, 70, 77). Это недопустимо для библиотечного кода — оркестратор не сможет перехватить ошибку.
**Решение:** Заменить `sys.exit()` на исключения. Убрать `if __name__ == '__main__'` блок.

---

#### `proofreader.py` — собственный logger вместо общего
**Проблема:** Использует `logging.getLogger('system')` вместо `system_logger` из `logger.py`. Это непоследовательно.
**Решение:** Заменить на `from book_translator.logger import system_logger`.

---

### 2.4. Устаревшие файлы и мусор

| Файл/Директория | Причина | Действие |
|------------------|---------|----------|
| `__pycache__/` (корень) | Локальный кэш. Уже в `.gitignore`, не трекается git. | Удалить локально |
| `data/_glossary_old.json` (149 КБ) | Старый формат глоссария. Использовался `migrate_glossary.py` | Удалить |
| `data/_style_guide.md` (12 байт) | Содержит только текст «Style guide». Пустышка. | Удалить |
| `data/glossary.json` (3 байта) | Содержит `{}`. Пустой файл, старый формат. | Удалить |
| `data/world_info.md` (2.9 КБ) | Шаблон/референс. `init_cmd.py` создаёт `world_info.md` из константы `WORLD_INFO_TEMPLATE`, а не из этого файла. | Удалить (или переместить в `docs/` как референс) |
| `migrate_glossary.py` (63 строки) | Одноразовый скрипт миграции. Зависит от `data/_glossary_old.json`. | Удалить |

---

### 2.5. Дублирование AI-конфигов

| Файл | Размер | Содержимое |
|------|--------|------------|
| `CLAUDE.md` | 4384 байт | Инструкции для Claude Code |
| `GEMINI.md` | 4384 байт | **Идентичен** `CLAUDE.md` (1:1 копия) |
| `AGENTS.md` | 3185 байт | Сокращённая версия того же содержимого |

**Проблема:** Три файла с одной и той же информацией. `GEMINI.md` — точная копия `CLAUDE.md`.
**Решение:** Оставить один `AGENTS.md` как стандарт. Удалить `CLAUDE.md` и `GEMINI.md`, или сделать их символьными ссылками на `AGENTS.md`.
**Комментарий пользователя** К сожалению, не представляется возможным унифицировать системный инструкции, так как каждая LLM использует свой входной файл. Приходится хранить дубликаты с разными названиями.

---

### 2.6. Директория `data/` — пересмотр назначения

Текущее содержимое `data/`:
```
data/
├── _glossary_old.json    # устаревший (удалить)
├── _style_guide.md       # пустышка (удалить)
├── glossary.json          # пустой (удалить)
├── world_info.md          # ⚠ не используется в коде (init создаёт из константы)
└── style_guides/          # ✅ активно используется
    ├── default.md
    ├── en_ru.md
    ├── ja_ru.md
    ├── ko_ru.md
    └── zh_ru.md
```

**Статус интеграции:** Style guides в `data/style_guides/` **уже интегрированы** в команду `init`. Функция `_find_bundled_style_guide()` в `init_cmd.py` (строки 50–59) ищет файл `{source}_{target}.md` в `data/style_guides/` и копирует его при инициализации серии, с fallback на `default.md`.

После удаления трёх устаревших файлов и (опционально) `world_info.md`, директория `data/` будет содержать только актуальные `style_guides/`.

---

### 2.7. Директория `docs/` — минимальна

Содержит один файл `style_guide_prompt_template.md` (3268 байт). Этот файл — шаблон для LLM-генерации кастомных стайл-гайдов для новых языковых пар, не используемый в коде напрямую.

**Решение:** Оставить как есть. Файл полезен как документация для пользователя.
**Комментарий пользователя** Файл `release.md` уже удален.

---

### 2.8. `.gitignore` — неполный

Текущий `.gitignore`:
```
.sisyphus
text
translator/workspace/**
release.md
__pycache__
.state/
*.db-wal
*.db-shm
glossary.db
book_translator.egg-info/
```

**Отсутствуют:**
- `*.egg-info/` (обобщённый паттерн — сейчас есть только `book_translator.egg-info/`)
- `.pytest_cache/`
- `dist/`
- `build/`
- `*.pyc` (рекурсивно — `__pycache__` покрывает директории, но не одиночные `.pyc`)
- `.claude/`

**Примечание:** `book_translator.egg-info/` уже в `.gitignore` и не трекается git. `__pycache__/` в корне тоже не трекается. Эти файлы — только локальные артефакты.

---

## План по «причёсыванию»

### Приоритет 1: Удаление мусора (безрисковые изменения)

1. Удалить `__pycache__/` из корня (локальный артефакт, не в git)
2. Удалить `data/_glossary_old.json`, `data/_style_guide.md`, `data/glossary.json`
3. Удалить `migrate_glossary.py`
4. Дополнить `.gitignore` (`.pytest_cache/`, `dist/`, `build/`, `.claude/`, `*.egg-info/`)
5. ~~Удалить `release.md` из git-трека~~ — файл уже не существует

### Приоритет 2: Устранение дублирования

6. Консолидировать `CLAUDE.md` + `GEMINI.md` + `AGENTS.md` → один `AGENTS.md` (ограничение: LLM требуют разные имена файлов)
7. Удалить `config.py` (не используется)
8. Удалить `main.py` (дубль entry point)

### Приоритет 3: Очистка мёртвого кода

9. Удалить из `term_collector.py`: `collect_and_deduplicate_terms()`, `_edit_term()`, `present_for_confirmation()`, `update_glossary_file()`
10. Обновить тесты: удалить тесты в `test_term_collector.py` для удалённых функций; убрать бесполезные моки `present_for_confirmation` из `test_orchestrator.py`
11. Решить судьбу `diff_viewer.py` — интеграция или удаление

### Приоритет 4: Стилевые исправления

12. Заменить `Dict`/`List`/`Optional` на встроенные типы Python 3.11+ во всех модулях (9 файлов)
13. Исправить `convert_to_docx.py` — убрать 5 вызовов `sys.exit()`, заменить на исключения
14. Исправить `proofreader.py` — использовать `system_logger` из `logger.py`

### Приоритет 5: Рефакторинг `orchestrator.py`

15. Извлечь вызов `gemini-cli` в отдельный модуль `llm_runner.py`
16. Создать dataclass `WorkerConfig` для группировки параметров (22 и 23 аргумента в воркерах)
17. Вынести `_find_tool_versions_dir()` в `utils.py`
18. Извлечь этапы pipeline в отдельные функции или модуль `pipeline.py`

### Приоритет 6: Интеграция и доработки

19. Подключить `convert_to_epub.py` к CLI (добавить `--epub` флаг по аналогии с `--docx`) или удалить
20. Интегрировать `diff_viewer.py` в pipeline вычитки (если оставлен)
21. ~~Интегрировать `data/style_guides/` в команду `init`~~ — **уже реализовано** (`init_cmd.py:_find_bundled_style_guide()`)
