# Changelog

All notable changes to this project will be documented in this file.

## [v3.0.0] - 2026-03-30

### Added
- **Full TUI Application**: Complete Textual-based terminal user interface replacing the CLI-only workflow.
- **Dashboard Screen**: Central hub for managing series, viewing translation progress, and launching operations.
- **Interactive Glossary Management**: TUI screen for viewing, adding, editing, deleting, importing/exporting terms.
- **Translation Progress Screen**: Real-time visualization of chapter translation status across all pipeline stages.
- **Batch Translation Screen**: Interface for translating multiple chapters concurrently with progress tracking.
- **Log Viewer**: Built-in screen for viewing application logs with filtering by level and worker (`log_viewer.py` module).
- **Settings Screen**: Configure LLM backends, models, worker concurrency, and rate limits from the TUI.
- **Prompts Screen**: View and manage custom prompt templates for each pipeline stage.
- **Initialization Wizard**: Guided series setup with language selection and model configuration.
- **Theme Support**: Dark/light theme toggle with persistent user preferences (saved to `~/.config/book-translator/tui.json`).
- **Keyboard Shortcuts**: Comprehensive key bindings for efficient navigation and actions.
- **Modal Dialogs**: Confirmation prompts, wait screens, and term approval workflows.
- **Term Approval Workflow**: Interactive review of discovered terms before adding to glossary.
- **Translation Options Screen**: Configure output format (DOCX/EPUB), chunking parameters per translation.
- **Qwen Backend**: Third LLM backend (`qwen-code` CLI) alongside Gemini and Ollama (`run_qwen()` in `llm_runner.py`).
- **Cancellation Support**: `CancellationError` exception and cancellation handling for all LLM backends.
- **Stage-specific Temperature**: Per-stage temperature overrides via `llm.options.stage_temperature` config.
- **Think Mode Control**: `llm.options.think` flag to disable Qwen3 thinking mode.
- **Run Manifest**: Persisted translation run logs with worker state tracking (`update_run_manifest()`).
- **Local Prompts**: Separate prompt variants for local LLMs in `data/prompts/local/`.
- **Protocol-based UI**: `TranslationUI` protocol for UI backend abstraction in orchestrator.

### Changed
- **Entry Point**: `book-translator` command now launches TUI instead of running CLI commands directly.
- **Architecture**: Shift from imperative CLI to event-driven TUI with screen-based navigation.
- **User Interaction**: All user-facing prompts and confirmations now handled through TUI modals.
- **Progress Reporting**: Real-time progress updates in TUI instead of console output.
- **Configuration**: Runtime configuration changes possible through TUI settings screen.
- **Error Display**: Errors shown in TUI notifications instead of stderr.
- **Unified LLM Config**: All LLM backends configured via `[llm]` section (replaces `[gemini_cli]` timeouts).
- **Backend-aware Timeouts**: Ollama gets longer timeouts (600s worker, 900s proofreading) vs cloud backends (120s/300s).
- **Glossary Upsert**: `add_term()` uses `ON CONFLICT ... DO UPDATE` to preserve `id` and `created_at`.
- **Chunk Upsert**: `add_chunk()` uses `ON CONFLICT ... DO UPDATE` to preserve `id`.
- **Atomic Status Updates**: New `batch_update_chunk_statuses()` for transactional multi-chunk updates.
- **Chapter Lock Logic**: Current process locks treated as stale (allows restart after crash).
- **Prompt Templates**: Updated all prompts with `{target_lang_name}`, `{source_lang_name}` placeholders.
- **Logger Module**: Enhanced `logger.py` with additional loggers and formatting.
- **LLM Runner**: Major refactor of `llm_runner.py` with separate functions per backend, process tracking, cancellation.
- **Orchestrator**: Protocol-based UI abstraction, improved concurrency, better error handling.
- **Discovery**: Unified config loading with backend-aware defaults, stage temperature support.
- **EPUB Conversion**: Updated to support language metadata parameter.
- **Path Resolver**: Improved series root discovery and prompt resolution.
- **Term Collector**: Modernized type hints, backward-compatible key handling.
- **Proofreader**: Enhanced diff application logic.
- **Glossary Manager**: Updated to use `term_source`/`term_target` keys with legacy fallback.
- **DB Module**: Upsert semantics for terms and chunks, atomic batch operations.
- **Exceptions**: Added `CancellationError` for user-initiated cancellation.
- **Default Prompts**: New `default_prompts.py` module for bundled prompt loading.
- **Chapter Splitter**: Improved chunking logic with configurable parameters.
- **Utils**: Enhanced JSON parsing for LLM responses.

### Removed
- **CLI Subcommands**: `init`, `translate`, `translate-all`, `glossary`, `status` commands (replaced by TUI).
- **Commands Package**: Entire `src/book_translator/commands/` directory removed.
- **Rich Status TUI**: Replaced by full Textual application.
- **Console-based Progress**: Replaced by TUI progress widgets.
- **Old TUI Module**: `tui.py` removed, replaced by `textual_app/` package.
- **All Tests**: Test files removed (to be rewritten for v3.0 architecture).
- **Gemini-specific Config**: `[gemini_cli]` section deprecated in favor of unified `[llm]` config.
- **Documentation**: Moved user-facing docs to `_deprecated_docs/` (to be rewritten).

