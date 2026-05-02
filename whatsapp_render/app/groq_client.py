from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx


async def chat_completion(messages: List[Dict[str, str]]) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY no configurada")

    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload: Dict[str, Any] = {
        "model": model,
        "temperature": 0.3,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        return "No pude generar una respuesta en este momento."
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip() or "No pude generar una respuesta."
