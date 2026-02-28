import os
import subprocess
import time
import json
import re
import shutil
import sys
import uuid
import concurrent.futures
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Dict, Any, List, Optional

from book_translator.logger import setup_loggers, system_logger, input_logger, output_logger
from book_translator import chapter_splitter
from book_translator.tui import create_progress
from book_translator import term_collector
from book_translator import convert_to_docx
from book_translator import proofreader
from book_translator import db
from book_translator import discovery
from book_translator import path_resolver
from book_translator import default_prompts
from book_translator.rate_limiter import RateLimiter


def _run_single_worker(
    chunk: Dict[str, Any],
    prompt_template: str,
    step_name: str,
    output_suffix: str,
    cli_args: Dict[str, Any],
    volume_paths,
    model_name: str,
    glossary_str: str,
    style_guide_str: str,
    chunks_db: Path,
    chapter_name: str,
    rate_limiter: RateLimiter,
    previous_context: str = ""
) -> bool:
    worker_id = uuid.uuid4().hex[:6]
    chunk_index = chunk['chunk_index']
    
    try:
        db.add_chunk(chunks_db, chapter_name, chunk_index, content_source=chunk['content_source'], content_target=chunk['content_target'], status=f"{step_name}_in_progress")
        
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=4, max=10),
            retry=retry_if_exception_type((subprocess.CalledProcessError, subprocess.TimeoutExpired)),
            reraise=True
        )
        def _do_run():
            chunk_content = chunk['content_target'] if step_name == "reading" else chunk['content_source']
            final_prompt = prompt_template.replace('{text}', chunk_content).replace('{glossary}', glossary_str).replace('{style_guide}', style_guide_str).replace('{previous_context}', previous_context)
            
            input_logger.info(f"[{worker_id}] --- PROMPT FOR: chunk_{chunk_index} ---\n{final_prompt}\n")

            output_filename = f"chunk_{chunk_index}.txt"
            
            if output_suffix == ".json":
                output_path = volume_paths.cache_dir / f"chunk_{chunk_index}{output_suffix}"
            else:
                output_path = None
            
            command = ['gemini', '-m', model_name, '-p', final_prompt, '--output-format', cli_args.get('output_format', 'text')]

            system_logger.info(f"[Orchestrator] Запущен воркер [id: {worker_id}] для: chunk_{chunk_index}")

            try:
                with rate_limiter:
                    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', timeout=120, check=True)
                return result.stdout, output_path, output_filename
            except subprocess.CalledProcessError as e:
                system_logger.error(f"[Orchestrator] Воркер [id: {worker_id}] для chunk_{chunk_index} завершился с ошибкой (код: {e.returncode}).")
                output_logger.error(f"[{worker_id}] --- FAILED OUTPUT FROM: chunk_{chunk_index} ---\n{e.stderr.strip()}\n")
                raise
            except subprocess.TimeoutExpired as e:
                system_logger.error(f"[Orchestrator] Воркер [id: {worker_id}] превысил лимит времени (120с). Принудительное завершение.")
                raise

        stdout_output, output_path, output_filename = _do_run()
        
        system_logger.info(f"[Orchestrator] Воркер [id: {worker_id}] для {output_filename} успешно завершен.")
        
        if output_path:
            try:
                output_path.write_text(stdout_output, encoding='utf-8')
            except Exception as e:
                system_logger.error(f"[Orchestrator] Ошибка при записи вывода от воркера [id: {worker_id}]: {e}")

        output_logger.info(f"[{worker_id}] --- SUCCESSFUL OUTPUT FROM: {output_filename} ---\n{stdout_output}\n")

        if step_name == "discovery":
            db.add_chunk(chunks_db, chapter_name, chunk_index, content_source=chunk['content_source'], content_target=chunk['content_target'], status="discovery_done")
        elif step_name == "translation":
            db.add_chunk(chunks_db, chapter_name, chunk_index, content_source=chunk['content_source'], content_target=stdout_output, status="translation_done")
        elif step_name == "reading":
            db.add_chunk(chunks_db, chapter_name, chunk_index, content_source=chunk['content_source'], content_target=stdout_output, status="reading_done")
            
        return True

    except Exception as e:
        system_logger.critical(f"[Orchestrator] КРИТИЧЕСКАЯ ОШИБКА при запуске воркера [id: {worker_id}] для chunk_{chunk_index}: {e}", exc_info=True)
        db.add_chunk(chunks_db, chapter_name, chunk_index, content_source=chunk['content_source'], content_target=chunk['content_target'], status=f"{step_name}_failed")
        return False


