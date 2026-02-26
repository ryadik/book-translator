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

def _run_single_worker(task_path: str, prompt_template: str, step_paths: Dict[str, str], output_suffix: str, cli_args: Dict[str, Any], workspace_paths: Dict[str, Any], model_name: str, glossary_str: str, style_guide_str: str) -> bool:
    worker_id = uuid.uuid4().hex[:6]
    in_progress_path = None
    try:
        in_progress_path = task_manager.move_task(task_path, step_paths["in_progress"])
        
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=4, max=10),
            retry=retry_if_exception_type((subprocess.CalledProcessError, subprocess.TimeoutExpired)),
            reraise=True
        )
        def _do_run():
            with open(in_progress_path, 'r', encoding='utf-8') as f:
                chunk_content = f.read()

            final_prompt = prompt_template.replace('{text}', chunk_content).replace('{glossary}', glossary_str).replace('{style_guide}', style_guide_str)
            input_logger.info(f"[{worker_id}] --- PROMPT FOR: {os.path.basename(in_progress_path)} ---\n{final_prompt}\n")

            output_filename = os.path.basename(in_progress_path)
            
            if output_suffix == ".json":
                output_path = os.path.join(workspace_paths["terms"], f"{output_filename}{output_suffix}")
            else:
                output_path = os.path.join(step_paths["done"], output_filename)
            
            command = ['gemini', '-m', model_name, '-p', final_prompt, '--output-format', cli_args.get('output_format', 'text')]

            system_logger.info(f"[Orchestrator] Запущен воркер [id: {worker_id}] для: {os.path.basename(in_progress_path)}")

            try:
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', timeout=120, check=True)
                return result.stdout, output_path, output_filename
            except subprocess.CalledProcessError as e:
                system_logger.error(f"[Orchestrator] Воркер [id: {worker_id}] для {os.path.basename(in_progress_path)} завершился с ошибкой (код: {e.returncode}).")
                output_logger.error(f"[{worker_id}] --- FAILED OUTPUT FROM: {os.path.basename(in_progress_path)} ---\n{e.stderr.strip()}\n")
                raise
            except subprocess.TimeoutExpired as e:
                system_logger.error(f"[Orchestrator] Воркер [id: {worker_id}] превысил лимит времени (120с). Принудительное завершение.")
                raise

        stdout_output, output_path, output_filename = _do_run()
        
        system_logger.info(f"[Orchestrator] Воркер [id: {worker_id}] для {output_filename} успешно завершен.")
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f_out:
                f_out.write(stdout_output)
            output_logger.info(f"[{worker_id}] --- SUCCESSFUL OUTPUT FROM: {output_filename} ---\n{stdout_output}\n")
        except Exception as e:
            system_logger.error(f"[Orchestrator] Ошибка при записи вывода от воркера [id: {worker_id}]: {e}")

        if output_suffix == ".json":
            task_manager.move_task(in_progress_path, step_paths["done"])
        else:
            os.remove(in_progress_path)
            
        return True

    except Exception as e:
        system_logger.critical(f"[Orchestrator] КРИТИЧЕСКАЯ ОШИБКА при запуске воркера [id: {worker_id}] для {task_path}: {e}", exc_info=True)
        if in_progress_path and os.path.exists(in_progress_path):
            task_manager.move_task(in_progress_path, step_paths["failed"])
        return False

