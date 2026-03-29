"""
Вспомогательные утилиты для book-translator.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import json_repair

_logger = logging.getLogger('system')

# Matches any opening code fence: ```json, ```text, ```python, ``` etc.
_CODE_FENCE_OPEN = re.compile(r'^```\w*\s*\n?', re.MULTILINE)
_CODE_FENCE_CLOSE = re.compile(r'\n?```\s*$', re.MULTILINE)


def strip_code_fence(text: str) -> str:
    """Снимает markdown code fence с текста любого вида (```json, ```text, ``` и т.д.).

    Args:
        text: Сырой текст, возможно обёрнутый в code fence.

    Returns:
        Текст без code fence, обрезанный по пробелам.
    """
    text = text.strip()
    text = _CODE_FENCE_OPEN.sub('', text, count=1)
    text = _CODE_FENCE_CLOSE.sub('', text, count=1)
    return text.strip()


def parse_llm_json(raw: str) -> Any:
    """Парсит JSON из сырого ответа gemini-cli.

    Обрабатывает следующие форматы:
    1. Чистый JSON
    2. JSON в markdown code fence: ```json ... ```
    3. Обёртку gemini-cli: {"response": "..."}
    4. Слегка повреждённый JSON (через json_repair)

    Args:
        raw: Сырая строка из stdout gemini-cli.

    Returns:
        Распарсенный Python-объект (dict, list и т.д.).

    Raises:
        ValueError: Если не удалось извлечь валидный JSON.
    """
    text = strip_code_fence(raw)

    # Парсим первый уровень
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Пробуем json_repair для слегка повреждённых ответов
        try:
            repaired = json_repair.repair_json(text)
            parsed = json.loads(repaired)
        except (json.JSONDecodeError, Exception) as e:
            raise ValueError(f"Не удалось распарсить JSON из ответа LLM: {e}\nОтвет: {raw[:200]!r}")

    # Обработка обёртки gemini-cli: {"response": "..."}
    if isinstance(parsed, dict) and "response" in parsed and isinstance(parsed.get("response"), str):
        response_text = parsed["response"]
        if isinstance(response_text, str):
            if not response_text.strip():
                raise ValueError("Gemini-cli вернул пустой response в обёртке")
            inner_text = strip_code_fence(response_text)
            try:
                return json.loads(inner_text)
            except json.JSONDecodeError:
                try:
                    repaired = json_repair.repair_json(inner_text)
                    return json.loads(repaired)
                except Exception as e:
                    _logger.warning(
                        f"[parse_llm_json] Не удалось распарсить inner JSON из обёртки gemini-cli: {e}. "
                        f"Содержимое response (первые 300 символов): {response_text[:300]!r}"
                    )
                    raise ValueError(
                        f"Не удалось распарсить inner JSON из обёртки gemini-cli: {e}\n"
                        f"Response: {response_text[:200]!r}"
                    )

    return parsed


def find_tool_versions_dir() -> Path | None:
    """Walk up from this file to find a directory containing .tool-versions (for asdf)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / '.tool-versions').exists():
            return parent
    return None