def _run_global_proofreading(
    chunks: List[Dict[str, Any]],
    prompt_template: str,
    model_name: str,
    rate_limiter: RateLimiter,
    progress=None,
    task_id=None
) -> List[Dict[str, Any]]:
    system_logger.info("[Orchestrator] Запуск глобальной вычитки...")
    
    # Format chunks for the prompt
    formatted_chunks = []
    for chunk in chunks:
        formatted_chunks.append(f"Chunk {chunk['chunk_index']}:\ncontent_source: {chunk['content_source']}\ncontent_target: {chunk['content_target']}\n")
    
    chunks_text = "\n".join(formatted_chunks)
    final_prompt = prompt_template + "\n\n" + chunks_text
    
    # Replace content_en with content_source in the prompt template if needed
    final_prompt = final_prompt.replace("content_en", "content_source")
    
    command = ['gemini', '-m', model_name, '-p', final_prompt, '--output-format', 'json']
    
    try:
        with rate_limiter:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', timeout=300, check=True)
        
        raw_output = result.stdout.strip()
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:]
        if raw_output.startswith("```"):
            raw_output = raw_output[3:]
        if raw_output.endswith("```"):
            raw_output = raw_output[:-3]
        raw_output = raw_output.strip()
        
        diffs = json.loads(raw_output)
        if isinstance(diffs, dict) and "response" in diffs:
            # gemini-cli might wrap the output in a JSON object with stats
            response_text = diffs["response"]
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            diffs = json.loads(response_text)
            
        if not isinstance(diffs, list):
            system_logger.warning(f"[Orchestrator] Глобальная вычитка вернула не список. Пропуск. Ответ: {raw_output}")
            return chunks
            
        system_logger.info(f"[Orchestrator] Получено {len(diffs)} правок от глобальной вычитки.")
        updated_chunks = proofreader.apply_diffs(chunks, diffs)
        
        if progress and task_id is not None:
            progress.update(task_id, advance=1)
            
        return updated_chunks
        
    except subprocess.CalledProcessError as e:
        system_logger.error(f"[Orchestrator] Ошибка глобальной вычитки (код: {e.returncode}).\n{e.stderr.strip()}")
        return chunks
    except subprocess.TimeoutExpired:
        system_logger.error("[Orchestrator] Глобальная вычитка превысила лимит времени (300с).")
        return chunks
    except json.JSONDecodeError:
        system_logger.error("[Orchestrator] Ошибка парсинга JSON от глобальной вычитки.")
        return chunks
    except Exception as e:
        system_logger.critical(f"[Orchestrator] Неожиданная ошибка при глобальной вычитке: {e}", exc_info=True)
        return chunks


