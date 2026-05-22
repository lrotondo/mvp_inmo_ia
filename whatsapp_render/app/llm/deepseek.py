from __future__ import annotations

import logging
from typing import Any

import httpx

from app.llm.config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)

_CHAT_URL = "https://api.deepseek.com/v1/chat/completions"


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str:
    api_key = DEEPSEEK_API_KEY
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY no configurada")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": DEEPSEEK_MODEL,
        "temperature": 0.2 if temperature is None else temperature,
        "messages": messages,
        "stream": False,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            response = await client.post(_CHAT_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error("Error DeepSeek: %s", e.response.text)
            return (
                "Disculpame, tuve un problema al consultar el catálogo. "
                "¿Me podrás repetir la pregunta?"
            )

    choices = data.get("choices") or []
    if not choices:
        return "No pude generar una respuesta en este momento."
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


async def chat_short(system: str, user: str) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return await chat_completion(messages, max_tokens=256, temperature=0.2)
