import logging
import sys
import os
import json
from datetime import datetime
from rich.logging import RichHandler
from book_translator.tui import console

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage()
        }
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)

system_logger = logging.getLogger('system')
input_logger = logging.getLogger('worker_input')
output_logger = logging.getLogger('worker_output')

default_formatter = JsonFormatter()
default_handler = logging.StreamHandler(sys.stdout)
default_handler.setFormatter(default_formatter)
system_logger.addHandler(default_handler)
system_logger.setLevel(logging.INFO)
system_logger.propagate = False

for logger_instance in [input_logger, output_logger]:
    logger_instance.addHandler(logging.NullHandler())
    logger_instance.propagate = False

def setup_loggers(log_dir: str, debug_mode: bool):
    for logger_instance in [system_logger, input_logger, output_logger]:
        if logger_instance.hasHandlers():
            logger_instance.handlers.clear()

    system_logger.setLevel(logging.DEBUG)
    input_logger.setLevel(logging.DEBUG)
    output_logger.setLevel(logging.DEBUG)

    json_formatter = JsonFormatter()

    console_handler = RichHandler(console=console, rich_tracebacks=True, markup=True)
    console_handler.setLevel(logging.INFO)
    # console_handler.setFormatter(json_formatter)  # RichHandler has its own formatting
    system_logger.addHandler(console_handler)

    if not debug_mode:
        input_logger.addHandler(logging.NullHandler())
        output_logger.addHandler(logging.NullHandler())
        return

    os.makedirs(log_dir, exist_ok=True)

    system_log_path = os.path.join(log_dir, 'system_output.log')
    system_file_handler = logging.FileHandler(system_log_path, mode='w', encoding='utf-8')
    system_file_handler.setLevel(logging.DEBUG)
    system_file_handler.setFormatter(json_formatter)
    system_logger.addHandler(system_file_handler)

    input_log_path = os.path.join(log_dir, 'workers_input.log')
    input_file_handler = logging.FileHandler(input_log_path, mode='w', encoding='utf-8')
    input_file_handler.setLevel(logging.DEBUG)
    input_file_handler.setFormatter(json_formatter)
    input_logger.addHandler(input_file_handler)

    output_log_path = os.path.join(log_dir, 'workers_output.log')
    output_file_handler = logging.FileHandler(output_log_path, mode='w', encoding='utf-8')
    output_file_handler.setLevel(logging.DEBUG)
    output_file_handler.setFormatter(json_formatter)
    output_logger.addHandler(output_file_handler)

    system_logger.debug("Логгеры успешно настроены в debug-режиме.")
