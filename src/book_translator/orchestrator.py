import os
import subprocess
import json
import uuid
import concurrent.futures
from contextlib import contextmanager
from datetime import datetime
from dataclasses import dataclass, field, replace as dc_replace
from pathlib import Path
from typing import Any

from book_translator.logger import setup_loggers, system_logger
from book_translator.log_viewer import update_run_manifest
from book_translator.languages import get_typography_rules, get_language_name
from book_translator import chapter_splitter
from book_translator import term_collector
from book_translator import convert_to_docx
from book_translator import convert_to_epub
from book_translator import proofreader
from book_translator import db
from book_translator import discovery
from book_translator import path_resolver
from book_translator import default_prompts
from book_translator.rate_limiter import RateLimiter
from book_translator.utils import parse_llm_json
from book_translator.exceptions import TranslationLockedError, CancellationError
from book_translator import llm_runner


class _NullProgressHandle:
    def advance(self, amount: int = 1) -> None:
        return None


class _NullInteractions:
    """Fallback interactions for tests and non-interactive backend calls."""

    @contextmanager
    def progress(self, label: str, total: int):
        yield _NullProgressHandle()

    def confirm(self, prompt: str, default: bool = False) -> bool:
        return default

    def approve_terms(
        self,
        terms: list[dict],
        tsv_path: Path,
        glossary_db_path: Path,
        source_lang: str,
        target_lang: str,
    ) -> int:
        return 0


def _stage_options(base_options: dict, stage_name: str) -> dict:
    """Build stage-specific Ollama options, applying per-stage temperature override."""
    opts = dict(base_options)
    stage_temps = opts.pop('stage_temperature', {})
    if stage_name in stage_temps:
        opts['temperature'] = stage_temps[stage_name]
    return opts


def _safe_chapter_name(chapter_name: str) -> str:
    return chapter_name.replace('/', '_').replace('\\', '_')


def _chapter_lock_path(volume_paths: Any, chapter_name: str) -> Path:
    return volume_paths.state_dir / f".lock.{_safe_chapter_name(chapter_name)}"


def _read_lock_metadata(lock_file: Path) -> dict[str, Any] | None:
    try:
        return json.loads(lock_file.read_text(encoding='utf-8'))
    except Exception:
        return None


def _acquire_chapter_lock(lock_file: Path, chapter_name: str, force: bool) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    lock_payload = {
        'pid': os.getpid(),
        'chapter_name': chapter_name,
        'run_id': run_id,
    }

    if force and lock_file.exists():
        lock_file.unlink()

    while True:
        try:
            with lock_file.open('x', encoding='utf-8') as f:
                json.dump(lock_payload, f, ensure_ascii=False)
            return lock_payload
        except FileExistsError:
            metadata = _read_lock_metadata(lock_file) or {}
            pid = metadata.get('pid')
            if isinstance(pid, int) and _is_pid_alive(pid):
                raise TranslationLockedError(
                    f"Обнаружена блокировка для главы '{chapter_name}' (PID {pid}). "
                    "Используйте `--force` для принудительного сброса."
                )
            lock_file.unlink(missing_ok=True)


def _release_chapter_lock(lock_file: Path, run_id: str) -> None:
    if not lock_file.exists():
        return
    metadata = _read_lock_metadata(lock_file)
    if metadata and metadata.get('run_id') != run_id:
        system_logger.warning("[Orchestrator] Lock уже принадлежит другому run; чужую блокировку не удаляю.")
        return
    lock_file.unlink(missing_ok=True)


def _cleanup_chapter_artifacts(volume_paths: Any, chapter_name: str) -> None:
    safe_chapter = _safe_chapter_name(chapter_name)
    for cache_file in volume_paths.cache_dir.glob(f"{safe_chapter}_chunk_*.json"):
        cache_file.unlink(missing_ok=True)

    for ext in ('.txt', '.docx', '.epub'):
        (volume_paths.output_dir / f'{chapter_name}{ext}').unlink(missing_ok=True)

    (volume_paths.state_dir / f'pending_terms_{safe_chapter}.tsv').unlink(missing_ok=True)


def _reset_in_progress_to_failed(chunks_db: Path, chapter_name: str) -> None:
    """Reset any *_in_progress chunks to *_failed so next --resume can retry them."""
    for chunk in db.get_chunks(chunks_db, chapter_name):
        if chunk['status'].endswith('_in_progress'):
            new_status = chunk['status'].replace('_in_progress', '_failed')
            db.update_chunk_status(chunks_db, chapter_name, chunk['chunk_index'], new_status)


