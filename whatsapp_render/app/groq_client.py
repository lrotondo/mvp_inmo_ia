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
        "temperature": 0.2, # Un poco más bajo para ser más determinista
        "max_tokens": 600,
        "top_p": 0.9,
        "messages": messages,
        "stream": False # Aseguramos que sea síncrono para tu flujo actual
    }

    async with httpx.AsyncClient(timeout=45.0) as client: # 45s es suficiente
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Error de Groq: {e.response.text}")
            return "Lo siento, tuve un problema técnico. ¿Podrías repetir tu consulta?"