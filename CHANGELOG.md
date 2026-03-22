# Changelog

All notable changes to this project will be documented in this file.

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
