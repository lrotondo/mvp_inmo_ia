from __future__ import annotations

import os
import logging
from typing import Any, Dict, List
import httpx

logger = logging.getLogger(__name__)

async def chat_completion(messages: List[Dict[str, str]]) -> str:
    # 1. Buscamos la API Key de DeepSeek
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY no configurada en las variables de entorno")

    # 2. El endpoint oficial de DeepSeek que imita a OpenAI
    url = "https://api.deepseek.com/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload: Dict[str, Any] = {
        # Usamos deepseek-chat (que apunta internamente a DeepSeek-V3)
        "model": "deepseek-chat", 
        "temperature": 0.3, # Mantenemos la precisión para el catálogo de Tandil
        "messages": messages,
        "stream": False
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Error de DeepSeek API: {e.response.text}")
            return "Disculpame, tuve un problema al consultar el catálogo. ¿Me podrás repetir la pregunta? 🏠"

    choices = data.get("choices") or []
    if not choices:
        return "No pude generar una respuesta en este momento."
        
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()