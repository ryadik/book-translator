# Prompts (Series Overrides)

Files in this directory serve as **series-level prompt overrides**.

All prompts are bundled in `src/book_translator/default_prompts.py`. At runtime, `path_resolver.resolve_prompt()` checks the series `prompts/` directory first — if a file is found here, it takes priority over the bundled default.

To override a prompt for a specific series, place the file in:
```
{series_root}/prompts/{prompt_name}.txt
```

## Available prompt names

| File | Stage |
|---|---|
| `translation.txt` | Translation (per-chunk) |
| `proofreading.txt` | Proofreading (per-chunk) |
| `global_proofreading.txt` | Global proofreading (full document) |
| `term_discovery.txt` | Term discovery |

## Available placeholders

| Placeholder | Description |
|---|---|
| `{text}` | Source text chunk |
| `{glossary}` | Glossary terms formatted for the prompt |
| `{style_guide}` | Contents of `style_guide.md` |
| `{world_info}` | Contents of `world_info.md` |
| `{previous_context}` | Source text of the previous chunk (translation continuity) |
| `{typography_rules}` | Language-specific typography rules from `languages.py` |
| `{target_lang_name}` | Full name of the target language (e.g. `Russian`) |
| `{source_lang_name}` | Full name of the source language (e.g. `Japanese`) |

Files in this repository (`prompts/*.txt`) are synced with the bundled defaults and can be used as a reference or starting point for customization.
