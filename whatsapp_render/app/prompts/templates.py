from __future__ import annotations

import os

CLOSING_CAPTACION_TEXT = (
    "Muchas gracias por la información. Ya registré los datos de tu propiedad. "
    "Un asesor especialista de nuestro equipo se va a comunicar con vos a la brevedad "
    "para coordinar los pasos a seguir y realizar la tasación."
)

VISIT_HANDOFF_TEMPLATE = (
    "¡Perfecto! Registré tu interés{property_part}.\n\n"
    "Un asesor de nuestro equipo se va a comunicar con vos por WhatsApp a la brevedad "
    "para coordinar la visita según la disponibilidad real.\n\n"
    "Si tenés alguna preferencia general (mañana, tarde o fin de semana), contanos; "
    "el asesor lo tendrá en cuenta al contactarte."
)

_FLOW_LABELS: dict[str, str] = {
    "nuevo": "inicio de conversación",
    "compra": "compra",
    "alquiler": "alquiler",
    "captacion": "captación de propiedad para vender",
}

_DEFAULT_MINIMAL_SYSTEM_PROMPT = """Sos el asistente de WhatsApp de {tenant_name} (inmobiliaria).
Rama actual: {flow_label}.

Reglas:
- Respuestas breves (2-4 líneas), tono amable y profesional.
- No inventes propiedades, precios, direcciones ni barrios.
- Prohibido usar [LISTADO:ids] o listar opciones en viñetas; el sistema envía fotos por separado.
- Si hay un bloque "OPCIONES MOSTRADAS", respondé solo con esos datos (Opción 1, 2, 3).
- No propongas fechas ni horarios exactos de visita; un asesor coordina después.
- En captación, pedí tipo de inmueble, ubicación y ambientes/metros si faltan."""


def format_visit_handoff(property_ref: str) -> str:
    prop = (property_ref or "").strip()
    part = f" en *{prop}*" if prop else ""
    return VISIT_HANDOFF_TEMPLATE.format(property_part=part)


def build_triage_message(tenant_name: str) -> str:
    name = (tenant_name or "").strip() or "la inmobiliaria"
    return (
        f"Hola, soy el asistente de *{name}*. "
        "¿Querés *comprar*, *alquilar* o *vender* una propiedad?"
    )


def _minimal_prompt_template() -> str:
    return os.environ.get("MINIMAL_SYSTEM_PROMPT", "").strip() or _DEFAULT_MINIMAL_SYSTEM_PROMPT


def build_chat_system_prompt(
    *,
    tenant_name: str,
    flow_path: str,
    catalog_block: str = "",
    system_prompt_override: str | None = None,
) -> str:
    """Un único system prompt corto para triage/captación/general."""
    name = (tenant_name or "").strip() or "la inmobiliaria"
    path = (flow_path or "nuevo").strip().lower()
    flow_label = _FLOW_LABELS.get(path, path)

    if (system_prompt_override or "").strip():
        base = system_prompt_override.strip()
    else:
        base = _minimal_prompt_template().format(
            tenant_name=name,
            flow_label=flow_label,
        )

    parts = [base]
    block = (catalog_block or "").strip()
    if block:
        parts.append(
            "\n### OPCIONES MOSTRADAS (solo para responder preguntas)\n"
            "No reenvíes el listado. Usá solo estos datos:\n"
            f"{block}"
        )
    return "\n\n".join(parts)
