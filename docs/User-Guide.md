# User Guide

## 2.1 Установка

### Требования

- Python `>=3.11`
- установленный и авторизованный `gemini` CLI
- для `.docx`: пакет `python-docx`
- для `.epub`: пакет `ebooklib`

### Установка пакета

```bash
pip install -e .
```

Для разработки:

```bash
pip install -e ".[dev]"
```

### Что устанавливается из Python-зависимостей

| Зависимость | Зачем нужна |
| --- | --- |
| `rich` | TUI и rich-логирование |
| `tenacity` | retry для `gemini` subprocess |
| `json-repair` | починка слегка повреждённого JSON от LLM |
| `python-docx` | конвертация `.txt -> .docx` |
| `ebooklib` | конвертация `.txt -> .epub` |

### Начальная структура серии

Команда `init` создаёт:

```text
<Series>/
  book-translator.toml
  world_info.md
  style_guide.md
  glossary.db
  prompts/
  volume-01/
    source/
    output/
```

## 2.2 Запуск

### Инициализация

```bash
book-translator init "My Series" --source-lang ja --target-lang ru
```

### Перевод одной главы

```bash
cd "My Series"
book-translator translate volume-01/source/chapter-01.txt
```

### Перевод всех `.txt` в одном `source/`

```bash
book-translator translate volume-01/source
```

### Перевод всех томов

```bash
book-translator translate-all
```

### Работа с глоссарием

```bash
book-translator glossary list
book-translator glossary export --output glossary.tsv
book-translator glossary import glossary.tsv
```

### Просмотр статуса

```bash
book-translator status
```

## 2.3 Полный сценарий работы

1. Выполнить `init`.
2. Заполнить `world_info.md`.
3. Проверить или заменить `style_guide.md`.
4. При необходимости создать override prompts в `prompts/`.
5. Поместить исходные `.txt` в `volume-XX/source/`.
6. Запустить `translate` для файла или директории.
7. Дождаться discovery.
8. Если найдены новые термины, отредактировать `pending_terms_<chapter>.tsv` и подтвердить импорт нажатием `Enter`.
9. Дождаться translation.
10. Дождаться proofreading.
11. Дождаться global proofreading.
12. При запросе решить, нужна ли конвертация в `.docx` и `.epub`, если эти решения не были зафиксированы флагами.
13. Забрать результат из `volume-XX/output/`.

## 2.4 Resume / Recovery

### Как работает resume

- `--resume` не пропускает живую блокировку.
- `--resume` переводит все статусы `*_in_progress` и `*_failed` обратно в `*_pending`.
- Если в `chapter_state` есть запись, а чанков нет, состояние главы сбрасывается, затем выполняется повторный chunking.

### Как работает force

- `--force` удаляет lock-файл текущей главы, если он существует.
- `--force` очищает записи главы из `chunks.db`.
- `--force` удаляет cache JSON, `pending_terms_*.tsv` и итоговые `.txt/.docx/.epub` конкретной главы.

### Как работает `--stage`

- `--stage discovery` выставляет все чанки в `discovery_pending`.
- `--stage translation` выставляет все чанки в `translation_pending`.
- `--stage proofreading` выставляет все чанки в `reading_pending`.
- `--stage global_proofreading` тоже выставляет все чанки в `reading_pending`.
- После reset старые cache/output артефакты удаляются.

### Edge cases recovery

| Ситуация | Поведение |
| --- | --- |
| найден lock с живым PID | выбрасывается `TranslationLockedError` |
| найден lock с мёртвым PID | lock удаляется, процесс продолжается |
| `chapter_state` есть, чанков нет | `chapter_state` очищается, chunking повторяется |
| глобальная вычитка не удалась | глава не переводится в `complete`, сборка не выполняется |
| любой этап вернул ошибки по чанкам | оркестратор завершает run без продвижения на следующий этап |

## 2.5 Работа с глоссарием

### Источники терминов

- ручной импорт TSV;
- автоматический discovery через LLM;
- ручное редактирование `pending_terms_<chapter>.tsv`.

### Формат TSV

```tsv
# source_term	target_term	comment
原文	Перевод	Комментарий
```

Правила:

- строки `#...` игнорируются;
- пустые строки игнорируются;
- строка с менее чем двумя колонками игнорируется;
- при повторном импорте термин с тем же `(term_source, source_lang, target_lang)` полностью заменяется.

### Как глоссарий влияет на pipeline

- discovery получает текущий глоссарий, чтобы не предлагать уже известные термины;
- translation получает сериализованный JSON глоссария;
- proofreading получает тот же JSON глоссария;
- global proofreading тоже получает глоссарий, но применяет изменения уже как diffs.

## 2.6 Работа с `world_info.md`

- Файл читается на этапах translation и proofreading.
- Для тома возможен override: `volume-XX/world_info.md` имеет приоритет над `series_root/world_info.md`.
- Если файл отсутствует и на уровне тома, и на уровне серии, в prompt подставляется пустая строка.

## 2.7 Ошибки и их интерпретация

| Ошибка | Значение | Что делать |
| --- | --- | --- |
| `book-translator.toml not found` | запуск вне корня серии | перейти в серию или выполнить `init` |
| `TranslationLockedError` | другая живая сессия уже переводит эту главу | дождаться завершения или использовать `--force` осознанно |
| `Требуется интерактивное подтверждение терминов` | discovery нашёл термины, но stdin не TTY | запускать интерактивно или заранее заполнить глоссарий |
| `RuntimeError` при сборке главы | не все чанки находятся в `reading_done` | изучить статусы через `status` и `chunks.db` |
| `ValueError` из `parse_llm_json` | LLM вернула непарсибельный JSON | изучить debug-логи, перезапустить этап |
| `ImportError` при DOCX/EPUB | отсутствует библиотека конвертации | установить пакет |
| `FileNotFoundError` для prompt/файла главы | неверный путь или отсутствующий override | исправить структуру файлов |

## Конфигурация `book-translator.toml`

### Минимальный рабочий пример

```toml
[series]
name = "My Series"
source_lang = "ja"
target_lang = "ru"

[gemini_cli]
model = "gemini-2.5-pro"
worker_timeout_seconds = 120
proofreading_timeout_seconds = 300

[retry]
max_attempts = 3
wait_min_seconds = 4
wait_max_seconds = 10

[splitter]
target_chunk_size = 600
max_part_chars = 800
min_chunk_size = 300

[workers]
max_concurrent = 50
max_rps = 2.0
```

### Валидация

- `source_lang`, `target_lang`: ровно 2 строчные буквы;
- `splitter.*`: положительные целые числа;
- `workers.max_concurrent`: `1..200`;
- `workers.max_rps`: `0.1..100`;
- `retry.max_attempts`: `1..10`;
- `gemini_cli.*timeout_seconds`: положительные `int` или `float`.