def _run_workers_pooled(max_workers: int, tasks: List[str], prompt_template: str, step_paths: Dict[str, str], output_suffix: str, cli_args: Dict[str, Any], workspace_paths: Dict[str, Any], model_name: str, glossary_str = "", style_guide_str = ""):
    all_successful = True
    total_tasks = len(tasks)
    completed_tasks_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_single_worker,
                task_path,
                prompt_template,
                step_paths,
                output_suffix,
                cli_args,
                workspace_paths,
                model_name,
                glossary_str,
                style_guide_str
            ): task_path for task_path in tasks
        }

        for future in concurrent.futures.as_completed(futures):
            task_path = futures[future]
            try:
                success = future.result()
                if success:
                    completed_tasks_count += 1
                    system_logger.info(f"[Orchestrator] Прогресс: ({completed_tasks_count}/{total_tasks})")
                else:
                    all_successful = False
            except Exception as e:
                system_logger.critical(f"[Orchestrator] Неожиданная ошибка при обработке {task_path}: {e}", exc_info=True)
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

    try:
        with open(lock_file, 'w') as f: f.write(str(os.getpid()))
        system_logger.info(f"[Orchestrator] Рабочая директория для главы '{chapter_name}' создана и заблокирована.")

        if resume:
            task_manager.requeue_stalled_and_failed(workspace_paths["steps"])

        # --- Этап 0: Разделение на чанки ---
        discovery_paths = workspace_paths["steps"]["discovery"]
        if not task_manager.get_pending_tasks(discovery_paths) and not resume:
            system_logger.info("[Orchestrator] Разделение главы на чанки...")
            chapter_splitter.split_chapter_intelligently(chapter_file_path, discovery_paths["pending"], cfg['chapter_splitter']['target_chunk_size'], cfg['chapter_splitter']['max_part_chars'])
        
        # --- Этап 1: Поиск терминов ---
        if not os.path.exists(discovery_checkpoint):
            system_logger.info("\n--- ЭТАП 1: Поиск новых терминов ---")
            glossary_content = "{}"
            try:
                with open("data/glossary.json", 'r', encoding='utf-8') as f: glossary_content = f.read() or "{}"
            except FileNotFoundError:
                system_logger.warning("Файл 'data/glossary.json' не найден.")
                if input("Продолжить с пустым глоссарием? (y/n): ").lower() == 'y':
                    with open("data/glossary.json", 'w', encoding='utf-8') as f: f.write(glossary_content)
                else: system_logger.info("Операция прервана пользователем."); return

            with open("prompts/term_discovery.txt", 'r', encoding='utf-8') as f: term_prompt_template = f.read()
            
            pending_tasks = task_manager.get_pending_tasks(discovery_paths)
            if pending_tasks:
                success = _run_workers_pooled(max_workers, pending_tasks, term_prompt_template, discovery_paths, ".json", {"output_format": "json"}, workspace_paths, model_name=cfg.get('gemini_cli', {}).get('model', 'gemini-2.5-pro'), glossary_str=glossary_content)
                if not success: system_logger.error("[Orchestrator] Этап поиска терминов завершился с ошибками."); return

            system_logger.info("\n--- Сбор и подтверждение терминов ---")
            new_terms = term_collector.collect_and_deduplicate_terms(workspace_paths)
            approved_terms = term_collector.present_for_confirmation(new_terms)
            if approved_terms is None: system_logger.info("[Orchestrator] Пользователь отменил операцию."); return
            if approved_terms: term_collector.update_glossary_file(approved_terms, "data/glossary.json")
            
            with open(discovery_checkpoint, 'w') as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
            system_logger.info("[Orchestrator] Чекпоинт 'discovery_complete' создан.")
            task_manager.copy_tasks_to_next_step(discovery_paths["done"], workspace_paths["steps"]["translation"]["pending"])
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа поиска терминов.")
        
        # --- Этап 2: Перевод ---
        translation_paths = workspace_paths["steps"]["translation"]
        if not os.path.exists(translation_checkpoint):
            system_logger.info("\n--- ЭТАП 2: Перевод чанков ---")
            try:
                with open("prompts/translation.txt", 'r', encoding='utf-8') as f: translation_prompt_template = f.read()
                with open("data/glossary.json", 'r', encoding='utf-8') as f: glossary_content = f.read()
                with open("data/style_guide.md", 'r', encoding='utf-8') as f: style_guide_content = f.read()
            except FileNotFoundError as e:
                system_logger.error(f"[Orchestrator] Не найден обязательный файл: {e}"); return
            
            pending_tasks = task_manager.get_pending_tasks(translation_paths)
            if pending_tasks:
                success = _run_workers_pooled(max_workers, pending_tasks, translation_prompt_template, translation_paths, ".txt", {"output_format": "text"}, workspace_paths, model_name=cfg.get('gemini_cli', {}).get('model', 'gemini-2.5-pro'), glossary_str=glossary_content, style_guide_str=style_guide_content)
                if not success: system_logger.error("[Orchestrator] Этап перевода завершился с ошибками."); return
            
            with open(translation_checkpoint, 'w') as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
            system_logger.info("[Orchestrator] Чекпоинт 'translation_complete' создан.")
            task_manager.copy_tasks_to_next_step(translation_paths["done"], workspace_paths["steps"]["reading"]["pending"])
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа перевода.")

        # --- Этап 3: Вычитка ---
        reading_paths = workspace_paths["steps"]["reading"]
        if not os.path.exists(reading_checkpoint):
            system_logger.info("\n--- ЭТАП 3: Вычитка текста ---")
            try:
                with open("prompts/proofreading.txt", 'r', encoding='utf-8') as f: proofreading_prompt_template = f.read()
                with open("data/glossary.json", 'r', encoding='utf-8') as f: glossary_content = f.read()
                with open("data/style_guide.md", 'r', encoding='utf-8') as f: style_guide_content = f.read()
            except FileNotFoundError as e:
                system_logger.error(f"[Orchestrator] Не найден обязательный файл: {e}"); return
            
            pending_tasks = task_manager.get_pending_tasks(reading_paths)
            if pending_tasks:
                success = _run_workers_pooled(max_workers, pending_tasks, proofreading_prompt_template, reading_paths, ".txt", {"output_format": "text"}, workspace_paths, model_name=cfg.get('gemini_cli', {}).get('model', 'gemini-2.5-pro'), glossary_str=glossary_content, style_guide_str=style_guide_content)
                if not success: system_logger.error("[Orchestrator] Этап вычитки завершился с ошибками."); return

            with open(reading_checkpoint, 'w') as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
            system_logger.info("[Orchestrator] Чекпоинт 'reading_complete' создан.")
        else:
            system_logger.info("\n[Orchestrator] Обнаружен чекпоинт. Пропуск этапа вычитки.")

        # --- ФИНАЛЬНАЯ СБОРКА ---
        system_logger.info("\n--- Сборка итогового файла ---")
        final_chunks_dir = workspace_paths["steps"]["reading"]["done"]
        final_chunks = [os.path.join(final_chunks_dir, f) for f in sorted(os.listdir(final_chunks_dir))]
        final_chunks.sort(key=lambda f: int(re.search(r'chunk_(\d+).txt', os.path.basename(f)).group(1)))
        
        input_dir = os.path.dirname(chapter_file_path)
        txt_output_path = os.path.join(input_dir, "ru.txt")
        
        with open(txt_output_path, 'w', encoding='utf-8') as final_file:
            for i, chunk_path in enumerate(final_chunks):
                with open(chunk_path, 'r', encoding='utf-8') as chunk_file:
                    final_file.write(chunk_file.read())
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