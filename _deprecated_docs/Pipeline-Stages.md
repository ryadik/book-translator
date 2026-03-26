# Pipeline Stages

## Discovery

### Вход

- `chunks.content_source`
- текущий `glossary.db`
- `style_guide.md`
- `world_info.md`
- типографические правила
- языковые имена

### Выход

- JSON-файлы в `volume/.state/cache/<chapter>_chunk_<n>.json`
- при наличии новых терминов: `pending_terms_<chapter>.tsv`
- обновление статусов `discovery_pending -> discovery_done`
- продвижение главы в `translation`

### Логика

1. Для всех `discovery_pending` запускаются worker threads.
2. Каждый worker вызывает `gemini` с `output_format="json"`.
3. JSON валидируется через `parse_llm_json()`.
4. Сырые ответы пишутся в cache.
5. `term_collector.collect_terms_from_responses()` извлекает и дедуплицирует термины.
6. `approve_via_tsv()` ждёт ручного подтверждения.
7. `promote_chapter_stage()` переводит статусы в `translation_pending`.

### Ошибки

- пустой stdout;
- невалидный JSON;
- ошибка записи cache-файла;
- отказ subprocess;
- отсутствие TTY при найденных терминах.

### Retry

- retry встроен в `llm_runner.run_gemini()`.
- при исчерпании retries чанк получает `discovery_failed`.

### Edge cases

- если `collect_terms_from_responses()` не находит новых терминов, TSV не создаётся;
- если один worker упал, этап завершается без promotion.

## Translation

### Вход

- `chunks.content_source`
- подтверждённый глоссарий
- `style_guide.md`
- `world_info.md`
- `previous_context` = предыдущий `content_source`

### Выход

- `chunks.content_target`
- статусы `translation_done`
- promotion в `proofreading` с переводом всех `translation_done -> reading_pending`

### Логика

1. Берутся чанки со статусом `translation_pending`.
2. Для каждого чанка строится prompt из translation template.
3. Ответ LLM сохраняется в `content_target`.
4. После полного успеха глава переводится в `proofreading`.

### Ошибки

- пустой ответ;
- subprocess error/timeout;
- любое исключение в worker.

### Retry

- через `llm_runner.run_gemini()`.

### Edge cases

- если pending-чанков нет, этап всё равно пытается выполнить promotion и требует, чтобы все чанки уже были `translation_done`.

## Proofreading

### Вход

- `chunks.content_target` как входной текст;
- глоссарий;
- `style_guide.md`;
- `world_info.md`;
- `previous_context` = предыдущий `content_target`.

### Выход

- обновлённый `content_target`;
- статусы `reading_done`;
- promotion в `global_proofreading`.

### Логика

- полностью совпадает по структуре с translation, но worker получает `step_name="reading"` и берёт текст из `content_target`.

### Ошибки / Retry / Edge cases

- те же принципы, что и у translation.

## Global proofreading

### Вход

- все чанки главы, уже находящиеся в `reading_done`
- глоссарий
- `style_guide.md`
- `target_lang_name`

### Выход

- список diffs от LLM;
- локально модифицированный список чанков;
- массовое обновление `content_target` в БД;
- promotion в `complete`.

### Логика

1. Все чанки сериализуются в текст вида:

```text
Chunk N:
content_source: ...
content_target: ...
```

2. Выполняется один вызов `gemini` с `output_format='json'`.
3. Ответ должен быть списком diff-объектов.
4. `proofreader.apply_diffs()` применяет только правки с ровно одним совпадением `find`.
5. Если глобальная вычитка успешна, БД обновляется через `batch_update_chunks_content()`.
6. Глава продвигается в `complete`.

### Ошибки

- ответ не список;
- subprocess failure;
- timeout;
- ошибка парсинга JSON;
- непредвиденное исключение.

### Retry

- тот же retry-контур в `llm_runner.run_gemini()`.

### Edge cases

- skipped diff не считается фатальной ошибкой;
- если global proofreading вернул `False`, стадия `complete` не выставляется;
- сборка файла после этого не выполняется.