def _is_pid_alive(pid: int) -> bool:
    """Return True if process with given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


@dataclass
class WorkerConfig:
    """Shared configuration for worker pool execution."""
    volume_paths: Any  # path_resolver.VolumePaths
    model_name: str
    chunks_db: Path
    chapter_name: str
    rate_limiter: RateLimiter
    output_format: str = "text"
    glossary_str: str = ""
    style_guide_str: str = ""
    world_info_str: str = ""
    typography_rules_str: str = ""
    target_lang_name: str = "Russian"
    source_lang_name: str = "Japanese"
    worker_timeout: int = 120
    retry_attempts: int = 3
    retry_wait_min: int = 4
    retry_wait_max: int = 10
    backend: str = "gemini"
    ollama_url: str = "http://localhost:11434"
    ollama_options: dict = field(default_factory=dict)


def _run_single_worker(
    chunk: dict[str, Any],
    prompt_template: str,
    step_name: str,
    config: WorkerConfig,
    previous_context: str = "",
) -> bool:
    worker_id = uuid.uuid4().hex[:6]
    chunk_index = chunk['chunk_index']

    try:
        db.update_chunk_status(config.chunks_db, config.chapter_name, chunk_index, f"{step_name}_in_progress")

        chunk_content = chunk['content_target'] if step_name == "reading" else chunk['content_source']
        final_prompt = (prompt_template
                        .replace('{text}', chunk_content)
                        .replace('{glossary}', config.glossary_str)
                        .replace('{style_guide}', config.style_guide_str)
                        .replace('{previous_context}', previous_context)
                        .replace('{world_info}', config.world_info_str)
                        .replace('{typography_rules}', config.typography_rules_str)
                        .replace('{target_lang_name}', config.target_lang_name)
                        .replace('{source_lang_name}', config.source_lang_name))

        stdout_output = llm_runner.run_llm(
            backend=config.backend,
            prompt=final_prompt,
            model_name=config.model_name,
            output_format=config.output_format,
            rate_limiter=config.rate_limiter,
            timeout=config.worker_timeout,
            retry_attempts=config.retry_attempts,
            retry_wait_min=config.retry_wait_min,
            retry_wait_max=config.retry_wait_max,
            worker_id=worker_id,
            label=f"chunk_{chunk_index}",
            ollama_url=config.ollama_url,
            ollama_options=config.ollama_options,
        )

        if not stdout_output or not stdout_output.strip():
            system_logger.error(f"[Orchestrator] Воркер [id: {worker_id}] для chunk_{chunk_index} вернул пустой ответ.")
            db.update_chunk_status(config.chunks_db, config.chapter_name, chunk_index, f"{step_name}_failed")
            return False

        if config.output_format == "json":
            try:
                parse_llm_json(stdout_output)
            except ValueError as e:
                system_logger.error(f"[Orchestrator] Воркер [id: {worker_id}] для chunk_{chunk_index} вернул невалидный JSON: {e}")
                db.update_chunk_status(config.chunks_db, config.chapter_name, chunk_index, f"{step_name}_failed")
                return False
            safe_chapter = config.chapter_name.replace('/', '_').replace('\\', '_')
            output_path = config.volume_paths.cache_dir / f"{safe_chapter}_chunk_{chunk_index}.json"
            try:
                output_path.write_text(stdout_output, encoding='utf-8')
            except Exception as e:
                system_logger.error(f"[Orchestrator] Ошибка при записи вывода от воркера [id: {worker_id}]: {e}")
                db.update_chunk_status(config.chunks_db, config.chapter_name, chunk_index, "discovery_failed")
                return False

        system_logger.info(f"[Orchestrator] Воркер [id: {worker_id}] для chunk_{chunk_index} успешно завершен.")

        if step_name == "discovery":
            db.update_chunk_status(config.chunks_db, config.chapter_name, chunk_index, "discovery_done")
        elif step_name in ("translation", "reading"):
            status = "translation_done" if step_name == "translation" else "reading_done"
            db.update_chunk_content(config.chunks_db, config.chapter_name, chunk_index, stdout_output, status)

        return True

    except Exception as e:
        system_logger.critical(f"[Orchestrator] КРИТИЧЕСКАЯ ОШИБКА при запуске воркера [id: {worker_id}] для chunk_{chunk_index}: {e}", exc_info=True)
        db.update_chunk_status(config.chunks_db, config.chapter_name, chunk_index, f"{step_name}_failed")
        return False


def _run_global_proofreading(
    chunks: list[dict[str, Any]],
    prompt_template: str,
    model_name: str,
    rate_limiter: RateLimiter,
    proofreading_timeout: int = 300,
    retry_attempts: int = 3,
    retry_wait_min: int = 4,
    retry_wait_max: int = 10,
    progress_handle=None,
    glossary_str: str = "",
    style_guide_str: str = "",
    target_lang_name: str = "Russian",
    backend: str = "gemini",
    ollama_url: str = "http://localhost:11434",
    ollama_options: dict | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    system_logger.info("[Orchestrator] Запуск глобальной вычитки...")

    # Format chunks for the prompt
    formatted_chunks = []
    for chunk in chunks:
        formatted_chunks.append(f"Chunk {chunk['chunk_index']}:\ncontent_source: {chunk['content_source']}\ncontent_target: {chunk['content_target']}\n")

    chunks_text = "\n".join(formatted_chunks)
    final_prompt = (prompt_template
                    .replace('{glossary}', glossary_str)
                    .replace('{style_guide}', style_guide_str)
                    .replace('{target_lang_name}', target_lang_name)
                    + "\n\n" + chunks_text)

    try:
        stdout = llm_runner.run_llm(
            backend=backend,
            prompt=final_prompt,
            model_name=model_name,
            output_format='json',
            rate_limiter=rate_limiter,
            timeout=proofreading_timeout,
            retry_attempts=retry_attempts,
            retry_wait_min=retry_wait_min,
            retry_wait_max=retry_wait_max,
            worker_id='global',
            label='global_proofreading',
            ollama_url=ollama_url,
            ollama_options=ollama_options,
        )

        diffs = parse_llm_json(stdout.strip())

        if not isinstance(diffs, list):
            system_logger.warning(f"[Orchestrator] Глобальная вычитка вернула не список. Пропуск. Ответ: {stdout[:200]}")
            return chunks, False

        # Unwrap [[{...}]] → [{...}]: json_repair sometimes wraps a list in another list
        # when the model includes extra text around the JSON.
        if diffs and isinstance(diffs[0], list):
            diffs = [item for sublist in diffs for item in sublist if isinstance(item, dict)]
            system_logger.warning("[Orchestrator] Глобальная вычитка вернула вложенный список — выполнена распаковка.")

        system_logger.info(f"[Orchestrator] Получено {len(diffs)} правок от глобальной вычитки.")
        updated_chunks, applied, skipped = proofreader.apply_diffs(chunks, diffs)
        system_logger.info(f"[Orchestrator] Правки применены: {applied}, пропущено: {skipped}.")
        if skipped > 0:
            system_logger.warning(f"[Orchestrator] {skipped} правок не применено — текст изменился или совпадений нет.")

        if progress_handle is not None:
            progress_handle.advance(1)

        return updated_chunks, True

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        system_logger.error(f"[Orchestrator] Ошибка глобальной вычитки: {e}")
        return chunks, False
    except ValueError as e:
        system_logger.error(f"[Orchestrator] Ошибка парсинга JSON от глобальной вычитки: {e}")
        return chunks, False
    except Exception as e:
        system_logger.critical(f"[Orchestrator] Неожиданная ошибка при глобальной вычитке: {e}", exc_info=True)
        return chunks, False


def _run_workers_pooled(
    max_workers: int,
    chunks: list[dict[str, Any]],
    prompt_template: str,
    step_name: str,
    config: WorkerConfig,
    contexts: dict[int, str] | None = None,
    ui=None,
):
    all_successful = True
    total_tasks = len(chunks)
    completed_tasks_count = 0
    contexts = contexts or {}

    with ui.progress(step_name, total_tasks) as handle:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _run_single_worker,
                    chunk,
                    prompt_template,
                    step_name,
                    config,
                    contexts.get(chunk['chunk_index'], ""),
                ): chunk for chunk in chunks
            }

            for future in concurrent.futures.as_completed(futures):
                chunk = futures[future]
                try:
                    success = future.result()
                    if success:
                        completed_tasks_count += 1
                        handle.advance(1)
                        system_logger.info(f"[Orchestrator] Прогресс: ({completed_tasks_count}/{total_tasks})")
                    else:
                        all_successful = False
                except CancellationError:
                    raise  # не перехватывать — пользователь отменил/поставил на паузу
                except Exception as e:
                    system_logger.critical(f"[Orchestrator] Неожиданная ошибка при обработке chunk_{chunk['chunk_index']}: {e}", exc_info=True)
                    all_successful = False

    return all_successful


# Mapping from stage name to the chunk status that marks it as pending
_STAGE_PENDING_STATUS: dict[str, str] = {
    'discovery': 'discovery_pending',
    'translation': 'translation_pending',
    'proofreading': 'reading_pending',
    'global_proofreading': 'reading_pending',
}


def run_translation_process(
    series_root: Path,
    chapter_path: Path,
    debug: bool = False,
    resume: bool = False,
    force: bool = False,
    auto_docx: bool | None = None,
    auto_epub: bool | None = None,
    restart_stage: str | None = None,
    dry_run: bool = False,
    ui=None,
    log_handler=None,
):
    current_stage = "startup"
    final_status = "failed"
    final_error: str | None = None
    if ui is None:
        ui = _NullInteractions()
    # Reset any leftover cancellation state from a previous run before starting.
    llm_runner.reset_cancellation()
    cfg = discovery.load_series_config(series_root)
    max_workers = cfg.get('workers', {}).get('max_concurrent', 50)
    worker_timeout = cfg.get('llm', {}).get('worker_timeout_seconds', 120)
    proofreading_timeout = cfg.get('llm', {}).get('proofreading_timeout_seconds', 300)
    retry_attempts = cfg.get('retry', {}).get('max_attempts', 3)
    retry_wait_min = cfg.get('retry', {}).get('wait_min_seconds', 4)
    retry_wait_max = cfg.get('retry', {}).get('wait_max_seconds', 10)
    source_lang = cfg.get('series', {}).get('source_lang', 'ja')
    target_lang = cfg.get('series', {}).get('target_lang', 'ru')

    # LLM backend config
    llm_cfg = cfg.get('llm', {})
    backend = llm_cfg.get('backend', 'gemini')
    ollama_url = llm_cfg.get('ollama_url', 'http://localhost:11434')
    ollama_options = llm_cfg.get('options', {})
    stage_models = llm_cfg.get('models', {})

    if backend == 'ollama':
        discovery_model = stage_models.get('discovery', 'qwen3:8b')
        translation_model = stage_models.get('translation', 'qwen3:30b-a3b')
        proofreading_model = stage_models.get('proofreading', 'qwen3:30b-a3b')
        global_proofreading_model = stage_models.get('global_proofreading', 'qwen3:14b')
    elif backend == 'qwen':
        qwen_model = cfg.get('qwen_cli', {}).get('model', 'qwen-plus')
        discovery_model = qwen_model
        translation_model = qwen_model
        proofreading_model = qwen_model
        global_proofreading_model = qwen_model
    else:
        gemini_model = cfg.get('gemini_cli', {}).get('model', 'gemini-2.5-pro')
        discovery_model = gemini_model
        translation_model = gemini_model
        proofreading_model = gemini_model
        global_proofreading_model = gemini_model
    typography_rules = get_typography_rules(target_lang)
    target_lang_name = get_language_name(target_lang)
    source_lang_name = get_language_name(source_lang)
    debug_mode = debug

    volume_name, chapter_name = path_resolver.resolve_volume_from_chapter(series_root, chapter_path)
    volume_paths = path_resolver.get_volume_paths(series_root, volume_name)
    path_resolver.ensure_volume_dirs(volume_paths)
    series_paths = path_resolver.get_series_paths(series_root, volume_name)

    log_artifacts = setup_loggers(
        str(volume_paths.logs_dir),
        debug_mode,
        console_handler=log_handler,
        volume_name=volume_name,
        chapter_name=chapter_name,
    )
    manifest_path = log_artifacts.get("manifest_path") if isinstance(log_artifacts, dict) else None

    def _update_manifest(**updates: Any) -> None:
        if manifest_path:
            update_run_manifest(manifest_path, **updates)

    system_logger.info("--- Запуск нового процесса перевода ---")

    glossary_db = series_root / 'glossary.db'
    chunks_db = volume_paths.chunks_db
    db.init_chunks_db(chunks_db)
    rate_limiter = RateLimiter(cfg['workers']['max_rps'])

    lock_file = _chapter_lock_path(volume_paths, chapter_name)
    lock_payload: dict[str, Any] | None = None

    if force and volume_paths.state_dir.exists():
        system_logger.info(f"[Orchestrator] Обнаружен флаг `--force`. Очистка состояния главы '{chapter_name}'...")
        db.init_chunks_db(chunks_db)
        db.clear_chapter(chunks_db, chapter_name)
        _cleanup_chapter_artifacts(volume_paths, chapter_name)

    # Load prompts (backend-aware: ollama uses simplified prompts unless user overrides)
    term_prompt_template = path_resolver.resolve_prompt(series_root, 'term_discovery', default_prompts.PROMPTS, backend, default_prompts.LOCAL_PROMPTS)
    translation_prompt_template = path_resolver.resolve_prompt(series_root, 'translation', default_prompts.PROMPTS, backend, default_prompts.LOCAL_PROMPTS)
    proofreading_prompt_template = path_resolver.resolve_prompt(series_root, 'proofreading', default_prompts.PROMPTS, backend, default_prompts.LOCAL_PROMPTS)
    global_proofreading_prompt_template = path_resolver.resolve_prompt(series_root, 'global_proofreading', default_prompts.PROMPTS, backend, default_prompts.LOCAL_PROMPTS)

    # Load context files
    style_guide_content = series_paths.style_guide.read_text(encoding='utf-8') if series_paths.style_guide else ''
    world_info_content = series_paths.world_info.read_text(encoding='utf-8') if series_paths.world_info else ''

    # Base worker configuration (glossary_str and model_name set per stage below)
    base_config = WorkerConfig(
        volume_paths=volume_paths,
        model_name=translation_model,  # default; overridden per stage via dc_replace
        chunks_db=chunks_db,
        chapter_name=chapter_name,
        rate_limiter=rate_limiter,
        style_guide_str=style_guide_content,
        world_info_str=world_info_content,
        typography_rules_str=typography_rules,
        target_lang_name=target_lang_name,
        source_lang_name=source_lang_name,
        worker_timeout=worker_timeout,
        retry_attempts=retry_attempts,
        retry_wait_min=retry_wait_min,
        retry_wait_max=retry_wait_max,
        backend=backend,
        ollama_url=ollama_url,
        ollama_options=ollama_options,
    )

    # Validate backend connectivity before starting the pipeline
    if backend == 'ollama':
        required = list({discovery_model, translation_model, proofreading_model, global_proofreading_model})
        llm_runner.check_ollama_connection(ollama_url, required)
    elif backend == 'qwen':
        llm_runner.check_qwen_binary()
    elif backend == 'gemini':
        llm_runner.check_gemini_binary()

    # Handle restart_stage: reset pipeline to the requested stage
    if restart_stage and restart_stage in _STAGE_PENDING_STATUS:
        system_logger.info(f"[Orchestrator] Принудительный перезапуск этапа: {restart_stage}")
        db.reset_chapter_stage(chunks_db, chapter_name, restart_stage, _STAGE_PENDING_STATUS[restart_stage])
        _cleanup_chapter_artifacts(volume_paths, chapter_name)

    # Dry-run: show plan without making API calls
    if dry_run:
        chunks = db.get_chunks(chunks_db, chapter_name)
        stage = db.get_chapter_stage(chunks_db, chapter_name) or 'не начат'
        system_logger.info(
            f"[Dry-run] Глава: {chapter_name}\n"
            f"  Бэкенд: {backend}\n"
            f"  Модели: discovery={discovery_model}, translation={translation_model}, "
            f"proofreading={proofreading_model}, global={global_proofreading_model}\n"
            f"  Воркеров: {max_workers}\n"
            f"  Таймаут воркера: {worker_timeout}с\n"
            f"  Таймаут вычитки: {proofreading_timeout}с\n"
            f"  Retry: {retry_attempts} попытки, {retry_wait_min}-{retry_wait_max}с\n"
            f"  Текущий этап: {stage}\n"
            f"  Чанков в БД: {len(chunks)}\n"
            f"  Глоссарий: {series_paths.glossary_db}\n"
            f"  Стайлгайд: {series_paths.style_guide or 'отсутствует'}\n"
            f"  World info: {series_paths.world_info or 'отсутствует'}"
        )
        _update_manifest(
            current_stage="dry_run",
            status="dry_run",
            finished_at=datetime.now().astimezone().isoformat(),
        )
        return None

    try:
        lock_payload = _acquire_chapter_lock(lock_file, chapter_name, force)
        system_logger.info(f"[Orchestrator] Рабочая директория для главы '{chapter_name}' заблокирована.")

        if resume:
            # Reset stalled tasks
            chunks = db.get_chunks(chunks_db, chapter_name)
            for chunk in chunks:
                if chunk['status'].endswith('_in_progress') or chunk['status'].endswith('_failed'):
                    new_status = chunk['status'].replace('_in_progress', '_pending').replace('_failed', '_pending')
                    db.update_chunk_status(chunks_db, chapter_name, chunk['chunk_index'], new_status)

        # --- Этап 0: Разделение на чанки ---
        chunks = db.get_chunks(chunks_db, chapter_name)
        if not chunks:
            if db.get_chapter_stage(chunks_db, chapter_name) is not None:
                system_logger.warning(
                    "[Orchestrator] Обнаружен chapter_state без чанков. "
                    "Сбрасываю состояние главы и выполняю чанкинг заново."
                )
                db.clear_chapter_state(chunks_db, chapter_name)
            system_logger.info("[Orchestrator] Разделение главы на чанки...")
            chunks_data = chapter_splitter.split_chapter_intelligently(
                str(chapter_path),
                cfg['splitter']['target_chunk_size'],
                cfg['splitter']['max_part_chars'],
                cfg['splitter']['min_chunk_size'],
            )
            for chunk_data in chunks_data:
                db.add_chunk(chunks_db, chapter_name, chunk_data['id'], content_source=chunk_data['text'], status="discovery_pending")
            chunks = db.get_chunks(chunks_db, chapter_name)

        # --- Этап 1: Поиск терминов ---
        stage = db.get_chapter_stage(chunks_db, chapter_name)
        if stage not in ('translation', 'proofreading', 'global_proofreading', 'complete'):
            current_stage = "discovery"
            _update_manifest(current_stage=current_stage, status="running")
            system_logger.info("\n--- ЭТАП 1: Поиск новых терминов ---")
            _cleanup_chapter_artifacts(volume_paths, chapter_name)
            terms = db.get_terms(glossary_db, source_lang, target_lang)
            glossary_content = json.dumps([dict(t) for t in terms], ensure_ascii=False, indent=2)

            pending_chunks = [c for c in db.get_chunks(chunks_db, chapter_name) if c['status'] == 'discovery_pending']
            if pending_chunks:
                discovery_config = dc_replace(base_config, output_format="json", glossary_str=glossary_content, model_name=discovery_model, ollama_options=_stage_options(ollama_options, 'discovery'))
                success = _run_workers_pooled(
                    max_workers, pending_chunks, term_prompt_template, "discovery",
                    discovery_config, ui=ui,
                )
                if not success:
                    _reset_in_progress_to_failed(chunks_db, chapter_name)
                    system_logger.error("[Orchestrator] Этап поиска терминов завершился с ошибками.")
                    final_error = "Этап поиска терминов завершился с ошибками."
                    final_status = "failed"
                    _update_manifest(current_stage=current_stage, status=final_status, error=final_error)
                    return False

            system_logger.info("\n--- Сбор и подтверждение терминов ---")
            raw_responses = []
            safe_chapter = _safe_chapter_name(chapter_name)
            for json_file in sorted(volume_paths.cache_dir.glob(f"{safe_chapter}_chunk_*.json")):
                raw_responses.append(json_file.read_text(encoding='utf-8'))

            new_terms = term_collector.collect_terms_from_responses(raw_responses)
            if new_terms:
                tsv_path = volume_paths.state_dir / f'pending_terms_{safe_chapter}.tsv'
                ui.approve_terms(new_terms, tsv_path, glossary_db, source_lang, target_lang)
            else:
                system_logger.info("[TermCollector] Новых терминов для добавления не найдено.")

            db.promote_chapter_stage(
                chunks_db,
                chapter_name,
                'translation',
                expected_statuses={'discovery_done'},
                status_mapping={'discovery_done': 'translation_pending'},
            )
            system_logger.info("[Orchestrator] Этап discovery завершён.")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа поиска терминов.")

        # --- Этап 2: Перевод ---
        stage = db.get_chapter_stage(chunks_db, chapter_name)
        if stage not in ('proofreading', 'global_proofreading', 'complete'):
            current_stage = "translation"
            _update_manifest(current_stage=current_stage, status="running")
            system_logger.info("\n--- ЭТАП 2: Перевод чанков ---")
            terms = db.get_terms(glossary_db, source_lang, target_lang)
            glossary_content = json.dumps([dict(t) for t in terms], ensure_ascii=False, indent=2)

            all_chunks = db.get_chunks(chunks_db, chapter_name)
            pending_chunks = [c for c in all_chunks if c['status'] == 'translation_pending']

            contexts = {}
            for i, chunk in enumerate(all_chunks):
                if i > 0:
                    contexts[chunk['chunk_index']] = all_chunks[i-1]['content_source']

            if pending_chunks:
                translation_config = dc_replace(base_config, glossary_str=glossary_content, model_name=translation_model, ollama_options=_stage_options(ollama_options, 'translation'))
                success = _run_workers_pooled(
                    max_workers, pending_chunks, translation_prompt_template, "translation",
                    translation_config, contexts=contexts, ui=ui,
                )
                if not success:
                    _reset_in_progress_to_failed(chunks_db, chapter_name)
                    system_logger.error("[Orchestrator] Этап перевода завершился с ошибками.")
                    final_error = "Этап перевода завершился с ошибками."
                    final_status = "failed"
                    _update_manifest(current_stage=current_stage, status=final_status, error=final_error)
                    return False

            db.promote_chapter_stage(
                chunks_db,
                chapter_name,
                'proofreading',
                expected_statuses={'translation_done'},
                status_mapping={'translation_done': 'reading_pending'},
            )
            system_logger.info("[Orchestrator] Этап translation завершён.")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа перевода.")

        # --- Этап 3: Вычитка ---
        stage = db.get_chapter_stage(chunks_db, chapter_name)
        if stage not in ('global_proofreading', 'complete'):
            current_stage = "proofreading"
            _update_manifest(current_stage=current_stage, status="running")
            system_logger.info("\n--- ЭТАП 3: Вычитка текста ---")
            terms = db.get_terms(glossary_db, source_lang, target_lang)
            glossary_content = json.dumps([dict(t) for t in terms], ensure_ascii=False, indent=2)

            all_chunks = db.get_chunks(chunks_db, chapter_name)
            pending_chunks = [c for c in all_chunks if c['status'] == 'reading_pending']

            contexts = {}
            for i, chunk in enumerate(all_chunks):
                if i > 0:
                    contexts[chunk['chunk_index']] = all_chunks[i-1]['content_target'] or ""

            if pending_chunks:
                proofreading_config = dc_replace(base_config, glossary_str=glossary_content, model_name=proofreading_model, ollama_options=_stage_options(ollama_options, 'proofreading'))
                success = _run_workers_pooled(
                    max_workers, pending_chunks, proofreading_prompt_template, "reading",
                    proofreading_config, contexts=contexts, ui=ui,
                )
                if not success:
                    _reset_in_progress_to_failed(chunks_db, chapter_name)
                    system_logger.error("[Orchestrator] Этап вычитки завершился с ошибками.")
                    final_error = "Этап вычитки завершился с ошибками."
                    final_status = "failed"
                    _update_manifest(current_stage=current_stage, status=final_status, error=final_error)
                    return False

            db.promote_chapter_stage(
                chunks_db,
                chapter_name,
                'global_proofreading',
                expected_statuses={'reading_done'},
            )
            system_logger.info("[Orchestrator] Этап proofreading завершён.")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа вычитки.")

        # --- Этап 3.5: Глобальная вычитка ---
        stage = db.get_chapter_stage(chunks_db, chapter_name)
        if stage != 'complete':
            current_stage = "global_proofreading"
            _update_manifest(current_stage=current_stage, status="running")
            system_logger.info("\n--- ЭТАП 3.5: Глобальная вычитка текста ---")

            all_chunks = db.get_chunks(chunks_db, chapter_name)
            terms = db.get_terms(glossary_db, source_lang, target_lang)
            glossary_content = json.dumps([dict(t) for t in terms], ensure_ascii=False, indent=2)

            with ui.progress("global proofreading", 1) as handle:
                updated_chunks, global_success = _run_global_proofreading(
                    all_chunks,
                    global_proofreading_prompt_template,
                    global_proofreading_model,
                    rate_limiter,
                    proofreading_timeout,
                    retry_attempts,
                    retry_wait_min,
                    retry_wait_max,
                    progress_handle=handle,
                    glossary_str=glossary_content,
                    style_guide_str=style_guide_content,
                    target_lang_name=target_lang_name,
                    backend=backend,
                    ollama_url=ollama_url,
                    ollama_options=_stage_options(ollama_options, 'global_proofreading'),
                )

            if not global_success:
                system_logger.error("[Orchestrator] Глобальная вычитка не завершилась корректно. Этап не будет помечен как complete.")
                final_error = "Глобальная вычитка не завершилась корректно."
                final_status = "failed"
                _update_manifest(current_stage=current_stage, status=final_status, error=final_error)
                return False

            db.batch_update_chunks_content(
                chunks_db,
                chapter_name,
                [{'chunk_index': c['chunk_index'], 'content_target': c['content_target'], 'status': 'reading_done'}
                 for c in updated_chunks],
            )

            db.promote_chapter_stage(
                chunks_db,
                chapter_name,
                'complete',
                expected_statuses={'reading_done'},
            )
            system_logger.info("[Orchestrator] Этап global_proofreading завершён.")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа глобальной вычитки.")

        # --- ФИНАЛЬНАЯ СБОРКА ---
        current_stage = "assembly"
        _update_manifest(current_stage=current_stage, status="running")
        system_logger.info("\n--- Сборка итогового файла ---")
        all_final_chunks = db.get_chunks(chunks_db, chapter_name)
        status_counts = db.get_chunk_status_counts(chunks_db, chapter_name)
        if not all_final_chunks:
            raise RuntimeError(f"Глава '{chapter_name}' не содержит чанков. Сборка запрещена.")
        if set(status_counts) != {'reading_done'}:
            raise RuntimeError(
                f"Глава '{chapter_name}' не готова к сборке. "
                f"Текущие статусы чанков: {status_counts}"
            )

        final_chunks = [c for c in all_final_chunks if c['status'] == 'reading_done']
        final_chunks.sort(key=lambda c: c['chunk_index'])

        txt_output_path = volume_paths.output_dir / f'{chapter_name}.txt'

        with open(txt_output_path, 'w', encoding='utf-8') as final_file:
            for i, chunk in enumerate(final_chunks):
                final_file.write(chunk['content_target'])
                if i < len(final_chunks) - 1:
                    final_file.write("\n\n")

        system_logger.info(f"✅ Глава успешно переведена и собрана в файл: {txt_output_path}")

        # --- ОПЦИОНАЛЬНАЯ КОНВЕРТАЦИЯ В DOCX ---
        if auto_docx is True or (auto_docx is None and ui.confirm("\nКонвертировать итоговый файл в .docx? (y/n): ")):
            try:
                docx_output_path = txt_output_path.with_suffix('.docx')
                convert_to_docx.convert_txt_to_docx(str(txt_output_path), str(docx_output_path))
            except ImportError:
                system_logger.error("Библиотека 'python-docx' не найдена. Установите: pip install -e .")
            except Exception as e:
                system_logger.error(f"Ошибка конвертации в .docx: {e}")

        # --- ОПЦИОНАЛЬНАЯ КОНВЕРТАЦИЯ В EPUB ---
        if auto_epub is True or (auto_epub is None and ui.confirm("\nКонвертировать итоговый файл в .epub? (y/n): ")):
            try:
                epub_output_path = txt_output_path.with_suffix('.epub')
                convert_to_epub.convert_txt_to_epub(
                    input_file=txt_output_path,
                    output_file=epub_output_path,
                    title=chapter_name,
                    language=target_lang,
                )
                system_logger.info(f"✅ EPUB сохранён: {epub_output_path}")
            except ImportError:
                system_logger.error("Библиотека 'ebooklib' не найдена. Установите: pip install ebooklib")
            except Exception as e:
                system_logger.error(f"Ошибка конвертации в .epub: {e}")
        final_status = "completed"
        _update_manifest(current_stage="complete", status=final_status)
        return True

    except CancellationError:
        # Пользователь отменил или поставил перевод на паузу — не ошибка, выходим чисто.
        final_status = "cancelled"
        _update_manifest(current_stage=current_stage, status=final_status)
        system_logger.info("[Orchestrator] Перевод отменён пользователем.")
        return False
    except TranslationLockedError:
        final_error = f"Обнаружена блокировка для главы '{chapter_name}'."
        final_status = "locked"
        _update_manifest(current_stage=current_stage, status="locked", error=final_error)
        raise
    except Exception as e:
        final_error = str(e)
        final_status = "failed"
        _update_manifest(current_stage=current_stage, status=final_status, error=final_error)
        system_logger.critical(f"[Orchestrator] НЕПЕРЕХВАЧЕННАЯ КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True)
        raise
    finally:
        if lock_payload is not None:
            _release_chapter_lock(lock_file, lock_payload['run_id'])
        if not lock_file.exists():
            system_logger.info("[Orchestrator] Блокировка снята.")
        system_logger.info("\n[Orchestrator] Процесс завершен.")
        _update_manifest(
            current_stage=current_stage,
            status=final_status,
            error=final_error,
            finished_at=datetime.now().astimezone().isoformat(),
        )
