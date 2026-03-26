# Book Translator

Интерактивный инструмент для перевода ранобэ, веб-романов и других текстов с любого языка на русский. Поддерживает два LLM-бэкенда: **Gemini** (облачный) и **Ollama** (локальный, бесплатно, без лимитов).

## Основные возможности

* **Два LLM-бэкенда**: переключение между облачным Gemini и локальным Ollama одним кликом в TUI.
* **Разные модели для разных задач**: каждый этап конвейера использует оптимальную модель.
* **Интерактивный TUI**: полноценный текстовый интерфейс для управления всеми операциями.
* **Четырёхэтапный конвейер**:
  1. **Discovery** — поиск и извлечение терминов.
  2. **Translation** — перевод с учётом глоссария и контекста.
  3. **Proofreading** — вычитка каждого чанка.
  4. **Global proofreading** — финальная вычитка всей главы.
* **Управление глоссарием**: добавление, редактирование, импорт/экспорт терминов.
* **Пакетный перевод**: перевод всех ожидающих глав одной командой.
* **Сохранение состояния**: SQLite-базы для возобновления прерванных переводов.

---

## Установка

```bash
# Клонируйте репозиторий
git clone <url>
cd book-translator

# Установите (рекомендуется через pipx)
pipx install .

# Или в режиме разработки
pip install -e ".[dev]"
```

---

## Настройка Ollama (локальный бэкенд)

> Пропустите этот раздел, если используете Gemini.

### 1. Установка

**macOS:**
```bash
# Через Homebrew
brew install ollama

# Или скачайте с https://ollama.com/download
```

**Windows:**
Скачайте установщик с https://ollama.com/download

### 2. Запуск

```bash
ollama serve
```

Проверка: откройте http://localhost:11434 в браузере — должна открыться страница "Ollama is running".

### 3. Загрузка моделей

```bash
ollama pull qwen3:8b          # ~5 GB — для поиска терминов
ollama pull qwen3:30b-a3b     # ~18 GB — для перевода и вычитки
ollama pull qwen3:14b         # ~9 GB — для глобальной вычитки
```

---

## Настройка Gemini (облачный бэкенд)

```bash
# Установите gemini-cli
npm install -g @google/gemini-cli

# Авторизуйтесь
gemini auth
```

---

## Использование

### Запуск

```bash
book-translator
```

Откроется TUI-интерфейс. Если серия не инициализирована, нажмите `i` для создания новой.

### Горячие клавиши (Dashboard)

| Клавиша | Действие |
|---------|----------|
| `Enter` | Перевести выбранную главу |
| `a` | Перевести все ожидающие главы |
| `i` | Инициализировать новую серию |
| `g` | Открыть глоссарий |
| `p` | Промпты |
| `c` | Конфигурация |
| `l` | Логи |
| `r` | Обновить |
| `q` | Выход |
| `Ctrl+D` | Переключить тему |

### Горячие клавиши (Глоссарий)

| Клавиша | Действие |
|---------|----------|
| `a` | Добавить термин |
| `Enter` | Редактировать выбранный |
| `d` | Удалить |
| `e` | Экспорт в TSV |
| `i` | Импорт из TSV |
| `f` | Поиск |
| `Esc` | Назад |

---

## Структура проекта

```
МояСерия/                           ← корень серии
├── book-translator.toml            ← конфигурация
├── glossary.db                     ← глоссарий
├── world_info.md                   ← описание мира
├── style_guide.md                  ← правила стиля
├── prompts/                        ← кастомные промпты
└── volume-01/
    ├── source/                     ← исходные .txt
    ├── output/                     ← переведённые файлы
    └── .state/
        ├── chunks.db               ← состояние чанков
        └── logs/                   ← логи
```

---

## Конфигурация (`book-translator.toml`)

```toml
[series]
name = "My Series"
source_lang = "ja"
target_lang = "ru"

[llm]
backend = "ollama"  # или "gemini"
ollama_url = "http://localhost:11434"

[llm.models]
discovery = "qwen3:8b"
translation = "qwen3:30b-a3b"
proofreading = "qwen3:30b-a3b"
global_proofreading = "qwen3:14b"

[llm.options]
temperature = 0.3
num_ctx = 8192
think = false

[llm.options.stage_temperature]
discovery = 0.1
translation = 0.4
proofreading = 0.3
global_proofreading = 0.1

[gemini_cli]
model = "gemini-2.5-pro"

[workers]
max_concurrent = 3
max_rps = 100.0

[splitter]
target_chunk_size = 600
max_part_chars = 800
min_chunk_size = 300

[retry]
max_attempts = 3
wait_min_seconds = 4
wait_max_seconds = 10
```

---

## Стайлгайды

При инициализации автоматически копируется подходящий стайлгайд:
- `ja_ru.md` — Японский→Русский
- `ko_ru.md` — Корейский→Русский
- `zh_ru.md` — Китайский→Русский
- `en_ru.md` — Английский→Русский
- `default.md` — шаблон для других языков

---

## Кастомизация промптов

Создайте файлы в `{series_root}/prompts/`:
- `translation.txt` — промпт перевода
- `proofreading.txt` — промпт вычитки
- `global_proofreading.txt` — глобальная вычитка
- `term_discovery.txt` — поиск терминов

Пользовательские промпты имеют приоритет над встроенными.

---

## Разработка

### Запуск тестов

```bash
pytest
pytest -v
pytest --cov=src/book_translator
```

### Структура кода

```
src/book_translator/
├── cli.py                  ← точка входа
├── orchestrator.py         ← управление конвейером
├── llm_runner.py           ← вызовы LLM
├── discovery.py            ← загрузка конфига
├── db.py                   ← SQLite-операции
├── path_resolver.py        ← разрешение путей
├── chapter_splitter.py     ← разделение на чанки
├── textual_app/            ← TUI-приложение
│   ├── app.py
│   ├── screens/
│   │   ├── dashboard.py
│   │   ├── translation.py
│   │   ├── glossary.py
│   │   ├── init_screen.py
│   │   └── ...
│   └── messages.py
└── data/
    ├── prompts/            ← промпты для Gemini
    ├── prompts/local/      ← промпты для Ollama
    └── style_guides/       ← стайлгайды
```

---

## Лицензия

MIT
