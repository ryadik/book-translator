# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Translate All Command**: Introduced `translate-all` CLI command to sequentially translate all volumes in a series.
- **Rich Status TUI**: Upgraded `status` command to use `rich` for detailed, table-based progress reporting.
- **EPUB Conversion**: Added `convert_to_epub.py` for exporting translations to EPUB format.
- **CLI Translation Options**: Added `--dry-run`, `--stage` to forcefully restart from a specific pipeline step, and `--docx`/`--no-docx` flags.
- **Diff Viewer**: Added `diff_viewer.py` for visualizing changes.
- **Robust JSON Parsing**: Added `parse_llm_json` utility to better handle malformed JSON responses from LLMs.
- **Documentation**: Added `AGENTS.md` and `FEATURES.md`.
- **Glossary Migration**: Provided `migrate_glossary.py` for seamless upgrades.

### Changed
- **Dependencies Management**: Removed `requirements.txt` in favor of full `pyproject.toml` specification including `dev` optional dependencies (added `ebooklib`).
- **Database-Driven State**: Replaced file-based checkpoints with SQLite DB-driven chapter stages (`get_chapter_stage`, `set_chapter_stage`, `reset_chapter_stage`).
- **Orchestrator Refactoring**: Rewrote translation pipeline to rely on the new DB stages, supporting partial restarts and dry runs.
- **Configuration Validation**: Enhanced `discovery.py` with rigorous TOML config validation (language codes, chunk sizes, concurrency limits, timeouts).

## [Phase 3 Release]

### Added
- **CLI with Subcommands**: Transitioned to a robust CLI architecture using `argparse` with subcommands (`init`, `translate`, `glossary`, `status`).
- **TOML Configuration**: Introduced `book-translator.toml` for series-level configuration, replacing the old JSON config.
- **Global Series-Level Glossary**: Implemented a global SQLite glossary database (`glossary.db`) with WAL mode enabled for concurrent access and better performance.
- **Smart Path Resolution**: Added intelligent path resolution to automatically find the series root and configuration file from any subdirectory.
- **Volume-Level State Isolation**: Isolated translation state (`state.db`) and temporary files to individual volume directories (`.state/`), allowing multiple volumes to be translated independently within the same series.
