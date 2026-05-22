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

_LISTING_FOLLOWUP_RULES = """Cuando exista el bloque "OPCIONES MOSTRADAS":
- El cliente pregunta sobre el listado que ya recibió (fotos por WhatsApp).
- Respondé con datos concretos citando "Opción 1", "Opción 2" o "Opción 3" según corresponda.
- Si preguntan por un atributo (patio, pileta, precio, metros, etc.), decilo por cada opción relevante según el bloque; no omitas el dato si está ahí.
- Si dicen "esa casa", "la primera", "la de Hudson", etc., usá los mensajes recientes del cliente y el bloque para inferir la opción; si queda ambiguo, respondé qué opción(es) cumplen y pedí solo el número de opción.
- No respondas solo con "¿te interesa alguna?" sin aportar información del bloque cuando la respuesta está en los datos."""

_DEFAULT_MINIMAL_SYSTEM_PROMPT = (
    """Sos el asistente de WhatsApp de {tenant_name} (inmobiliaria).
Rama actual: {flow_label}.

Reglas:
- Respuestas breves (2-4 líneas), tono amable y profesional.
- No inventes propiedades, precios, direcciones ni barrios.
- Prohibido usar [LISTADO:ids] o listar opciones en viñetas; el sistema envía fotos por separado.
- No propongas fechas ni horarios exactos de visita; un asesor coordina después.
- En captación, pedí tipo de inmueble, ubicación y ambientes/metros si faltan.

"""
    + _LISTING_FOLLOWUP_RULES
)


def format_visit_handoff(property_ref: str) -> str:
    prop = (property_ref or "").strip()
    part = f" en *{prop}*" if prop else ""
    return VISIT_HANDOFF_TEMPLATE.format(property_part=part)


_INTAKE_BUNDLE_ALQUILER = (
    "Para ayudarte mejor, contame en un solo mensaje:\n"
    "• ¿Preferís *casa* o *departamento*?\n"
    "• ¿Tenés *zona o barrio* preferido? (Si no, decime «sin preferencia de zona».)\n"
    "• ¿Cuántos *dormitorios* necesitás?"
)

_INTAKE_BUNDLE_COMPRA = (
    "Para ayudarte mejor, contame en un solo mensaje:\n"
    "• ¿Buscás *casa*, *departamento* o *lote*?\n"
    "• Si es casa o departamento: ¿*zona o barrio* preferido? (O «sin preferencia de zona».)\n"
    "• ¿Cuántos *dormitorios* como mínimo? (En lote, solo si te importa.)\n"
    "• ¿Tenés un *presupuesto máximo en USD*? (Si no, podés omitirlo.)"
)


def build_intake_bundle_question(flow_path: str) -> str:
    path = (flow_path or "").strip().lower()
    if path == "alquiler":
        return _INTAKE_BUNDLE_ALQUILER
    if path == "compra":
        return _INTAKE_BUNDLE_COMPRA
    return "Contame qué buscás y te ayudo."


_WAITLIST_BUNDLE_ALQUILER = (
    "Entiendo que ninguna de las opciones te cierra.\n\n"
    "Para agregarte a nuestra *lista de espera*, contame en *un solo mensaje*:\n"
    "• ¿Preferís *casa* o *departamento*?\n"
    "• ¿*Zona o barrio* preferido? (O «sin preferencia de zona».)\n"
    "• ¿Cuántos *dormitorios* necesitás?\n"
    "• ¿*Presupuesto mensual* aproximado en ARS? (Si no, podés omitirlo.)\n"
    "• *Mascotas*, garantía u otras preferencias importantes\n"
    "• Si querés, por qué no te sirvieron las opciones que viste (opcional)"
)

_WAITLIST_BUNDLE_COMPRA = (
    "Entiendo que ninguna de las opciones te cierra.\n\n"
    "Para agregarte a nuestra *lista de espera*, contame en *un solo mensaje*:\n"
    "• ¿Buscás *casa*, *departamento* o *lote*?\n"
    "• ¿*Zona o barrio* preferido? (O «sin preferencia de zona».)\n"
    "• ¿Cuántos *dormitorios* como mínimo?\n"
    "• ¿*Presupuesto máximo en USD*? (Si no, podés omitirlo.)\n"
    "• Preferencias (patio, cochera, metros, etc.)\n"
    "• Si querés, por qué no te sirvieron las opciones que viste (opcional)"
)


def build_waitlist_bundle_question(flow_path: str) -> str:
    path = (flow_path or "").strip().lower()
    if path == "alquiler":
        return _WAITLIST_BUNDLE_ALQUILER
    if path == "compra":
        return _WAITLIST_BUNDLE_COMPRA
    return (
        "Entiendo que ninguna opción te cierra. "
        "Contame en un solo mensaje todo lo que buscás para agregarte a la lista de espera."
    )


WAITLIST_CONFIRMATION_TEXT = (
    "¡Listo! Ya te registré en nuestra *lista de espera*.\n\n"
    "Un *asesor del equipo* se va a comunicar con vos por WhatsApp "
    "ni bien tengamos propiedades que cumplan con lo que necesitás."
)


def build_triage_message(tenant_name: str) -> str:
    name = (tenant_name or "").strip() or "la inmobiliaria"
    return (
        f"Hola, soy el asistente de *{name}*. "
        "¿Querés *comprar*, *alquilar* o *vender* una propiedad?"
    )


def _minimal_prompt_template() -> str:
    return os.environ.get("MINIMAL_SYSTEM_PROMPT", "").strip() or _DEFAULT_MINIMAL_SYSTEM_PROMPT


def _uses_custom_system_prompt(system_prompt_override: str | None) -> bool:
    if (system_prompt_override or "").strip():
        return True
    return bool(os.environ.get("MINIMAL_SYSTEM_PROMPT", "").strip())


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
        if "{tenant_name}" in base or "{flow_label}" in base:
            base = base.format(tenant_name=name, flow_label=flow_label)
    else:
        env_raw = os.environ.get("MINIMAL_SYSTEM_PROMPT", "").strip()
        if env_raw:
            base = (
                env_raw.format(tenant_name=name, flow_label=flow_label)
                if "{tenant_name}" in env_raw or "{flow_label}" in env_raw
                else env_raw
            )
        else:
            base = _DEFAULT_MINIMAL_SYSTEM_PROMPT.format(
                tenant_name=name,
                flow_label=flow_label,
            )

    parts = [base]
    block = (catalog_block or "").strip()
    if block:
        if _uses_custom_system_prompt(system_prompt_override):
            parts.append(_LISTING_FOLLOWUP_RULES)
        parts.append(
            "\n### OPCIONES MOSTRADAS (listado ya enviado al cliente)\n"
            "No reenvíes el listado ni repitas todas las fichas. "
            "Respondé la consulta usando solo estas opciones (citá Opción N):\n"
            f"{block}"
        )
    return "\n\n".join(parts)