### Migration from v2.x
- Launch `book-translator` to enter the TUI interface
- Use keyboard shortcuts or mouse navigation to perform actions
- All previous functionality available through TUI screens
- Configuration files and database formats remain compatible
- Update `book-translator.toml`: move `[gemini_cli]` timeouts to `[llm]` section if using custom values
- Add `qwen` backend support: set `llm.backend = "qwen"` and configure `[llm.models]`

## [Unreleased]

### Added
- **Multi-language support**: Translation pipeline supports any source language via `source_lang`/`target_lang` in TOML config.
- **`languages.py`**: Language code → name mapping (`get_language_name()`) and per-language typography rules (`get_typography_rules()`).
- **Bundled style guides**: Language-pair-specific guides (`ja_ru`, `ko_ru`, `zh_ru`, `en_ru`, `default`) with auto-selection during `init`.
- **`docs/style_guide_prompt_template.md`**: LLM prompt template for generating custom style guides.
- **EPUB language metadata**: `convert_to_epub.py` accepts a `language` parameter for correct EPUB metadata.
- **`world_info.md` context**: Loaded and passed to translation, proofreading, and global proofreading prompts.
- **Style guide in discovery**: Style guide content passed to term discovery prompt.
- **Global proofreading rewrite**: Structured JSON diff array (`find`/`replace`) applied only on exact single matches.
- **`llm_runner.py`**: Extracted LLM subprocess runner module.
- **`WorkerConfig` dataclass**: Clean configuration for worker pool execution.
- **Atomic stage transitions**: `promote_chapter_stage` ensures consistency between chapter state and chunk statuses.
- **Chapter-specific locking**: Database locking scoped to individual chapters.
- **`min_chunk_size` config**: Configurable minimum chunk size for chapter splitting.
- **Configurable RPS**: `rps` field in TOML config (default 2).
- **`--stage` flag**: Restart translation from a specific pipeline stage.
- **Comprehensive documentation**: Wiki-style docs covering architecture, API, pipeline, concurrency, database, and testing.

### Changed
- **Prompts parametrized**: All prompts use `{target_lang_name}`, `{source_lang_name}`, `{typography_rules}` placeholders instead of hardcoded languages.
- **Term discovery simplified**: Flat JSON schema (`source`/`target`/`comment`), single-pass collection without nested grouping.
- **Default prompts as package data**: Moved from Python raw strings to `data/prompts/*.txt`, loaded via `importlib.resources`.
- **`WorkerConfig` simplified**: `cli_args` dict and `output_suffix` parameter replaced with `output_format: str` field.
- **Unreachable `parsed_json is None` check**: Replaced with proper `try/except ValueError`.
- **`term_collector.py` modernized**: Updated type hints, `source`/`target` keys with backward-compatible fallback.
- **`glossary_manager.py`**: `generate_approval_tsv()` uses `term_source`/`term_target` keys with legacy fallback.
- **CLI imports optimized**: Lazy loading in subcommands.
- **Typography rules extracted**: Moved from inline prompt text to `languages.py`.

### Fixed
- **Race conditions**: Concurrent chunk processing under `ThreadPoolExecutor`.
- **Database locking**: Parallel workers competing for SQLite connections.
- **Off-by-one in proofreader**: `apply_diffs` applying corrections to wrong chunk.
- **Duplicate `{text}` placeholder**: Text appeared twice in translation prompts.
- **`content_ru` → `content_target`**: Key mismatch in proofreading stage.
- **Global proofreading JSON keys**: Mismatch between prompt-instructed and code-expected keys.
- **`{{` escaping**: Double-brace in prompt JSON examples caused literal `{{` in rendered prompts.
- **`--force` scope**: Now clears chapter records, not entire database.
- **`status` double-count**: `reading_done` was counted twice in status command.

### Removed
- **`diff_viewer.py`**, **`migrate_glossary.py`**, **`config.py`**, **`main.py`**: Obsolete modules.
- **`data/` root directory**: Duplicate style guides (runtime uses `src/book_translator/data/`).
- **`prompts/` root directory**: Duplicate of bundled package data.
- **Dead DB functions**: `delete_term`, `get_term_count`, `get_chunks_by_status` (test-only usage).
- **Dead import**: `resolve_volume_from_chapter` in `translate_cmd.py`.
- **`requirements.txt`**: Replaced by `pyproject.toml`.
- **Hardcoded series references**: DanMachi-specific content removed from prompts.
- **Em-dash contradiction**: Conflicting rule removed from style guide.
- **`</output>` XML tags**: Stray tags removed from prompts.
- **`AGENTS.md`**, **`GEMINI.md`**: Redundant documentation (covered by `CLAUDE.md`).

## [Phase 3 Release]

### Added
- **CLI with Subcommands**: `argparse`-based architecture with `init`, `translate`, `glossary`, `status`.
- **TOML Configuration**: `book-translator.toml` for series-level configuration.
- **Global Series-Level Glossary**: SQLite `glossary.db` with WAL mode.
- **Smart Path Resolution**: Auto-discovery of series root from any subdirectory.
- **Volume-Level State Isolation**: Per-volume `state.db` in `.state/` directories.
- **Rich Status TUI**: Table-based progress reporting via `rich`.
- **EPUB Conversion**: `convert_to_epub.py` for EPUB export.
- **CLI Options**: `--dry-run`, `--docx`/`--no-docx`, `--force`, `--resume` flags.
- **Robust JSON Parsing**: `parse_llm_json` for handling malformed LLM responses.
- **Database-Driven State**: SQLite-based chapter stages replacing file checkpoints.
