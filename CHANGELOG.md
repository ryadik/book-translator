# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added (Multi-language support — LANG-1..11)
- **Multi-language support**: Translation pipeline now supports any source language (ja, ko, zh, en, and others) with `source_lang`/`target_lang` from TOML config.
- **`languages.py`**: New module with language code → name mapping (`get_language_name()`) and per-language typography rules (`get_typography_rules()`).
- **Bundled style guides**: Language-pair-specific guides in `data/style_guides/`: `ja_ru.md`, `ko_ru.md`, `zh_ru.md`, `en_ru.md`, `default.md`.
- **Auto style guide selection**: `init` command now automatically copies the correct bundled style guide for the language pair; falls back to `default.md` for unknown pairs.
- **`docs/style_guide_prompt_template.md`**: LLM prompt template for generating custom style guides for any language pair.
- **EPUB language metadata**: `convert_to_epub.py` now accepts a `language` parameter, setting correct metadata on the generated EPUB.

### Changed (Multi-language support — LANG-1..11)
- **Prompts parametrized**: All four prompts (`translation`, `proofreading`, `global_proofreading`, `term_discovery`) now use `{target_lang_name}`, `{source_lang_name}`, and `{typography_rules}` placeholders instead of hardcoded "Russian"/"Japanese".
- **ANCHOR D extracted**: Typography rules (Russian typesetting, ANCHOR D section) moved from inline prompt text to `languages.py` → injected via `{typography_rules}` placeholder.
- **Term discovery JSON keys**: Discovery prompt now uses language-neutral keys `source`/`target`/`romanization` instead of `jp`/`ru`/`romaji`; backward-compatible fallback preserved in `term_collector.py` and `glossary_manager.py`.
- **`term_collector.py`**: Refactored to use `source`/`target`/`romanization` keys with backward-compatible fallback chains for old `jp`/`ru` format.
- **`glossary_manager.py`**: `generate_approval_tsv()` updated to use `term_source`/`term_target` keys with fallback to legacy `term_jp`/`term_ru`.

### Added (Prompt quality & world_info — FIX-1..IMPROVE-6)
- **`world_info.md` context**: `world_info.md` is now loaded and passed to translation and proofreading prompts as `{world_info}` placeholder.
- **`style_guide` in discovery**: Style guide content is now passed to the term discovery stage prompt.
- **Rewritten global proofreading prompt**: Now requests a structured JSON diff array with `"find"`/`"replace"` keys; applied only on exact single matches.

### Fixed (Prompt quality — FIX-1..4)
- **Duplicate `{text}` placeholder**: Removed duplicate `{text}` injection that caused text to appear twice in translation prompts.
- **`content_ru` → `content_target`**: Fixed key mismatch in proofreading — result was read from `content_ru` but LLM returned `content_target`.
- **Global proofreading JSON key mismatch**: Fixed mismatch between prompt-instructed and code-expected JSON keys in global proofreading response.
- **`{{` escaping in JSON examples**: Fixed double-brace escaping in prompt JSON examples that caused literal `{{` to appear in rendered prompts.

### Changed (Prompt quality — IMPROVE-1..6)
- **Removed hardcoded series references**: Removed DanMachi/specific series references from default prompts.
- **Em-dash contradiction resolved**: Removed conflicting em-dash rule that contradicted the U+2500 dialogue operator rule in the style guide.
- **Removed `</output>` tags**: Cleaned up prompt output wrappers that caused LLM to include stray XML tags in translated text.

### Added (Phase 3 features)
- **Translate All Command**: `translate-all` CLI command to sequentially translate all volumes in a series.
- **Rich Status TUI**: `status` command upgraded to use `rich` for detailed table-based progress reporting.
- **EPUB Conversion**: `convert_to_epub.py` for exporting translations to EPUB format.
- **CLI Translation Options**: Added `--dry-run`, `--stage`, `--docx`/`--no-docx` flags.
- **Diff Viewer**: `diff_viewer.py` for visualizing changes.
- **Robust JSON Parsing**: `parse_llm_json` utility for handling malformed LLM JSON responses.
- **Glossary Migration**: `migrate_glossary.py` for seamless upgrades.

### Changed (Phase 3)
- **Dependencies Management**: Removed `requirements.txt` in favor of full `pyproject.toml` specification.
- **Database-Driven State**: Replaced file-based checkpoints with SQLite DB-driven chapter stages.
- **Orchestrator Refactoring**: Rewrote translation pipeline for DB stages, supporting partial restarts and dry runs.
- **Configuration Validation**: Enhanced `discovery.py` with rigorous TOML config validation.

## [Phase 3 Release]

### Added
- **CLI with Subcommands**: Transitioned to a robust CLI architecture using `argparse` with subcommands (`init`, `translate`, `glossary`, `status`).
- **TOML Configuration**: Introduced `book-translator.toml` for series-level configuration, replacing the old JSON config.
- **Global Series-Level Glossary**: Implemented a global SQLite glossary database (`glossary.db`) with WAL mode enabled for concurrent access and better performance.
- **Smart Path Resolution**: Added intelligent path resolution to automatically find the series root and configuration file from any subdirectory.
- **Volume-Level State Isolation**: Isolated translation state (`state.db`) and temporary files to individual volume directories (`.state/`), allowing multiple volumes to be translated independently within the same series.
