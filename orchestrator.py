import os
import subprocess
import time
import json
import re
import shutil
import sys
import uuid
import concurrent.futures
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Dict, Any, List

from logger import setup_loggers, system_logger, input_logger, output_logger
import config
import chapter_splitter
import task_manager
import term_collector
import convert_to_docx
import db
from rate_limiter import RateLimiter

def _run_single_worker(
    chunk: Dict[str, Any],
    prompt_template: str,
    step_name: str,
    output_suffix: str,
    cli_args: Dict[str, Any],
    workspace_paths: Dict[str, Any],
    model_name: str,
    glossary_str: str,
    style_guide_str: str,
    db_path: str,
    project_id: str,
    rate_limiter: RateLimiter,
    previous_context: str = ""
) -> bool:
    worker_id = uuid.uuid4().hex[:6]
    chunk_index = chunk['chunk_index']
    
    try:
        db.add_chunk(db_path, project_id, chunk_index, chunk['content_jp'], chunk['content_ru'], f"{step_name}_in_progress")
        
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=4, max=10),
            retry=retry_if_exception_type((subprocess.CalledProcessError, subprocess.TimeoutExpired)),
            reraise=True
        )
        def _do_run():
            chunk_content = chunk['content_ru'] if step_name == "reading" else chunk['content_jp']
            final_prompt = prompt_template.replace('{text}', chunk_content).replace('{glossary}', glossary_str).replace('{style_guide}', style_guide_str).replace('{previous_context}', previous_context)
            
            input_logger.info(f"[{worker_id}] --- PROMPT FOR: chunk_{chunk_index} ---\n{final_prompt}\n")

            output_filename = f"chunk_{chunk_index}.txt"
            
            if output_suffix == ".json":
                output_path = os.path.join(workspace_paths["terms"], f"chunk_{chunk_index}{output_suffix}")
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
                with open(output_path, 'w', encoding='utf-8') as f_out:
                    f_out.write(stdout_output)
            except Exception as e:
                system_logger.error(f"[Orchestrator] Ошибка при записи вывода от воркера [id: {worker_id}]: {e}")

        output_logger.info(f"[{worker_id}] --- SUCCESSFUL OUTPUT FROM: {output_filename} ---\n{stdout_output}\n")

        if step_name == "discovery":
            db.add_chunk(db_path, project_id, chunk_index, chunk['content_jp'], chunk['content_ru'], "discovery_done")
        elif step_name == "translation":
            db.add_chunk(db_path, project_id, chunk_index, chunk['content_jp'], stdout_output, "translation_done")
        elif step_name == "reading":
            db.add_chunk(db_path, project_id, chunk_index, chunk['content_jp'], stdout_output, "reading_done")
            
        return True

    except Exception as e:
        system_logger.critical(f"[Orchestrator] КРИТИЧЕСКАЯ ОШИБКА при запуске воркера [id: {worker_id}] для chunk_{chunk_index}: {e}", exc_info=True)
        db.add_chunk(db_path, project_id, chunk_index, chunk['content_jp'], chunk['content_ru'], f"{step_name}_failed")
        return False

