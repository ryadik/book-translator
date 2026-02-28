# Changelog

All notable changes to this project will be documented in this file.

## [Phase 3 Release]

### Added
- **CLI with Subcommands**: Transitioned to a robust CLI architecture using `argparse` with subcommands (`init`, `translate`, `glossary`, `status`).
- **TOML Configuration**: Introduced `book-translator.toml` for series-level configuration, replacing the old JSON config.
- **Global Series-Level Glossary**: Implemented a global SQLite glossary database (`glossary.db`) with WAL mode enabled for concurrent access and better performance.
- **Smart Path Resolution**: Added intelligent path resolution to automatically find the series root and configuration file from any subdirectory.
- **Volume-Level State Isolation**: Isolated translation state (`state.db`) and temporary files to individual volume directories (`.state/`), allowing multiple volumes to be translated independently within the same series.
