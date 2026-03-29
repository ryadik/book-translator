# Book Translator Wiki

Этот раздел оформлен как GitHub Wiki в файловом виде. Документация описывает фактическое поведение текущей кодовой базы `book-translator`, а не только заявленную архитектуру.

## Навигация

- [Overview](Overview.md)
- [User Guide](User-Guide.md)
- [Architecture Deep Dive](Architecture-Deep-Dive.md)
- [API Documentation](API-Documentation.md)
- [Codebase Reference](Codebase-Reference.md)
- [Database](Database.md)
- [Pipeline Stages](Pipeline-Stages.md)
- [Concurrency Model](Concurrency-Model.md)
- [Error Handling and Retry](Error-Handling-and-Retry.md)
- [Tests Documentation](Tests-Documentation.md)

## Границы документации

- Документация покрывает CLI, pipeline, SQLite, файловую структуру, внутренние модули, bundled prompts/style guides и тесты.
- Документация отражает фактическое состояние кода в `src/book_translator` и `tests`.
- Если README расходится с кодом, приоритет у кода.

## Критические замечания

- `ASSUMPTION`: внешний бинарник `gemini` установлен отдельно и доступен в `PATH`; репозиторий не содержит его исходный код.
- В проектном описании фигурирует "multiprocessing", но текущая реализация использует `ThreadPoolExecutor` и отдельные subprocess-вызовы `gemini`, а не Python `multiprocessing`.
- README упоминает `state.db`; фактическое имя локальной БД тома в коде: `volume-XX/.state/chunks.db`.
