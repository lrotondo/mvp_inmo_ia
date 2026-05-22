from __future__ import annotations


def format_user_message(text: str) -> str:
    return f"Consulta del cliente: {text.strip()}"


def build_user_message_for_llm(
    current_user_text: str,
    *,
    prior_user_messages: list[str] | None = None,
    listing_followup: bool = False,
) -> str:
    """Arma el mensaje user para el LLM con contexto de listado e historial corto."""
    parts: list[str] = []
    if listing_followup:
        parts.append(
            "Contexto: el cliente ya recibió el listado de propiedades (opciones con fotos). "
            "Responde sobre esas opciones usando el bloque OPCIONES MOSTRADAS del system."
        )
    prior = [m.strip() for m in (prior_user_messages or []) if m.strip()]
    for index, msg in enumerate(prior, start=1):
        parts.append(f"Mensaje anterior {index} del cliente: {msg}")
    current = (current_user_text or "").strip()
    if current:
        parts.append(f"Consulta actual del cliente: {current}")
    return "\n\n".join(parts) if parts else ""


def build_model_messages(
    system_prompt: str,
    current_user_text: str,
    *,
    prior_user_messages: list[str] | None = None,
    listing_followup: bool = False,
) -> list[dict[str, str]]:
    """System + un mensaje user (historial corto opcional en el mismo user)."""
    user_content = build_user_message_for_llm(
        current_user_text,
        prior_user_messages=prior_user_messages,
        listing_followup=listing_followup,
    )
    if not user_content.strip():
        user_content = format_user_message(current_user_text)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


# Alias por compatibilidad
build_groq_messages = build_model_messages
