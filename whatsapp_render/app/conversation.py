from __future__ import annotations


def format_user_message(text: str) -> str:
    return f"Consulta del cliente: {text.strip()}"


def build_model_messages(
    system_prompt: str,
    current_user_text: str,
) -> list[dict[str, str]]:
    """Un solo turno de usuario; sin historial persistido."""
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": format_user_message(current_user_text),
        },
    ]


# Alias por compatibilidad
build_groq_messages = build_model_messages
