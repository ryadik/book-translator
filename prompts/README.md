# Prompts (Legacy Reference)

These prompt files are kept as reference documentation only.

Since Phase 3, all prompts are **bundled into `default_prompts.py`** and no longer
read from this directory at runtime.

To override a prompt for a specific series, place it in:
```
{series_root}/prompts/{prompt_name}.txt
```

Available prompt names: `translation`, `term_discovery`, `proofreading`, `global_proofreading`
