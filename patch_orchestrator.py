import re

with open('orchestrator.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add imports
imports_to_add = """import concurrent.futures
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
"""
content = content.replace('import uuid\n', 'import uuid\n' + imports_to_add)

# Replace _run_workers_pooled
new_funcs = """def _run_single_worker(task_path: str, prompt_template: str, step_paths: Dict[str, str], output_suffix: str, cli_args: Dict[str, Any], workspace_paths: Dict[str, Any], model_name: str, glossary_str: str, style_guide_str: str) -> bool:
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
            input_logger.info(f"[{worker_id}] --- PROMPT FOR: {os.path.basename(in_progress_path)} ---\n{final_prompt}\\n")

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
                output_logger.error(f"[{worker_id}] --- FAILED OUTPUT FROM: {os.path.basename(in_progress_path)} ---\n{e.stderr.strip()}\\n")
                raise
            except subprocess.TimeoutExpired as e:
                system_logger.error(f"[Orchestrator] Воркер [id: {worker_id}] превысил лимит времени (120с). Принудительное завершение.")
                raise

        stdout_output, output_path, output_filename = _do_run()
        
        system_logger.info(f"[Orchestrator] Воркер [id: {worker_id}] для {output_filename} успешно завершен.")
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f_out:
                f_out.write(stdout_output)
            output_logger.info(f"[{worker_id}] --- SUCCESSFUL OUTPUT FROM: {output_filename} ---\n{stdout_output}\\n")
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
"""

# Find the start and end of _run_workers_pooled
start_idx = content.find('def _run_workers_pooled')
end_idx = content.find('def run_translation_process')

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + new_funcs + '\n' + content[end_idx:]
    with open('orchestrator.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully patched orchestrator.py")
else:
    print("Could not find _run_workers_pooled or run_translation_process")
