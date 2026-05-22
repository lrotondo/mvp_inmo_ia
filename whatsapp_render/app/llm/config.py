from __future__ import annotations

import os

LLM_CHAT_PROVIDER = os.environ.get("LLM_CHAT_PROVIDER", "deepseek").strip().lower()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()
