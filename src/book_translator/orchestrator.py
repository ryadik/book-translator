import os
import subprocess
import json
import uuid
import concurrent.futures
from dataclasses import dataclass, field, replace as dc_replace
from pathlib import Path
from typing import Any

from book_translator.logger import setup_loggers, system_logger
from book_translator.languages import get_typography_rules, get_language_name
from book_translator import chapter_splitter
from book_translator.tui import create_progress
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
from book_translator.exceptions import TranslationLockedError
from book_translator import llm_runner


@dataclass
class WorkerConfig:
    """Shared configuration for worker pool execution."""
    cli_args: dict[str, Any]
    volume_paths: Any  # path_resolver.VolumePaths
    model_name: str
    chunks_db: Path
    chapter_name: str
    rate_limiter: RateLimiter
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


def _run_single_worker(
    chunk: dict[str, Any],
    prompt_template: str,
    step_name: str,
    output_suffix: str,
    config: WorkerConfig,
    previous_context: str = "",
) -> bool:
    worker_id = uuid.uuid4().hex[:6]
    chunk_index = chunk['chunk_index']

    try:
        db.add_chunk(config.chunks_db, config.chapter_name, chunk_index, content_source=chunk['content_source'], content_target=chunk['content_target'], status=f"{step_name}_in_progress")

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

        stdout_output = llm_runner.run_gemini(
            prompt=final_prompt,
            model_name=config.model_name,
            output_format=config.cli_args.get('output_format', 'text'),
            rate_limiter=config.rate_limiter,
            timeout=config.worker_timeout,
            retry_attempts=config.retry_attempts,
            retry_wait_min=config.retry_wait_min,
            retry_wait_max=config.retry_wait_max,
            worker_id=worker_id,
            label=f"chunk_{chunk_index}",
        )

        if output_suffix == ".json":
            output_path = config.volume_paths.cache_dir / f"chunk_{chunk_index}{output_suffix}"
            try:
                output_path.write_text(stdout_output, encoding='utf-8')
            except Exception as e:
                system_logger.error(f"[Orchestrator] Ошибка при записи вывода от воркера [id: {worker_id}]: {e}")

        system_logger.info(f"[Orchestrator] Воркер [id: {worker_id}] для chunk_{chunk_index} успешно завершен.")

        if step_name == "discovery":
            db.add_chunk(config.chunks_db, config.chapter_name, chunk_index, content_source=chunk['content_source'], content_target=chunk['content_target'], status="discovery_done")
        elif step_name == "translation":
            db.add_chunk(config.chunks_db, config.chapter_name, chunk_index, content_source=chunk['content_source'], content_target=stdout_output, status="translation_done")
        elif step_name == "reading":
            db.add_chunk(config.chunks_db, config.chapter_name, chunk_index, content_source=chunk['content_source'], content_target=stdout_output, status="reading_done")

        return True

    except Exception as e:
        system_logger.critical(f"[Orchestrator] КРИТИЧЕСКАЯ ОШИБКА при запуске воркера [id: {worker_id}] для chunk_{chunk_index}: {e}", exc_info=True)
        db.add_chunk(config.chunks_db, config.chapter_name, chunk_index, content_source=chunk['content_source'], content_target=chunk['content_target'], status=f"{step_name}_failed")
        return False


def _run_global_proofreading(
    chunks: list[dict[str, Any]],
    prompt_template: str,
    model_name: str,
    rate_limiter: RateLimiter,
    proofreading_timeout: int = 300,
    progress=None,
    task_id=None,
    glossary_str: str = "",
    style_guide_str: str = "",
    target_lang_name: str = "Russian"
) -> list[dict[str, Any]]:
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
        stdout = llm_runner.run_gemini(
            prompt=final_prompt,
            model_name=model_name,
            output_format='json',
            rate_limiter=rate_limiter,
            timeout=proofreading_timeout,
            retry_attempts=1,
            retry_wait_min=4,
            retry_wait_max=10,
            worker_id='global',
            label='global_proofreading',
        )

        diffs = parse_llm_json(stdout.strip())

        if not isinstance(diffs, list):
            system_logger.warning(f"[Orchestrator] Глобальная вычитка вернула не список. Пропуск. Ответ: {stdout[:200]}")
            return chunks

        system_logger.info(f"[Orchestrator] Получено {len(diffs)} правок от глобальной вычитки.")
        updated_chunks = proofreader.apply_diffs(chunks, diffs)

        if progress and task_id is not None:
            progress.update(task_id, advance=1)

        return updated_chunks

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        system_logger.error(f"[Orchestrator] Ошибка глобальной вычитки: {e}")
        return chunks
    except ValueError as e:
        system_logger.error(f"[Orchestrator] Ошибка парсинга JSON от глобальной вычитки: {e}")
        return chunks
    except Exception as e:
        system_logger.critical(f"[Orchestrator] Неожиданная ошибка при глобальной вычитке: {e}", exc_info=True)
        return chunks


