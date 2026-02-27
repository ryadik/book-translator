with open('orchestrator.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('input_logger.info(f"[{worker_id}] --- PROMPT FOR: {os.path.basename(in_progress_path)} ---\n{final_prompt}\\n")', 'input_logger.info(f"[{worker_id}] --- PROMPT FOR: {os.path.basename(in_progress_path)} ---\\n{final_prompt}\\n")')
content = content.replace('output_logger.error(f"[{worker_id}] --- FAILED OUTPUT FROM: {os.path.basename(in_progress_path)} ---\n{e.stderr.strip()}\\n")', 'output_logger.error(f"[{worker_id}] --- FAILED OUTPUT FROM: {os.path.basename(in_progress_path)} ---\\n{e.stderr.strip()}\\n")')
content = content.replace('output_logger.info(f"[{worker_id}] --- SUCCESSFUL OUTPUT FROM: {output_filename} ---\n{stdout_output}\\n")', 'output_logger.info(f"[{worker_id}] --- SUCCESSFUL OUTPUT FROM: {output_filename} ---\\n{stdout_output}\\n")')

with open('orchestrator.py', 'w', encoding='utf-8') as f:
    f.write(content)
