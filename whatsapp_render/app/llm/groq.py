from __future__ import annotations

import logging
from typing import Any

import httpx

from app.llm.config import GROQ_API_KEY, GROQ_MODEL

logger = logging.getLogger(__name__)


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str:
    api_key = GROQ_API_KEY
    if not api_key:
        raise RuntimeError("GROQ_API_KEY no configurada")

    model_name = (model or GROQ_MODEL).strip()
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload: dict[str, Any] = {
        "model": model_name,
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
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error("Error Groq: %s", e.response.text)
            return "Disculpame, tuve un problema técnico. ¿Podés repetir?"

    choices = data.get("choices") or []
    if not choices:
        return "No pude generar una respuesta."
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()
