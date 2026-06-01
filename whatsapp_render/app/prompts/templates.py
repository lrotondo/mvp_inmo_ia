from __future__ import annotations

import os
import re

CLOSING_CAPTACION_TEXT = (
    "Muchas gracias por la información. Ya registré los datos de tu propiedad. "
    "Un asesor especialista de nuestro equipo se va a comunicar con vos a la brevedad "
    "para coordinar los pasos a seguir y realizar la tasación."
)

VISIT_CONFIRMATION_TEXT = (
    "¡Perfecto! Registré tu interés{property_part}.\n\n"
    "Un asesor de nuestro equipo se va a comunicar con vos por WhatsApp a la brevedad "
    "para coordinar la visita según la disponibilidad real."
)

_VISIT_SCHEDULE_QUESTION_TEMPLATE = (
    "¡Genial! Para que un asesor te contacte y coordinen la visita{property_part}, "
    "contame en *un solo mensaje*:\n"
    "• ¿Qué *días* te vienen bien? (entre semana, fin de semana, o fechas puntuales)\n"
    "• ¿Preferís *mañana*, *tarde*, o no tenés preferencia de horario?\n"
    "Si preferís que te llamen sin definir horario, escribí *sin horario*."
)

# Compat: plantilla histórica (confirmación + pedido de horarios en un solo mensaje).
VISIT_HANDOFF_TEMPLATE = (
    VISIT_CONFIRMATION_TEXT
    + "\n\n"
    + "Si tenés alguna preferencia general (mañana, tarde o fin de semana), contanos; "
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
- Si el contexto indica una "Opción en foco", asumila para preguntas ambiguas (precio, patio, expensas) hasta que el cliente pida más opciones o nombre otra.
- Si existe "PROPIEDAD EN DETALLE (contexto activo)", el cliente ya vio esa ficha: respondé sobre esa propiedad sin reenviar otras fichas ni inventar otra dirección.
- No respondas solo con "¿te interesa alguna?" sin aportar información del bloque cuando la respuesta está en los datos."""

_DEFAULT_MINIMAL_SYSTEM_PROMPT = (
    """Sos el asistente de WhatsApp de {tenant_name} (inmobiliaria).
Rama actual: {flow_label}.

Reglas:
- Respuestas breves (2-4 líneas), tono amable y profesional.
- No inventes propiedades, precios, direcciones ni barrios.
- Prohibido usar [LISTADO:ids] o listar opciones en viñetas; el sistema envía fotos por separado.
- No propongas fechas ni horarios exactos de visita; un asesor coordina después.
- Si el cliente rechaza coordinar visita o pide más opciones, no confirmes interés ni digas que un asesor coordinará visita de esa propiedad.
- En captación, pedí tipo de inmueble, ubicación y ambientes/metros si faltan.

"""
    + _LISTING_FOLLOWUP_RULES
)


def _visit_property_part(property_ref: str) -> str:
    prop = (property_ref or "").strip()
    return f" de *{prop}*" if prop else ""


def build_visit_schedule_question(property_ref: str = "") -> str:
    return _VISIT_SCHEDULE_QUESTION_TEMPLATE.format(
        property_part=_visit_property_part(property_ref),
    )


def build_visit_declined_reply() -> str:
    return (
        "Sin problema. Si querés, seguimos buscando o contame en qué más te puedo ayudar."
    )


def build_visit_cancelled_more_options_reply() -> str:
    return "Entendido, te muestro más opciones."


def format_visit_confirmation(property_ref: str = "") -> str:
    return VISIT_CONFIRMATION_TEXT.format(
        property_part=_visit_property_part(property_ref),
    )


_VISIT_CONFIRMATION_MARKER_RE = re.compile(
    r"Registr[eé]\s+tu\s+inter[eé]s",
    re.I,
)


def is_visit_confirmation_message(text: str) -> bool:
    """True si el outbound es la confirmación de visita (sin ficha)."""
    return bool(_VISIT_CONFIRMATION_MARKER_RE.search(text or ""))


def format_visit_handoff(property_ref: str) -> str:
    """Compat tests: confirmación + pedido de horarios en un mensaje."""
    prop = (property_ref or "").strip()
    part = f" en *{prop}*" if prop else ""
    return VISIT_HANDOFF_TEMPLATE.format(property_part=part)


_INTAKE_BUNDLE_ALQUILER = (
    "Para ayudarte mejor, contame en un solo mensaje:\n"
    "• ¿Preferís *casa* o *departamento*?\n"
    "• ¿Tenés *zona o barrio* preferido?\n"
    "• ¿Cuántos *dormitorios* necesitás?"
)

_INTAKE_BUNDLE_COMPRA = (
    "Para ayudarte mejor, contame en un solo mensaje:\n"
    "• ¿Buscás *casa*, *departamento* o *lote*?\n"
    "• Si es casa o departamento: ¿*zona o barrio* preferido?, ¿Cuántos *dormitorios* como mínimo?\n"
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
    "• ¿*Tenés zona o barrio* preferido?\n"
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

WAITLIST_CATALOG_EXHAUSTED_INTRO = (
    "Revisé el catálogo y no tengo más opciones distintas para mostrarte.\n\n"
)

WAITLIST_CONSENT_TEXT = (
    "¿Te parece si te tomo los datos para buscar propiedades que se ajusten "
    "a lo que necesitás? Un asesor se comunicará para coordinar."
)


def build_waitlist_consent_question(*, catalog_exhausted: bool = False) -> str:
    if catalog_exhausted:
        return WAITLIST_CATALOG_EXHAUSTED_INTRO + WAITLIST_CONSENT_TEXT
    return WAITLIST_CONSENT_TEXT


def build_triage_message(tenant_name: str) -> str:
    name = (tenant_name or "").strip() or "la inmobiliaria"
    return (
        f"¡Hola! 👋 Soy el asistente de *{name}* y estoy para ayudarte "
        "a encontrar lo que estás buscando.\n\n"
        "Contame, ¿estás buscando algo para *alquilar*, *comprar* o *vender*?"
    )


def build_listing_intro(*, option_count: int) -> str:
    if option_count == 1:
        return "¡Buenísimo! Te comparto una opción que encaja con lo que buscás:"
    return "¡Buenísimo! Te comparto algunas opciones que encajan con lo que buscás:"


def build_listing_closing(*, option_count: int) -> str:
    if option_count == 1:
        return "¿Te llama la atención para pasarte más detalles?"
    return "¿Cuál te llama más la atención para pasarte más detalles?"


def build_listing_default_closing(*, option_count: int) -> str:
    if option_count == 1:
        return build_listing_closing(option_count=1)
    return (
        "¿Alguna de estas opciones te llama la atención para pasarte más detalles?"
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
