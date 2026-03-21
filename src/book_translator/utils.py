"""
Вспомогательные утилиты для book-translator.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import json_repair


def strip_code_fence(text: str) -> str:
    """Снимает markdown code fence с текста (```json ... ``` или ``` ... ```).

    Args:
        text: Сырой текст, возможно обёрнутый в code fence.

    Returns:
        Текст без code fence, обрезанный по пробелам.
    """
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
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
    if isinstance(parsed, dict) and "response" in parsed and len(parsed) <= 3:
        response_text = parsed["response"]
        if isinstance(response_text, str):
            inner_text = strip_code_fence(response_text)
            try:
                return json.loads(inner_text)
            except json.JSONDecodeError:
                try:
                    repaired = json_repair.repair_json(inner_text)
                    return json.loads(repaired)
                except Exception:
                    pass  # Возвращаем внешний parsed ниже

    return parsed


def find_tool_versions_dir() -> Path | None:
    """Walk up from this file to find a directory containing .tool-versions (for asdf)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / '.tool-versions').exists():
            return parent
    return None
