from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


async def chat_completion(
    messages: List[Dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY no configurada")

    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload: Dict[str, Any] = {
        "model": model,
        "temperature": 0.2 if temperature is None else temperature,
        "max_tokens": 600 if max_tokens is None else max_tokens,
        "top_p": 0.9,
        "messages": messages,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("Error de Groq: %s", e.response.text)
            return "Lo siento, tuve un problema técnico. ¿Podrías repetir tu consulta?"

        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        return "No pude generar una respuesta en este momento."

    message = choices[0].get("message") or {}
    content = str(message.get("content") or "").strip()
    return content or "No pude generar una respuesta en este momento."