def _run_workers_pooled(
    max_workers: int,
    chunks: List[Dict[str, Any]],
    prompt_template: str,
    step_name: str,
    output_suffix: str,
    cli_args: Dict[str, Any],
    workspace_paths: Dict[str, Any],
    model_name: str,
    db_path: str,
    project_id: str,
    rate_limiter: RateLimiter,
    glossary_str = "",
    style_guide_str = "",
    contexts: Dict[int, str] = None
):
    all_successful = True
    total_tasks = len(chunks)
    completed_tasks_count = 0
    contexts = contexts or {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_single_worker,
                chunk,
                prompt_template,
                step_name,
                output_suffix,
                cli_args,
                workspace_paths,
                model_name,
                glossary_str,
                style_guide_str,
                db_path,
                project_id,
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
                    system_logger.info(f"[Orchestrator] Прогресс: ({completed_tasks_count}/{total_tasks})")
                else:
                    all_successful = False
            except Exception as e:
                system_logger.critical(f"[Orchestrator] Неожиданная ошибка при обработке chunk_{chunk['chunk_index']}: {e}", exc_info=True)
                all_successful = False

    return all_successful

def run_translation_process(chapter_file_path: str, cleanup: bool, resume: bool, force_split: bool):
    debug_mode = not cleanup
    try:
        cfg = config.load_config()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить config.json. {e}")
        return

    max_workers = cfg.get("max_concurrent_workers", 3)
    chapter_name = os.path.basename(os.path.dirname(chapter_file_path))
    workspace_paths = task_manager.setup_task_workspace(cfg['workspace_dir'], chapter_name)
    
    setup_loggers(workspace_paths["logs"], debug_mode)
    system_logger.info("--- Запуск нового процесса перевода ---")
    
    db_path = os.path.join(workspace_paths["base"], "state.db")
    db.init_db(db_path)
    rate_limiter = RateLimiter(2.0)
    
    lock_file = os.path.join(workspace_paths["base"], ".lock")
    discovery_checkpoint = os.path.join(workspace_paths["base"], ".stage_discovery_complete")
    translation_checkpoint = os.path.join(workspace_paths["base"], ".stage_translation_complete")
    reading_checkpoint = os.path.join(workspace_paths["base"], ".stage_reading_complete")

    if os.path.exists(lock_file) and not resume:
        system_logger.warning(f"[Orchestrator] ОБНАРУЖЕНА БЛОКИРОВКА для главы '{chapter_name}'. Используйте `--resume` или `--force-split`.")
        sys.exit(1)

    if force_split and os.path.exists(workspace_paths["base"]):
        system_logger.info("[Orchestrator] Обнаружен флаг `--force-split`. Полная очистка рабочей директории...")
        task_manager.cleanup_workspace(workspace_paths)
        workspace_paths = task_manager.setup_task_workspace(cfg['workspace_dir'], chapter_name)
        setup_loggers(workspace_paths["logs"], debug_mode)
        db.init_db(db_path)

    try:
        with open(lock_file, 'w') as f: f.write(str(os.getpid()))
        system_logger.info(f"[Orchestrator] Рабочая директория для главы '{chapter_name}' создана и заблокирована.")

        if resume:
            # Reset stalled tasks
            chunks = db.get_chunks(db_path, chapter_name)
            for chunk in chunks:
                if chunk['status'].endswith('_in_progress') or chunk['status'].endswith('_failed'):
                    new_status = chunk['status'].replace('_in_progress', '_pending').replace('_failed', '_pending')
                    db.add_chunk(db_path, chapter_name, chunk['chunk_index'], chunk['content_jp'], chunk['content_ru'], new_status)

        # --- Этап 0: Разделение на чанки ---
        chunks = db.get_chunks(db_path, chapter_name)
        if not chunks and not resume:
            system_logger.info("[Orchestrator] Разделение главы на чанки...")
            temp_split_dir = os.path.join(workspace_paths["base"], "temp_split")
            chunks_data = chapter_splitter.split_chapter_intelligently(chapter_file_path, temp_split_dir, cfg['chapter_splitter']['target_chunk_size'], cfg['chapter_splitter']['max_part_chars'])
            for chunk_data in chunks_data:
                db.add_chunk(db_path, chapter_name, chunk_data['id'], chunk_data['text'], status="discovery_pending")
            chunks = db.get_chunks(db_path, chapter_name)
        
        # --- Этап 1: Поиск терминов ---
        if not os.path.exists(discovery_checkpoint):
            system_logger.info("\n--- ЭТАП 1: Поиск новых терминов ---")
            terms = db.get_terms(db_path, chapter_name)
            glossary_content = json.dumps(terms, ensure_ascii=False, indent=2)

            with open("prompts/term_discovery.txt", 'r', encoding='utf-8') as f: term_prompt_template = f.read()
            
            pending_chunks = [c for c in db.get_chunks(db_path, chapter_name) if c['status'] == 'discovery_pending']
            if pending_chunks:
                success = _run_workers_pooled(max_workers, pending_chunks, term_prompt_template, "discovery", ".json", {"output_format": "json"}, workspace_paths, cfg.get('gemini_cli', {}).get('model', 'gemini-2.5-pro'), db_path, chapter_name, rate_limiter, glossary_str=glossary_content)
                if not success: system_logger.error("[Orchestrator] Этап поиска терминов завершился с ошибками."); return

            system_logger.info("\n--- Сбор и подтверждение терминов ---")
            new_terms = term_collector.collect_and_deduplicate_terms(workspace_paths)
            approved_terms = term_collector.present_for_confirmation(new_terms)
            if approved_terms is None: system_logger.info("[Orchestrator] Пользователь отменил операцию."); return
            if approved_terms: term_collector.update_glossary_file(approved_terms, db_path, chapter_name)
            
            with open(discovery_checkpoint, 'w') as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
            system_logger.info("[Orchestrator] Чекпоинт 'discovery_complete' создан.")
            
            for chunk in db.get_chunks(db_path, chapter_name):
                if chunk['status'] == 'discovery_done':
                    db.add_chunk(db_path, chapter_name, chunk['chunk_index'], chunk['content_jp'], chunk['content_ru'], "translation_pending")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа поиска терминов.")
        
        # --- Этап 2: Перевод ---
        if not os.path.exists(translation_checkpoint):
            system_logger.info("\n--- ЭТАП 2: Перевод чанков ---")
            try:
                with open("prompts/translation.txt", 'r', encoding='utf-8') as f: translation_prompt_template = f.read()
                terms = db.get_terms(db_path, chapter_name)
                glossary_content = json.dumps(terms, ensure_ascii=False, indent=2)
                with open("data/style_guide.md", 'r', encoding='utf-8') as f: style_guide_content = f.read()
            except FileNotFoundError as e:
                system_logger.error(f"[Orchestrator] Не найден обязательный файл: {e}"); return
            
            all_chunks = db.get_chunks(db_path, chapter_name)
            pending_chunks = [c for c in all_chunks if c['status'] == 'translation_pending']
            
            contexts = {}
            for i, chunk in enumerate(all_chunks):
                if i > 0:
                    contexts[chunk['chunk_index']] = all_chunks[i-1]['content_jp']
            
            if pending_chunks:
                success = _run_workers_pooled(max_workers, pending_chunks, translation_prompt_template, "translation", ".txt", {"output_format": "text"}, workspace_paths, cfg.get('gemini_cli', {}).get('model', 'gemini-2.5-pro'), db_path, chapter_name, rate_limiter, glossary_str=glossary_content, style_guide_str=style_guide_content, contexts=contexts)
                if not success: system_logger.error("[Orchestrator] Этап перевода завершился с ошибками."); return
            
            with open(translation_checkpoint, 'w') as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
            system_logger.info("[Orchestrator] Чекпоинт 'translation_complete' создан.")
            
            for chunk in db.get_chunks(db_path, chapter_name):
                if chunk['status'] == 'translation_done':
                    db.add_chunk(db_path, chapter_name, chunk['chunk_index'], chunk['content_jp'], chunk['content_ru'], "reading_pending")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа перевода.")

        # --- Этап 3: Вычитка ---
        if not os.path.exists(reading_checkpoint):
            system_logger.info("\n--- ЭТАП 3: Вычитка текста ---")
            try:
                with open("prompts/proofreading.txt", 'r', encoding='utf-8') as f: proofreading_prompt_template = f.read()
                terms = db.get_terms(db_path, chapter_name)
                glossary_content = json.dumps(terms, ensure_ascii=False, indent=2)
                with open("data/style_guide.md", 'r', encoding='utf-8') as f: style_guide_content = f.read()
            except FileNotFoundError as e:
                system_logger.error(f"[Orchestrator] Не найден обязательный файл: {e}"); return
            
            all_chunks = db.get_chunks(db_path, chapter_name)
            pending_chunks = [c for c in all_chunks if c['status'] == 'reading_pending']
            
            contexts = {}
            for i, chunk in enumerate(all_chunks):
                if i > 0:
                    contexts[chunk['chunk_index']] = all_chunks[i-1]['content_ru'] or ""
            
            if pending_chunks:
                success = _run_workers_pooled(max_workers, pending_chunks, proofreading_prompt_template, "reading", ".txt", {"output_format": "text"}, workspace_paths, cfg.get('gemini_cli', {}).get('model', 'gemini-2.5-pro'), db_path, chapter_name, rate_limiter, glossary_str=glossary_content, style_guide_str=style_guide_content, contexts=contexts)
                if not success: system_logger.error("[Orchestrator] Этап вычитки завершился с ошибками."); return

            with open(reading_checkpoint, 'w') as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
            system_logger.info("[Orchestrator] Чекпоинт 'reading_complete' создан.")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа вычитки.")

        # --- ФИНАЛЬНАЯ СБОРКА ---
        system_logger.info("\n--- Сборка итогового файла ---")
        final_chunks = [c for c in db.get_chunks(db_path, chapter_name) if c['status'] == 'reading_done']
        final_chunks.sort(key=lambda c: c['chunk_index'])
        
        input_dir = os.path.dirname(chapter_file_path)
        txt_output_path = os.path.join(input_dir, "ru.txt")
        
        with open(txt_output_path, 'w', encoding='utf-8') as final_file:
            for i, chunk in enumerate(final_chunks):
                final_file.write(chunk['content_ru'])
                if i < len(final_chunks) - 1: final_file.write("\n\n")

        system_logger.info(f"✅ Глава успешно переведена и собрана в файл: {txt_output_path}")
        
        # --- ЭТАП 4: ОПЦИОНАЛЬНАЯ КОНВЕРТАЦИЯ В DOCX ---
        if input("\nКонвертировать итоговый файл в .docx? (y/n): ").lower() == 'y':
            try:
                docx_output_path = os.path.splitext(txt_output_path)[0] + ".docx"
                convert_to_docx.convert_txt_to_docx(txt_output_path, docx_output_path)
            except ImportError:
                system_logger.error("\n--- ОШИБКА КОНВЕРТАЦИИ ---")
                system_logger.error("Библиотека 'python-docx' не найдена.")
                system_logger.error("Пожалуйста, установите ее командой: pip install -r requirements.txt")
            except Exception as e:
                system_logger.error(f"Произошла ошибка во время конвертации в .docx: {e}")

    except Exception as e:
        system_logger.critical(f"[Orchestrator] НЕПЕРЕХВАЧЕННАЯ КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True)
    finally:
        if os.path.exists(lock_file):
            os.remove(lock_file)
            system_logger.info("[Orchestrator] Блокировка снята.")
        if not debug_mode:
            task_manager.cleanup_workspace(workspace_paths)
        else:
            system_logger.info("\n[Orchestrator] Процесс завершен. Рабочая директория сохранена для отладки.")
