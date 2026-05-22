from __future__ import annotations

import os

LLM_CHAT_PROVIDER = os.environ.get("LLM_CHAT_PROVIDER", "deepseek").strip().lower()
LLM_CLASSIFIER_PROVIDER = os.environ.get("LLM_CLASSIFIER_PROVIDER", "groq").strip().lower()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
