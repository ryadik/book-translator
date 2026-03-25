# Overview

## Назначение системы

`book-translator` автоматизирует перевод больших текстовых файлов по главам через внешний CLI-инструмент `gemini`. Система разбивает главу на чанки, выполняет discovery новых терминов, перевод, локальную вычитку и глобальную вычитку, хранит промежуточное состояние в SQLite и умеет продолжать работу после сбоя.

## Полный pipeline

```text
source/*.txt
  ->
chapter_splitter.split_chapter_intelligently
  ->
chunks.db / chunks(status=discovery_pending)
  ->
discovery
  -> cache/*.json с ответами LLM
  -> term_collector.collect_terms_from_responses
  -> pending_terms_<chapter>.tsv
  -> glossary.db
  ->
translation
  -> chunks.content_target + status=translation_done
  ->
proofreading
  -> chunks.content_target + status=reading_done
  ->
global_proofreading
  -> JSON diff list
  -> proofreader.apply_diffs
  -> обновление chunks.content_target
  ->
final assembly
  -> output/<chapter>.txt
  -> optional .docx
  -> optional .epub
```

## Ключевые сущности

| Сущность | Где хранится | Что означает |
| --- | --- | --- |
| `series_root` | директория с `book-translator.toml` | корень серии, общая конфигурация и общий глоссарий |
| `volume` | `volume-XX/` | изолированный том со своими исходниками, выходом и состоянием |
| `chapter` | `volume/source/<chapter>.txt` | единица оркестрации pipeline |
| `chunk` | таблица `chunks` | часть главы с индексом, исходным текстом, переводом и статусом |
| `chapter_state` | таблица `chapter_state` | текущий этап pipeline для главы |
| `glossary term` | таблица `glossary` | утверждённый термин для языковой пары |
| `prompt` | bundled file или `series_root/prompts/*.txt` | шаблон запроса к LLM |
| `world_info.md` | серия или том | контекст мира для translation/proofreading |
| `style_guide.md` | серия или том | правила стиля, передаваемые в LLM |
| lock file | `volume/.state/.lock.<chapter>` | защита от параллельного перевода одной и той же главы |

## Реальные этапы состояния главы

`chapter_state.pipeline_stage` принимает только:

- `discovery`
- `translation`
- `proofreading`
- `global_proofreading`
- `complete`

Отсутствие записи в `chapter_state` означает, что глава ещё не продвинута ни на один этап.

## Реальные статусы чанков

- `discovery_pending`
- `discovery_in_progress`
- `discovery_done`
- `discovery_failed`
- `translation_pending`
- `translation_in_progress`
- `translation_done`
- `translation_failed`
- `reading_pending`
- `reading_in_progress`
- `reading_done`
- `reading_failed`

## Главные side effects системы

- создаёт директории серии и томов;
- записывает и читает `glossary.db` и `chunks.db`;
- пишет lock-файлы, JSON-кэш discovery и итоговые `.txt/.docx/.epub`;
- вызывает внешний процесс `gemini`;
- может блокироваться на интерактивном подтверждении терминов и вопросах о конвертации;
- пишет логи в stdout и, в debug-режиме, в `volume/.state/logs/`.
