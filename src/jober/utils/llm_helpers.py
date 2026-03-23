"""Helpers para limpiar respuestas de LLMs."""

from __future__ import annotations

import re


def strip_markdown_fences(text: str) -> str:
    """Elimina code fences (```json ... ```) de la respuesta del LLM."""
    text = text.strip()
    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text
