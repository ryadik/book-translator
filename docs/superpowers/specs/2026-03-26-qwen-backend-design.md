# Qwen Backend Integration Design

**Date:** 2026-03-26
**Status:** Approved

## Goal

Add `qwen` as a third LLM backend (alongside `gemini` and `ollama`). The `qwen-code` CLI is a fork of `gemini-cli` with the same stdin/stdout subprocess interface. Qwen is a cloud backend — its performance profile matches gemini (fast inference, high concurrency).

## Approach

**Variant B — Separate `run_qwen()` function.** Mirrors `run_gemini()` with qwen-specific command construction. Follows the existing project pattern of one function per backend.

## Design

### 1. llm_runner.py

#### `run_qwen()`

Mirrors `run_gemini()`. Differences:

| Aspect | gemini | qwen |
|--------|--------|------|
| Binary | `gemini` | `qwen` |
| Headless flag | `-p ' '` | `--approval-mode yolo` |
| Command | `['gemini', '-m', model, '-p', ' ', '--output-format', fmt]` | `['qwen', '-m', model, '--output-format', fmt, '--approval-mode', 'yolo']` |

Shared behavior (identical to `run_gemini`):
- Prompt via stdin (`proc.communicate(input=prompt)`)
- `_active_processes` registry for cancellation
- `_cancelled` check before each attempt
- `@retry` with `CalledProcessError` and `TimeoutExpired`
- Rate limiter acquisition
- `cwd=_get_subprocess_cwd()`
- Logging to `input_logger` / `output_logger` / `system_logger`

Signature: same as `run_gemini()` (prompt, model_name, output_format, rate_limiter, timeout, retry_attempts, retry_wait_min, retry_wait_max, worker_id, label).

#### `check_qwen_binary()`

Pre-flight check. Uses `shutil.which('qwen')`. Raises `RuntimeError` with install instructions if not found. Called by orchestrator before pipeline starts.

#### `run_llm()` dispatcher

New branch:
```python
if backend == "qwen":
    return run_qwen(...)
elif backend == "ollama":
    return run_ollama(...)
return run_gemini(...)
```

No signature change — qwen needs no extra params beyond what `run_gemini` uses.

### 2. discovery.py

#### Validation

Update `_validate_config`:
```python
if backend not in ('gemini', 'ollama', 'qwen'):
    raise ValueError(...)
```

#### Defaults

Timeout defaults: qwen is cloud → 120s worker / 300s proofreading (same as gemini, not 600s/900s ollama).

```python
_default_worker_timeout = 600 if _backend == 'ollama' else 120
_default_proofread_timeout = 900 if _backend == 'ollama' else 300
```

No change needed — the `else` already covers both gemini and qwen.

Existing `[llm.models]` and `[llm.options]` defaults still set for all backends. The orchestrator ignores them for gemini/qwen (reads from `[gemini_cli]`/`[qwen_cli]` instead). This is existing behavior, not new.

### 3. init_screen.py

#### TOML template

New `TOML_TEMPLATE_QWEN`:
```toml
[series]
name = "{name}"
source_lang = "{source_lang}"
target_lang = "{target_lang}"

[llm]
backend = "qwen"

[qwen_cli]
model = "qwen-plus"
worker_timeout_seconds = 120
proofreading_timeout_seconds = 300

[retry]
max_attempts = 3
wait_min_seconds = 4
wait_max_seconds = 10

[splitter]
target_chunk_size = 600
max_part_chars = 800
min_chunk_size = 300

[workers]
max_concurrent = 50
max_rps = 2.0
```

#### Template selection in `run_init()`

```python
templates = {'ollama': TOML_TEMPLATE_OLLAMA, 'qwen': TOML_TEMPLATE_QWEN}
template = templates.get(backend, TOML_TEMPLATE_GEMINI)
```

#### UI

Third radio button in `InitScreen`:
```
RadioButton("Qwen (облачный)", id="radio-qwen")
```

Backend detection in `_create_series()` reads which radio is selected.

### 4. orchestrator.py

#### Model selection

```python
elif backend == 'qwen':
    qwen_model = cfg.get('qwen_cli', {}).get('model', 'qwen-plus')
    discovery_model = translation_model = proofreading_model = global_proofreading_model = qwen_model
```

Single model for all stages (same pattern as gemini).

#### Pre-flight check

```python
if backend == 'qwen':
    llm_runner.check_qwen_binary()
```

### 5. path_resolver.py / prompts

No changes. `resolve_prompt()` uses `LOCAL_PROMPTS` only when `backend == 'ollama'`. For qwen, full cloud prompts (`PROMPTS`) are used — qwen-plus is a capable cloud model.

### 6. dashboard.py

No code changes needed. The info bar already reads `config["llm"]["backend"]` and displays it. "qwen" will appear automatically.

## Files Changed

| File | Change |
|------|--------|
| `src/book_translator/llm_runner.py` | Add `run_qwen()`, `check_qwen_binary()`, update `run_llm()` |
| `src/book_translator/discovery.py` | Update validation to accept `'qwen'` |
| `src/book_translator/textual_app/screens/init_screen.py` | Add `TOML_TEMPLATE_QWEN`, radio button, template selection |
| `src/book_translator/orchestrator.py` | Add qwen model selection, pre-flight check |
| `tests/test_llm_runner.py` | Tests for `run_qwen()` and `check_qwen_binary()` |
| `tests/test_init_cmd.py` | Test for qwen backend init |
| `tests/test_discovery.py` | Test qwen validation |

## Files NOT Changed

- `db.py`, `chapter_splitter.py`, `term_collector.py`, `proofreader.py`, `glossary_manager.py`, `path_resolver.py`, `dashboard.py` — no backend dependency.

## Security Considerations

- Prompt passed via stdin, not CLI args — prevents leakage via `ps aux`
- No user-controlled strings interpolated into subprocess command array — prevents command injection
- `check_qwen_binary()` uses `shutil.which()`, not shell execution
- Rate limiter applied before process spawn — prevents resource exhaustion

## Testing Strategy

- **`test_llm_runner.py`**: success path, timeout, CalledProcessError, cancellation, `check_qwen_binary` (present/missing)
- **`test_init_cmd.py`**: `test_init_qwen_backend` — TOML structure, backend field, model, workers
- **`test_discovery.py`**: qwen passes validation; invalid backend rejected