def _run_workers_pooled(
    max_workers: int,
    chunks: list[dict[str, Any]],
    prompt_template: str,
    step_name: str,
    output_suffix: str,
    config: WorkerConfig,
    contexts: dict[int, str] | None = None,
):
    all_successful = True
    total_tasks = len(chunks)
    completed_tasks_count = 0
    contexts = contexts or {}

    with create_progress() as progress:
        task_id = progress.add_task(f"[cyan]Processing {step_name}...", total=total_tasks)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _run_single_worker,
                    chunk,
                    prompt_template,
                    step_name,
                    output_suffix,
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
                        progress.update(task_id, advance=1)
                        system_logger.info(f"[Orchestrator] Прогресс: ({completed_tasks_count}/{total_tasks})")
                    else:
                        all_successful = False
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
):
    cfg = discovery.load_series_config(series_root)
    max_workers = cfg.get('workers', {}).get('max_concurrent', 50)
    model_name = cfg.get('gemini_cli', {}).get('model', 'gemini-2.5-pro')
    worker_timeout = cfg.get('gemini_cli', {}).get('worker_timeout_seconds', 120)
    proofreading_timeout = cfg.get('gemini_cli', {}).get('proofreading_timeout_seconds', 300)
    retry_attempts = cfg.get('retry', {}).get('max_attempts', 3)
    retry_wait_min = cfg.get('retry', {}).get('wait_min_seconds', 4)
    retry_wait_max = cfg.get('retry', {}).get('wait_max_seconds', 10)
    source_lang = cfg.get('series', {}).get('source_lang', 'ja')
    target_lang = cfg.get('series', {}).get('target_lang', 'ru')
    typography_rules = get_typography_rules(target_lang)
    target_lang_name = get_language_name(target_lang)
    source_lang_name = get_language_name(source_lang)
    debug_mode = debug

    volume_name, chapter_name = path_resolver.resolve_volume_from_chapter(series_root, chapter_path)
    volume_paths = path_resolver.get_volume_paths(series_root, volume_name)
    path_resolver.ensure_volume_dirs(volume_paths)
    series_paths = path_resolver.get_series_paths(series_root, volume_name)

    setup_loggers(str(volume_paths.logs_dir), debug_mode)
    system_logger.info("--- Запуск нового процесса перевода ---")

    glossary_db = series_root / 'glossary.db'
    chunks_db = volume_paths.chunks_db
    db.init_chunks_db(chunks_db)
    rate_limiter = RateLimiter(2.0)

    lock_file = volume_paths.state_dir / '.lock'

    if lock_file.exists() and not resume:
        raise TranslationLockedError(
            f"Обнаружена блокировка для главы '{chapter_name}'. "
            "Используйте `--resume` для продолжения или `--force` для сброса."
        )

    if force and volume_paths.state_dir.exists():
        system_logger.info("[Orchestrator] Обнаружен флаг `--force`. Полная очистка состояния...")
        if lock_file.exists():
            lock_file.unlink()
        if chunks_db.exists():
            chunks_db.unlink()
        db.init_chunks_db(chunks_db)

    # Load prompts
    term_prompt_template = path_resolver.resolve_prompt(series_root, 'term_discovery', default_prompts.PROMPTS)
    translation_prompt_template = path_resolver.resolve_prompt(series_root, 'translation', default_prompts.PROMPTS)
    proofreading_prompt_template = path_resolver.resolve_prompt(series_root, 'proofreading', default_prompts.PROMPTS)
    global_proofreading_prompt_template = path_resolver.resolve_prompt(series_root, 'global_proofreading', default_prompts.PROMPTS)

    # Load context files
    style_guide_content = series_paths.style_guide.read_text(encoding='utf-8') if series_paths.style_guide else ''
    world_info_content = series_paths.world_info.read_text(encoding='utf-8') if series_paths.world_info else ''

    # Base worker configuration (glossary_str set per stage below)
    base_config = WorkerConfig(
        cli_args={},
        volume_paths=volume_paths,
        model_name=model_name,
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
    )

    # Handle restart_stage: reset pipeline to the requested stage
    if restart_stage and restart_stage in _STAGE_PENDING_STATUS:
        system_logger.info(f"[Orchestrator] Принудительный перезапуск этапа: {restart_stage}")
        db.reset_chapter_stage(chunks_db, chapter_name, restart_stage, _STAGE_PENDING_STATUS[restart_stage])

    # Dry-run: show plan without making API calls
    if dry_run:
        chunks = db.get_chunks(chunks_db, chapter_name)
        stage = db.get_chapter_stage(chunks_db, chapter_name) or 'не начат'
        system_logger.info(
            f"[Dry-run] Глава: {chapter_name}\n"
            f"  Модель: {model_name}\n"
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
        return

    try:
        lock_file.write_text(str(os.getpid()))
        system_logger.info(f"[Orchestrator] Рабочая директория для главы '{chapter_name}' заблокирована.")

        if resume:
            # Reset stalled tasks
            chunks = db.get_chunks(chunks_db, chapter_name)
            for chunk in chunks:
                if chunk['status'].endswith('_in_progress') or chunk['status'].endswith('_failed'):
                    new_status = chunk['status'].replace('_in_progress', '_pending').replace('_failed', '_pending')
                    db.add_chunk(chunks_db, chapter_name, chunk['chunk_index'], content_source=chunk['content_source'], content_target=chunk['content_target'], status=new_status)

        # --- Этап 0: Разделение на чанки ---
        chunks = db.get_chunks(chunks_db, chapter_name)
        if not chunks and not resume:
            system_logger.info("[Orchestrator] Разделение главы на чанки...")
            temp_split_dir = volume_paths.cache_dir / "temp_split"
            chunks_data = chapter_splitter.split_chapter_intelligently(
                str(chapter_path),
                str(temp_split_dir),
                cfg['splitter']['target_chunk_size'],
                cfg['splitter']['max_part_chars']
            )
            for chunk_data in chunks_data:
                db.add_chunk(chunks_db, chapter_name, chunk_data['id'], content_source=chunk_data['text'], status="discovery_pending")
            chunks = db.get_chunks(chunks_db, chapter_name)

        # --- Этап 1: Поиск терминов ---
        stage = db.get_chapter_stage(chunks_db, chapter_name)
        if stage not in ('translation', 'proofreading', 'global_proofreading', 'complete'):
            system_logger.info("\n--- ЭТАП 1: Поиск новых терминов ---")
            terms = db.get_terms(glossary_db, source_lang, target_lang)
            glossary_content = json.dumps([dict(t) for t in terms], ensure_ascii=False, indent=2)

            pending_chunks = [c for c in db.get_chunks(chunks_db, chapter_name) if c['status'] == 'discovery_pending']
            if pending_chunks:
                discovery_config = dc_replace(base_config, cli_args={"output_format": "json"}, glossary_str=glossary_content)
                success = _run_workers_pooled(
                    max_workers, pending_chunks, term_prompt_template, "discovery", ".json",
                    discovery_config,
                )
                if not success:
                    system_logger.error("[Orchestrator] Этап поиска терминов завершился с ошибками.")
                    return

            system_logger.info("\n--- Сбор и подтверждение терминов ---")
            raw_responses = []
            for json_file in volume_paths.cache_dir.glob("*.json"):
                raw_responses.append(json_file.read_text(encoding='utf-8'))

            new_terms = term_collector.collect_terms_from_responses(raw_responses)
            if any(new_terms.values()):
                tsv_path = volume_paths.state_dir / 'pending_terms.tsv'
                term_collector.approve_via_tsv(new_terms, tsv_path, glossary_db, source_lang, target_lang)
            else:
                system_logger.info("[TermCollector] Новых терминов для добавления не найдено.")

            db.set_chapter_stage(chunks_db, chapter_name, 'translation')
            system_logger.info("[Orchestrator] Этап discovery завершён.")

            for chunk in db.get_chunks(chunks_db, chapter_name):
                if chunk['status'] == 'discovery_done':
                    db.add_chunk(chunks_db, chapter_name, chunk['chunk_index'], content_source=chunk['content_source'], content_target=chunk['content_target'], status="translation_pending")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа поиска терминов.")

        # --- Этап 2: Перевод ---
        stage = db.get_chapter_stage(chunks_db, chapter_name)
        if stage not in ('proofreading', 'global_proofreading', 'complete'):
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
                translation_config = dc_replace(base_config, cli_args={"output_format": "text"}, glossary_str=glossary_content)
                success = _run_workers_pooled(
                    max_workers, pending_chunks, translation_prompt_template, "translation", ".txt",
                    translation_config, contexts=contexts,
                )
                if not success:
                    system_logger.error("[Orchestrator] Этап перевода завершился с ошибками.")
                    return

            db.set_chapter_stage(chunks_db, chapter_name, 'proofreading')
            system_logger.info("[Orchestrator] Этап translation завершён.")

            for chunk in db.get_chunks(chunks_db, chapter_name):
                if chunk['status'] == 'translation_done':
                    db.add_chunk(chunks_db, chapter_name, chunk['chunk_index'], content_source=chunk['content_source'], content_target=chunk['content_target'], status="reading_pending")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа перевода.")

        # --- Этап 3: Вычитка ---
        stage = db.get_chapter_stage(chunks_db, chapter_name)
        if stage not in ('global_proofreading', 'complete'):
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
                proofreading_config = dc_replace(base_config, cli_args={"output_format": "text"}, glossary_str=glossary_content)
                success = _run_workers_pooled(
                    max_workers, pending_chunks, proofreading_prompt_template, "reading", ".txt",
                    proofreading_config, contexts=contexts,
                )
                if not success:
                    system_logger.error("[Orchestrator] Этап вычитки завершился с ошибками.")
                    return

            db.set_chapter_stage(chunks_db, chapter_name, 'global_proofreading')
            system_logger.info("[Orchestrator] Этап proofreading завершён.")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа вычитки.")

        # --- Этап 3.5: Глобальная вычитка ---
        stage = db.get_chapter_stage(chunks_db, chapter_name)
        if stage != 'complete':
            system_logger.info("\n--- ЭТАП 3.5: Глобальная вычитка текста ---")

            all_chunks = db.get_chunks(chunks_db, chapter_name)
            terms = db.get_terms(glossary_db, source_lang, target_lang)
            glossary_content = json.dumps([dict(t) for t in terms], ensure_ascii=False, indent=2)

            with create_progress() as progress:
                task_id = progress.add_task("[cyan]Processing global proofreading...", total=1)
                updated_chunks = _run_global_proofreading(
                    all_chunks,
                    global_proofreading_prompt_template,
                    model_name,
                    rate_limiter,
                    proofreading_timeout,
                    progress,
                    task_id,
                    glossary_str=glossary_content,
                    style_guide_str=style_guide_content,
                    target_lang_name=target_lang_name
                )

            for chunk in updated_chunks:
                db.add_chunk(chunks_db, chapter_name, chunk['chunk_index'], content_source=chunk['content_source'], content_target=chunk['content_target'], status="reading_done")

            db.set_chapter_stage(chunks_db, chapter_name, 'complete')
            system_logger.info("[Orchestrator] Этап global_proofreading завершён.")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа глобальной вычитки.")

        # --- ФИНАЛЬНАЯ СБОРКА ---
        system_logger.info("\n--- Сборка итогового файла ---")
        final_chunks = [c for c in db.get_chunks(chunks_db, chapter_name) if c['status'] == 'reading_done']
        final_chunks.sort(key=lambda c: c['chunk_index'])

        txt_output_path = volume_paths.output_dir / f'{chapter_name}.txt'

        with open(txt_output_path, 'w', encoding='utf-8') as final_file:
            for i, chunk in enumerate(final_chunks):
                final_file.write(chunk['content_target'])
                if i < len(final_chunks) - 1:
                    final_file.write("\n\n")

        system_logger.info(f"✅ Глава успешно переведена и собрана в файл: {txt_output_path}")

        # --- ОПЦИОНАЛЬНАЯ КОНВЕРТАЦИЯ В DOCX ---
        if auto_docx is True or (auto_docx is None and input("\nКонвертировать итоговый файл в .docx? (y/n): ").lower() == 'y'):
            try:
                docx_output_path = txt_output_path.with_suffix('.docx')
                convert_to_docx.convert_txt_to_docx(str(txt_output_path), str(docx_output_path))
            except ImportError:
                system_logger.error("Библиотека 'python-docx' не найдена. Установите: pip install -e .")
            except Exception as e:
                system_logger.error(f"Ошибка конвертации в .docx: {e}")

        # --- ОПЦИОНАЛЬНАЯ КОНВЕРТАЦИЯ В EPUB ---
        if auto_epub is True or (auto_epub is None and input("\nКонвертировать итоговый файл в .epub? (y/n): ").lower() == 'y'):
            try:
                epub_output_path = txt_output_path.with_suffix('.epub')
                convert_to_epub.convert_txt_to_epub(
                    input_file=txt_output_path,
                    output_file=epub_output_path,
                    title=chapter_name,
                    language=target_lang,
                )
            except ImportError:
                system_logger.error("Библиотека 'ebooklib' не найдена. Установите: pip install ebooklib")
            except Exception as e:
                system_logger.error(f"Ошибка конвертации в .epub: {e}")

    except Exception as e:
        system_logger.critical(f"[Orchestrator] НЕПЕРЕХВАЧЕННАЯ КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True)
    finally:
        if lock_file.exists():
            lock_file.unlink()
            system_logger.info("[Orchestrator] Блокировка снята.")
        system_logger.info("\n[Orchestrator] Процесс завершен.")
