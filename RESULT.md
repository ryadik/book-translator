# Аудит `book-translator`

## Предположения

- Ниже я исхожу из того, что `chunks.db` и `chapter_state` должны быть источником истины, а `--resume` обязан быть crash-safe.
- Если это не так, архитектура уже сломана: текущий код всё равно позиционирует себя как checkpoint-based pipeline с возобновлением.
- Анализ основан на исходниках и тестах в текущем дереве. Неочевидные допущения я пометил явно.

## 1. 🔴 CRITICAL (must fix immediately)

### 1. `--resume` пробивает живую блокировку и разрешает второй процесс поверх первого

- Описание:
  `resume` отключает проверку lock-файла целиком. Если первый процесс уже переводит главу, второй процесс с `--resume` спокойно перезапишет `.lock` и пойдёт работать в тот же `chunks.db`.
- Почему это опасно:
  Это не просто гонка. Это два независимых оркестратора, которые одновременно двигают статусы чанков, пишут результаты, удаляют общий `.lock` в `finally` и могут закончить разными версиями текста. Источник истины превращается в лотерею.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:288-302`
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:364-366`
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:570-573`
- Как воспроизвести:
  1. Запустить `book-translator translate volume-01/source/chapter.txt`.
  2. Пока процесс жив, запустить ту же команду с `--resume`.
  3. Второй процесс не остановится на lock-проверке, а просто перепишет PID в `.lock`.
- Как исправить:
  1. Проверять lock всегда, независимо от `resume`.
  2. Хранить в lock не только PID, а минимум `chapter_name`, `started_at`, hostname и run-id.
  3. Создавать lock атомарно через `O_EXCL`/`Path.open("x")`, а не простым `write_text`.
  4. `--resume` должен продолжать только собственный незавершённый run или явно устаревший lock. Для насильственного захвата должен существовать только `--force`.

### 2. Переходы между этапами неатомарны: checkpoint двигается вперёд раньше данных

- Описание:
  После `discovery` код сначала пишет `chapter_state='translation'`, а уже потом массово переводит чанки из `discovery_done` в `translation_pending`. После `translation` он сначала пишет `chapter_state='proofreading'`, а только потом переводит `translation_done` в `reading_pending`.
- Почему это опасно:
  Падение между этими двумя действиями оставляет БД в противоречивом состоянии: глобальный этап уже “завершён”, а конкретные чанки ещё нет. Следующий `resume` будет доверять `chapter_state` и перепрыгнет через реально незавершённую работу.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:421-426`
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:456-461`
  `/Users/ryadik/personal/book-translator/src/book_translator/db.py:301-320`
- Как воспроизвести:
  1. Довести главу до конца `discovery`.
  2. Убить процесс после `db.set_chapter_stage(..., "translation")`, но до цикла `discovery_done -> translation_pending`.
  3. Запустить `--resume`.
  4. `discovery` будет пропущен, а `translation` увидит ноль `translation_pending` и продвинет pipeline дальше.
- Как исправить:
  1. Делать смену `chapter_state` и массовую смену статусов чанков в одной транзакции SQLite.
  2. Ввести инвариант: `chapter_state` можно продвинуть только если `COUNT(*)` неподходящих chunk-status для текущего этапа равно нулю.
  3. На `resume` валидировать согласованность `chapter_state` с chunk-status и при рассинхроне откатывать этап назад, а не идти дальше.

### 3. `--resume` на пустой БД пропускает чанкинг и может закончить “успешным” пустым файлом

- Описание:
  Разделение на чанки выполняется только при `if not chunks and not resume`. То есть пустая БД + `--resume` означает “не чанкать вообще”.
- Почему это опасно:
  После раннего падения до вставки чанков пользователь логично запускает `--resume`, а система вместо восстановления строит пустой pipeline, выставляет стадии и может собрать пустой `output/*.txt` как будто всё закончилось нормально.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:376-387`
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:528-541`
- Как воспроизвести:
  1. Создать `chunks.db` без записей по главе.
  2. Запустить `book-translator translate ... --resume`.
  3. Чанкинг не выполнится.
  4. Pipeline пройдёт по пустым спискам.
- Как исправить:
  1. Если чанков нет, выполнять чанкинг независимо от `resume`.
  2. Если `resume=True` и глава “не начата”, явно писать это в лог и переходить в обычный старт.
  3. Перед финальной сборкой запрещать успешное завершение при `total_chunks == 0`.

### 4. Глобальная вычитка и финальная сборка могут молча деградировать до частичного или сырого результата, но этап всё равно помечается как `complete`

- Описание:
  `_run_global_proofreading()` на любой ошибке возвращает исходные `chunks`, а вызывающий код без проверки записывает их обратно и ставит `chapter_state='complete'`. Затем финальная сборка берёт любой поднабор `reading_done` и объявляет успех, не сверяя количество чанков с ожидаемым.
- Почему это опасно:
  Это классический silent corruption. Система сама себе пишет “всё готово”, хотя глобальная вычитка могла не отработать вовсе, а итоговый TXT может быть неполным.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:128-190`
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:496-524`
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:528-541`
- Как воспроизвести:
  1. Заставить global proofreading вернуть не-список JSON или сломанный JSON.
  2. `_run_global_proofreading()` вернёт исходные чанки.
  3. Оркестратор всё равно проставит `complete`.
- Как исправить:
  1. Возвращать из `_run_global_proofreading()` не только чанки, но и явный флаг `success`.
  2. Не ставить `complete`, если global proofreading не выполнился корректно.
  3. Перед сборкой проверять: `count(reading_done) == count(all_chunks)` и нет ни одного `*_pending|*_failed|*_in_progress`.
  4. На нарушении инварианта падать с ошибкой и оставлять этап возобновляемым.

## 2. 🟠 HIGH RISK

### 5. Кэш discovery использует stale JSON от старых прогонов

- Описание:
  После discovery код читает все `cache/{chapter}_chunk_*.json` по glob. Кэш не чистится ни на `force`, ни на `restart_stage`, ни перед новым discovery-run.
- Почему это опасно:
  Старая разметка чанков, старые ответы LLM и новый прогон смешиваются. В глоссарий улетают “призрачные” термины из прошлой версии текста или прошлой схемы чанкинга.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:409-417`
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:304-309`
- Как воспроизвести:
  1. Прогнать discovery.
  2. Изменить исходный файл или параметры splitter.
  3. Запустить `--force` или `--stage discovery`.
  4. Старые JSON останутся в `cache`, и `collect_terms_from_responses()` прочитает их вместе с новыми.
- Как исправить:
  1. Перед новым discovery удалять chapter-scoped cache-файлы.
  2. Лучше: писать ответы в run-specific подкаталог, а собирать только файлы текущего run-id.
  3. При `force` чистить не только БД, но и chapter-scoped cache/output artifacts.

### 6. Retry-логика для `gemini-cli` не различает “безопасно повторить” и “запрос уже мог выполниться”

- Описание:
  Tenacity безусловно ретраит `CalledProcessError` и `TimeoutExpired`. Для внешнего LLM-вызова это не идемпотентно.
- Почему это опасно:
  При timeout запрос мог быть уже принят и даже выполнен на стороне модели. Повтор создаёт дублирующие дорогие вызовы, разные ответы для одного chunk и неочевидное расхождение между логическим “один шаг pipeline” и фактическими внешними сайд-эффектами.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/llm_runner.py:63-68`
  `/Users/ryadik/personal/book-translator/src/book_translator/llm_runner.py:71-91`
- Как воспроизвести:
  1. Вызвать LLM с сетевой задержкой вокруг таймаута.
  2. Получить `TimeoutExpired`.
  3. Тот же prompt будет отправлен повторно.
- Как исправить:
  1. Делить ошибки на retryable и ambiguous.
  2. Для timeout хранить артефакты stderr/stdout и помечать chunk как `*_ambiguous`, требующий ручного подтверждения или отдельного безопасного resume-режима.
  3. Если gemini-cli умеет request-id, использовать его.

### 7. Сборка терминов молча выкидывает конфликтующие варианты перевода по одному лишь `source`

- Описание:
  `collect_terms_from_responses()` дедуплицирует только по `source`, игнорируя различия в `target` и `comment`.
- Почему это опасно:
  При конфликтующих ответах LLM система выбирает первый попавшийся перевод и скрывает сам факт конфликта. Это прямой путь к загрязнению глоссария “официальными” ошибками.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/term_collector.py:57-80`
- Как воспроизвести:
  1. Дать два discovery-ответа: `hero -> Герой` и `hero -> Протагонист`.
  2. В итоговый список попадёт только первый.
- Как исправить:
  1. Дедуплицировать по `(source, target)` или хотя бы собирать все варианты.
  2. При конфликте генерировать TSV с несколькими кандидатами и явной пометкой `CONFLICT`.
  3. Логировать количество конфликтов как warning, а не тихо терять их.

### 8. Область блокировки выбрана по тому, где лежит БД, а не по единице работы

- Описание:
  `chapter_state` и chunk-status являются chapter-scoped, но `.lock` один на весь `volume/.state`.
- Почему это опасно:
  Это одновременно слишком широко и слишком слабо. Слишком широко, потому что вы сериализуете разные главы одного тома без доказанной необходимости. Слишком слабо, потому что lock не кодирует, какая именно глава владеет ресурсом.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:288`
  `/Users/ryadik/personal/book-translator/src/book_translator/db.py:85-103`
- Как исправить:
  1. Либо честно считать volume единицей работы и тогда тащить весь state/cache/output под volume-run.
  2. Либо делать chapter-scoped lock-файлы и chapter-scoped cache/run metadata.
  3. В любом случае кодировать владельца lock-а явно.

## 3. 🟡 MEDIUM

### 9. `restart_stage` и `force` не чистят производные артефакты

- Описание:
  При сбросе меняются записи в БД, но не удаляются `pending_terms.tsv`, chapter JSON-кэш и ранее собранный `output/*.txt`.
- Почему это опасно:
  Оператор видит старые артефакты и принимает их за актуальные. Дальше начинаются ручные ошибки, ложные диффы и неверные выводы о состоянии пайплайна.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:304-309`
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:409-417`
  `/Users/ryadik/personal/book-translator/src/book_translator/orchestrator.py:533-557`
- Как исправить:
  1. На `force` и `restart_stage` чистить chapter-scoped cache и pending approval files.
  2. Либо удалять старый финальный `output/*.txt/.docx/.epub`, либо писать их во временный файл и делать atomic replace только после успешной сборки.

### 10. Интерактивное подтверждение терминов ломает headless/automation сценарии

- Описание:
  `approve_via_tsv()` всегда делает `input()` и ждёт Enter.
- Почему это опасно:
  В `translate-all`, CI, nohup/tmux/cron или просто при закрытом stdin процесс зависает в середине pipeline. Снаружи это выглядит как “ничего не происходит”.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/term_collector.py:122-126`
- Как воспроизвести:
  Запустить discovery в неинтерактивном окружении с найденными терминами.
- Как исправить:
  1. Ввести явный режим `--approve-terms=interactive|skip|import-existing`.
  2. При отсутствии TTY падать с понятной ошибкой, а не зависать.
  3. Сохранять TSV и останавливать pipeline в статусе `awaiting_terms_approval`.

### 11. `min_chunk_size` есть в конфиге, но splitter его игнорирует

- Описание:
  В `book-translator.toml` и `load_series_config()` параметр есть, но в `split_chapter_intelligently()` он не используется вообще.
- Почему это опасно:
  Конфиг обещает инвариант, которого нет. Оператор думает, что контролирует гранулярность чанков, а на практике число LLM-вызовов и качество контекста определяются другой логикой.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/discovery.py:60-63`
  `/Users/ryadik/personal/book-translator/src/book_translator/chapter_splitter.py:6-96`
- Как исправить:
  1. Либо реально внедрить `min_chunk_size`.
  2. Либо удалить параметр из конфига и документации.
  3. Добавить тест, который валидирует фактическое применение значения.

### 12. Глобальные JSON-патчи применяются по “совпадению строки”, что остаётся хрупкой операцией даже с защитой `count()==1`

- Описание:
  Патч ищет произвольную строку в `content_target` и делает `replace`, если совпадение ровно одно.
- Почему это опасно:
  Один и тот же фрагмент может случайно стать уникальным только из-за пунктуации или форматирования; LLM не оперирует стабильными span-id. Итоговая коррекция привязана к текстовой случайности, а не к структуре документа.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/proofreader.py:19-52`
- Как исправить:
  1. Привязывать патч к стабильному идентификатору диапазона, а не к raw string.
  2. Как минимум требовать ещё `before_context`/`after_context`.
  3. Логировать и считать процент неприменённых диффов; при превышении порога считать global proofreading проваленным.

## 4. 🔵 LOW / CLEANUP

### 13. `save_approved_terms()` выглядит как мёртвый production-code

- Описание:
  Функция покрыта тестами, но в production flow не вызывается; orchestrator использует только `approve_via_tsv()`.
- Почему это опасно:
  Наличие альтернативного “правильного” пути сохранения маскирует реальный поток выполнения и затрудняет поддержку. Через полгода это будет ложная точка опоры для новых правок.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/term_collector.py:94-106`
- Как исправить:
  1. Либо удалить функцию как неиспользуемую.
  2. Либо реально использовать её в non-interactive flow и покрыть интеграционным сценарием.

### 14. `status` показывает misleading `Done`

- Описание:
  Счётчик `Done` суммирует все статусы, оканчивающиеся на `_done`, независимо от текущего этапа.
- Почему это опасно:
  На промежуточных этапах оператор видит красивую цифру и может принять её за реальную завершённость главы.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/commands/status_cmd.py:67-80`
- Как исправить:
  1. Показывать прогресс относительно текущего этапа.
  2. Отдельно выводить разбивку по статусам: `discovery_done`, `translation_done`, `reading_done`, `failed`, `pending`.

### 15. В splitter есть мусорный импорт

- Описание:
  `import os` в `chapter_splitter.py` не используется.
- Почему это опасно:
  Сам по себе не взрывает систему. Но это симптом слабой гигиены и отсутствия жёсткого контроля за мёртвым кодом.
- Где проявится:
  `/Users/ryadik/personal/book-translator/src/book_translator/chapter_splitter.py:1`
- Как исправить:
  Удалить неиспользуемый импорт и включить линтер, который режет такое автоматически.

## Итог

- Главная проблема проекта: pipeline не гарантирует согласованность между `chapter_state`, chunk-status и внешними артефактами.
- Самый опасный класс дефектов: “система считает этап завершённым, хотя данные этому не соответствуют”.
- До исправления критических пунктов доверять `--resume`, `--stage` и `complete` как надёжным механизмам восстановления нельзя.