def _run_workers_pooled(
    max_workers: int,
    chunks: List[Dict[str, Any]],
    prompt_template: str,
    step_name: str,
    output_suffix: str,
    cli_args: Dict[str, Any],
    volume_paths,
    model_name: str,
    chunks_db: Path,
    chapter_name: str,
    rate_limiter: RateLimiter,
    glossary_str = "",
    style_guide_str = "",
    contexts: Optional[Dict[int, str]] = None
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
                    cli_args,
                    volume_paths,
                    model_name,
                    glossary_str,
                    style_guide_str,
                    chunks_db,
                    chapter_name,
                    rate_limiter,
                    contexts.get(chunk['chunk_index'], "")
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


def run_translation_process(
    series_root: Path,
    chapter_path: Path,
    debug: bool = False,
    resume: bool = False,
    force: bool = False
):
    cfg = discovery.load_series_config(series_root)
    max_workers = cfg.get('workers', {}).get('max_concurrent', 50)
    model_name = cfg.get('gemini_cli', {}).get('model', 'gemini-2.5-pro')
    source_lang = cfg.get('series', {}).get('source_lang', 'ja')
    target_lang = cfg.get('series', {}).get('target_lang', 'ru')
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
    discovery_checkpoint = volume_paths.state_dir / '.stage_discovery_complete'
    translation_checkpoint = volume_paths.state_dir / '.stage_translation_complete'
    reading_checkpoint = volume_paths.state_dir / '.stage_reading_complete'
    global_reading_checkpoint = volume_paths.state_dir / '.stage_global_reading_complete'

    if lock_file.exists() and not resume:
        system_logger.warning(f"[Orchestrator] ОБНАРУЖЕНА БЛОКИРОВКА для главы '{chapter_name}'. Используйте `--resume` или `--force`.")
        sys.exit(1)

    if force and volume_paths.state_dir.exists():
        system_logger.info("[Orchestrator] Обнаружен флаг `--force`. Полная очистка рабочей директории...")
        # Remove state files only (keep dirs)
        for f in [lock_file, discovery_checkpoint, translation_checkpoint, reading_checkpoint, global_reading_checkpoint]:
            if f.exists():
                f.unlink()
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

    try:
        lock_file.write_text(str(os.getpid()))
        system_logger.info(f"[Orchestrator] Рабочая директория для главы '{chapter_name}' создана и заблокирована.")

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
        if not discovery_checkpoint.exists():
            system_logger.info("\n--- ЭТАП 1: Поиск новых терминов ---")
            terms = db.get_terms(glossary_db, source_lang, target_lang)
            glossary_content = json.dumps([dict(t) for t in terms], ensure_ascii=False, indent=2)
            
            pending_chunks = [c for c in db.get_chunks(chunks_db, chapter_name) if c['status'] == 'discovery_pending']
            if pending_chunks:
                success = _run_workers_pooled(max_workers, pending_chunks, term_prompt_template, "discovery", ".json", {"output_format": "json"}, volume_paths, model_name, chunks_db, chapter_name, rate_limiter, glossary_str=glossary_content)
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
            
            discovery_checkpoint.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
            system_logger.info("[Orchestrator] Чекпоинт 'discovery_complete' создан.")
            
            for chunk in db.get_chunks(chunks_db, chapter_name):
                if chunk['status'] == 'discovery_done':
                    db.add_chunk(chunks_db, chapter_name, chunk['chunk_index'], content_source=chunk['content_source'], content_target=chunk['content_target'], status="translation_pending")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа поиска терминов.")
        
        # --- Этап 2: Перевод ---
        if not translation_checkpoint.exists():
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
                success = _run_workers_pooled(max_workers, pending_chunks, translation_prompt_template, "translation", ".txt", {"output_format": "text"}, volume_paths, model_name, chunks_db, chapter_name, rate_limiter, glossary_str=glossary_content, style_guide_str=style_guide_content, contexts=contexts)
                if not success:
                    system_logger.error("[Orchestrator] Этап перевода завершился с ошибками.")
                    return
            
            translation_checkpoint.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
            system_logger.info("[Orchestrator] Чекпоинт 'translation_complete' создан.")
            
            for chunk in db.get_chunks(chunks_db, chapter_name):
                if chunk['status'] == 'translation_done':
                    db.add_chunk(chunks_db, chapter_name, chunk['chunk_index'], content_source=chunk['content_source'], content_target=chunk['content_target'], status="reading_pending")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа перевода.")

        # --- Этап 3: Вычитка ---
        if not reading_checkpoint.exists():
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
                success = _run_workers_pooled(max_workers, pending_chunks, proofreading_prompt_template, "reading", ".txt", {"output_format": "text"}, volume_paths, model_name, chunks_db, chapter_name, rate_limiter, glossary_str=glossary_content, style_guide_str=style_guide_content, contexts=contexts)
                if not success:
                    system_logger.error("[Orchestrator] Этап вычитки завершился с ошибками.")
                    return

            reading_checkpoint.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
            system_logger.info("[Orchestrator] Чекпоинт 'reading_complete' создан.")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа вычитки.")

        # --- Этап 3.5: Глобальная вычитка ---
        if not global_reading_checkpoint.exists():
            system_logger.info("\n--- ЭТАП 3.5: Глобальная вычитка текста ---")
            
            all_chunks = db.get_chunks(chunks_db, chapter_name)
            
            with create_progress() as progress:
                task_id = progress.add_task("[cyan]Processing global proofreading...", total=1)
                updated_chunks = _run_global_proofreading(
                    all_chunks,
                    global_proofreading_prompt_template,
                    model_name,
                    rate_limiter,
                    progress,
                    task_id
                )
            
            for chunk in updated_chunks:
                db.add_chunk(chunks_db, chapter_name, chunk['chunk_index'], content_source=chunk['content_source'], content_target=chunk['content_target'], status="reading_done")

            global_reading_checkpoint.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
            system_logger.info("[Orchestrator] Чекпоинт 'global_reading_complete' создан.")
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
        
        # --- ЭТАП 4: ОПЦИОНАЛЬНАЯ КОНВЕРТАЦИЯ В DOCX ---
        auto_docx = os.environ.get('AUTO_CONVERT_DOCX')
        if auto_docx == '1' or (auto_docx is None and input("\nКонвертировать итоговый файл в .docx? (y/n): ").lower() == 'y'):
            try:
                docx_output_path = txt_output_path.with_suffix('.docx')
                convert_to_docx.convert_txt_to_docx(str(txt_output_path), str(docx_output_path))
            except ImportError:
                system_logger.error("\n--- ОШИБКА КОНВЕРТАЦИИ ---")
                system_logger.error("Библиотека 'python-docx' не найдена.")
                system_logger.error("Пожалуйста, установите ее командой: pip install -r requirements.txt")
            except Exception as e:
                system_logger.error(f"Произошла ошибка во время конвертации в .docx: {e}")

    except Exception as e:
        system_logger.critical(f"[Orchestrator] НЕПЕРЕХВАЧЕННАЯ КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True)
    finally:
        if lock_file.exists():
            lock_file.unlink()
            system_logger.info("[Orchestrator] Блокировка снята.")
        # Dirs are permanent in new architecture — no cleanup needed
        system_logger.info("\n[Orchestrator] Процесс завершен.")
