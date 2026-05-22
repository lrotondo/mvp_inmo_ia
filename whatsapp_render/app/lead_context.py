from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from app.catalog import load_properties_for_catalog_path, resolve_rent_catalog_path

if TYPE_CHECKING:
    from app.conversation import HistoryTurn

LeadType = Literal["venta", "alquiler", "captacion"]

_VISIT_RE = re.compile(
    r"\b("
    r"visitar|visita|verla|verlo|ver\s+la|ver\s+el|coordinar\s+visita|agendar|"
    r"quiero\s+ver|me\s+interesa\s+(?:el|la|esa|ese)|reservar|reserva"
    r")\b",
    re.I,
)

# Alquiler: sin "me interesa la/esa" — interés leve no cuenta como visita
_RENT_VISIT_RE = re.compile(
    r"\b("
    r"visitar|visita|verla|verlo|verlos|verlas|ver\s+la|ver\s+el|ver\s+los|"
    r"coordinar\s+visita|agendar|quiero\s+ver|reservar|reserva|"
    r"cu[aá]ndo\s+podr[ií]a\s+ver|cu[aá]ndo\s+puedo\s+ver|"
    r"poder[ií]a\s+ver|podr[ií]a\s+ver|"
    r"los\s+dos\s+me\s+interesan|las\s+dos\s+me\s+interesan|"
    r"ambas\s+me\s+interesan|ambos\s+me\s+interesan"
    r")\b",
    re.I,
)

_TIME_PREFERENCE_RE = re.compile(
    r"\b("
    r"ma[nñ]ana|tarde|noche|fin\s+de\s+semana|s[aá]bado|domingo|"
    r"preferentemente|prefiero|me\s+queda\s+mejor|"
    r"horario|franja|despu[eé]s\s+del\s+mediod[ií]a|antes\s+del\s+mediod[ií]a"
    r")\b",
    re.I,
)

_BOT_ASKED_TIME_PREFERENCE_RE = re.compile(
    r"\b("
    r"ma[nñ]ana|tarde|fin\s+de\s+semana|preferencia\s+general|"
    r"qu[eé]\s+franja|horario\s+prefer"
    r")\b",
    re.I,
)

_HUMAN_CONTACT_RE = re.compile(
    r"\b("
    r"asesor|humano|persona|hablar\s+con|comunicar|comunicarme|contacto|"
    r"agente|vendedor|llamar|que\s+me\s+contacten|me\s+contacten"
    r")\b",
    re.I,
)

_BROWSE_ONLY_RE = re.compile(
    r"\b("
    r"dec[ií]me\s+qu[eé]\s+ten[eé]s|qu[eé]\s+ten[eé]s|qu[eé]\s+hay|"
    r"ten[eé]s\s+algo|alguna\s+opci[oó]n|ver\s+opci[oó]nes|"
    r"mostr[aá](?:me)?\s+opci[oó]nes|qu[eé]\s+disponible|mostr[aá]me|"
    r"qu[eé]\s+opciones|opciones\s+para\s+comprar|opciones\s+de\s+compra|"
    r"opciones\s+para\s+alquilar|opciones\s+de\s+alquiler|qu[eé]\s+casas|"
    r"qu[eé]\s+departamentos|qu[eé]\s+propiedades"
    r")\b",
    re.I,
)

_FLOW_SWITCH_COMPRA_RE = re.compile(
    r"\b("
    r"busco\s+comprar|quiero\s+comprar|opciones\s+de\s+compra|"
    r"opciones\s+para\s+comprar|qu[eé]\s+opciones.*compr"
    r")\b",
    re.I,
)
_FLOW_SWITCH_ALQUILER_RE = re.compile(
    r"\b("
    r"busco\s+alquilar|quiero\s+alquilar|opciones\s+de\s+alquiler|"
    r"opciones\s+para\s+alquilar|necesito\s+alquilar|qu[eé]\s+opciones.*alquil"
    r")\b",
    re.I,
)
_FLOW_SWITCH_CAPTACION_RE = re.compile(
    r"\b(quiero\s+vender|tengo\s+.*\s+para\s+vender|vender\s+mi)\b",
    re.I,
)

_FLOW_SWITCH_BY_PATH: dict[str, re.Pattern[str]] = {
    "compra": _FLOW_SWITCH_COMPRA_RE,
    "alquiler": _FLOW_SWITCH_ALQUILER_RE,
    "captacion": _FLOW_SWITCH_CAPTACION_RE,
}

_PROPERTY_CHOICE_RE = re.compile(
    r"\b("
    r"me\s+interesa|me\s+gusta|me\s+cierra|me\s+quedo|"
    r"quiero\s+(?:esa|ese|el|la|av\.?|calle)|"
    r"esa\s+(?:casa|depto|propiedad)|la\s+de\s+|"
    r"opcion\s+\d|opci[oó]n\s+\d|id\s*\d"
    r")\b",
    re.I,
)

_NO_DEFINED_ZONE_RE = re.compile(
    r"\b("
    r"no\s+tengo\s+zona|no\s+tengo\s+zonas?|"
    r"no\s+tengo\s+preferencia\s+de\s+zona|no\s+tengo\s+zonas?\s+preferid[ao]s?|"
    r"sin\s+zona\s+definida|sin\s+zonas?\s+preferid[ao]s?|"
    r"no\s+tengo\s+barrio|"
    r"cualquier\s+zona|cualquier\s+barrio|"
    r"sin\s+preferencia\s+de\s+zona|no\s+importa\s+la\s+zona|"
    r"no\s+me\s+importa\s+(?:la\s+)?zona|"
    r"toda\s+la\s+ciudad|en\s+cualquier\s+parte|"
    r"no\s+tengo\s+ubicaci[oó]n\s+definida|sin\s+ubicaci[oó]n\s+definida"
    r")\b",
    re.I,
)

_ZONE_SIGNAL_RE = re.compile(
    r"\b("
    r"barrio|zona|centro|microcentro|norte|sur|este|oeste|"
    r"country|los\s+nogales|garibaldi|mitre|"
    r"en\s+(?!alquiler|venta|compra\b)(?:el\s+|la\s+)?[a-záéíóúñ]{3,}|"
    r"por\s+[a-záéíóúñ]{3,}|"
    r"cerca\s+de|"
    r"tandil"
    r")\b",
    re.I,
)

_BEDROOM_SIGNAL_RE = re.compile(
    r"\b("
    r"\d+\s*(?:ó|o|or|y)\s*m[aá]s\s*dormitorios?|"
    r"m[aá]s\s+de\s+\d+\s*dorm(?:itorios?)?|"
    r"\d+\s*\+\s*dorm(?:itorios?)?|"
    r"\d+\s*(?:dormitorios?|dorm\.?|ambientes?)|"
    r"mono\s*amb(?:iente)?|"
    r"(?:un|una|dos|tres|cuatro|cinco|seis)\s+dormitorios?|"
    r"(?:un|una|dos|tres|cuatro)\s+ambientes?"
    r")\b",
    re.I,
)

_BUDGET_USD_RE = re.compile(
    r"(?:"
    r"us\s*\$?\s*[\d.,]+|"
    r"usd\s*[\d.,]+|"
    r"\$\s*[\d.,]+\s*(?:usd|d[oó]lares?)?|"
    r"presupuesto\s*(?:de\s+)?[\d.,]+|"
    r"tengo\s+[\d.,]{4,}|"
    r"[\d]{2,3}[.,]?\d{3}\s*(?:usd|d[oó]lares?)?"
    r")",
    re.I,
)

_PROPERTY_TYPE_RE = re.compile(
    r"\b(casa|departamento|depto|duplex|d[uú]plex|ph|lote|terreno|local)\b",
    re.I,
)


def lead_type_from_flow_path(flow_path: str) -> LeadType:
    path = (flow_path or "").strip().lower()
    if path == "alquiler":
        return "alquiler"
    if path == "captacion":
        return "captacion"
    return "venta"


def catalog_paths_for_flow(
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
) -> list[str]:
    path = (flow_path or "").strip().lower()
    if path == "alquiler":
        rent = resolve_rent_catalog_path(catalog_sale_path, catalog_rent_path)
        return [rent] if rent else []
    if path == "compra":
        sale = (catalog_sale_path or "").strip()
        return [sale] if sale else []
    return []


def format_user_messages_plain(
    history: list[HistoryTurn],
    current_user_text: str = "",
) -> str:
    parts: list[str] = []
    for turn in history:
        if turn.role == "user" and turn.content.strip():
            parts.append(turn.content.strip())
    if current_user_text.strip():
        parts.append(current_user_text.strip())
    return "\n".join(parts)


def _user_turn_texts(history: list[HistoryTurn]) -> list[str]:
    return [t.content.strip() for t in history if t.role == "user" and t.content.strip()]


def user_messages_for_flow(
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
) -> str:
    """
    Mensajes del cliente desde el último cambio explícito a esta rama (compra/alquiler).
    Evita que elecciones de alquiler contaminen gates de compra.
    """
    path = (flow_path or "").strip().lower()
    turns = _user_turn_texts(history)
    switch_re = _FLOW_SWITCH_BY_PATH.get(path)

    start = 0
    if switch_re is not None:
        for idx, msg in enumerate(turns):
            if switch_re.search(msg):
                start = idx

    scoped = turns[start:]
    current = current_user_text.strip()
    if current:
        if not scoped or scoped[-1] != current:
            scoped.append(current)
    elif scoped:
        pass
    elif current:
        scoped = [current]

    if not scoped and current:
        return current
    return "\n".join(scoped)


def should_suppress_visit_alerts(
    current_user_text: str,
    *,
    flow_just_switched: bool = False,
) -> bool:
    """Browse o primer mensaje tras cambiar de rama: no alertas de visita."""
    current = current_user_text.strip()
    if not current:
        return False
    if current_message_is_browse_only(current):
        return True
    return flow_just_switched and current_message_is_browse_only(current)


def user_declined_zone_preference(user_messages_text: str) -> bool:
    return bool(_NO_DEFINED_ZONE_RE.search(user_messages_text))


def user_has_budget_usd(user_messages_text: str) -> bool:
    return bool(_BUDGET_USD_RE.search(user_messages_text))


def user_property_type_label(user_messages_text: str) -> str | None:
    """«casa» o «departamento» si el cliente lo indicó (duplex/ph → departamento)."""
    from app.catalog_search import parse_property_type_from_blob

    return parse_property_type_from_blob(user_messages_text)


def user_has_property_type(user_messages_text: str) -> bool:
    return user_property_type_label(user_messages_text) is not None


def user_search_profile_ready(
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
) -> bool:
    """True si el perfil de búsqueda está completo (ver app.search_profile)."""
    from app.search_profile import build_search_profile

    path = (flow_path or "").strip().lower()
    if path not in ("compra", "alquiler"):
        return True
    return build_search_profile(history, current_user_text, flow_path).is_complete


from app.property_matching import _normalize_property_match_text, extract_property_ref
from app.visit_intent import (
    bot_asked_visit_time_preference,
    build_rent_visit_lead_notes,
    conversation_requests_human,
    conversation_wants_visit,
    conversation_wants_visit_rent,
    extract_visit_time_preference_label,
    rent_visit_ready_for_alert,
    scoped_rent_visit_intent,
    user_gave_visit_time_preference,
)


def user_signals_real_interest(
    history: list[HistoryTurn],
    current_user_text: str,
) -> bool:
    """Atajos deterministas antes del clasificador (solo mensajes del cliente)."""
    user_blob = format_user_messages_plain(history, current_user_text)
    if not user_blob.strip():
        return False
    if conversation_wants_visit(user_blob):
        return True
    if conversation_requests_human(user_blob):
        return True
    return False


def user_signals_real_interest_rent(
    history: list[HistoryTurn],
    current_user_text: str,
) -> bool:
    """Alquiler: visita/asesor en mensaje actual (evita re-disparar por historial)."""
    _ = history
    return user_signals_real_interest_rent_current_message(current_user_text)


def user_signals_real_interest_rent_current_message(current_user_text: str) -> bool:
    """Compat: visita/asesor solo en mensaje actual (usar rent_visit_ready_for_alert en alquiler)."""
    current = current_user_text.strip()
    if not current:
        return False
    if conversation_wants_visit_rent(current):
        return True
    if conversation_requests_human(current):
        return True
    return False


def user_signals_real_interest_current_message(current_user_text: str) -> bool:
    """Señales de interés solo en el mensaje actual (compra: evita historial de otra rama)."""
    current = current_user_text.strip()
    if not current:
        return False
    if conversation_wants_visit(current):
        return True
    if conversation_requests_human(current):
        return True
    if _PROPERTY_CHOICE_RE.search(current):
        return True
    return False


def format_conversation_for_classifier(
    history: list[HistoryTurn],
    current_user_text: str = "",
    *,
    flow_path: str = "compra",
) -> str:
    """Solo mensajes del cliente en la rama actual — sin contaminar con otra intención."""
    scoped = user_messages_for_flow(history, current_user_text, flow_path)
    if not scoped.strip():
        return ""
    lines = [f"Cliente: {line}" for line in scoped.split("\n") if line.strip()]
    return "\n".join(lines)


def current_message_is_browse_only(current_user_text: str) -> bool:
    body = current_user_text.strip()
    if not body:
        return False
    return bool(_BROWSE_ONLY_RE.search(body))


def qualifies_for_lead_notification(
    history: list[HistoryTurn],
    current_user_text: str,
    *,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    flow_just_switched: bool = False,
) -> bool:
    """
    Puerta determinista tras el clasificador LLM.
    Evita leads por 'decime qué tenés', datos inferidos del catálogo o mensajes del bot.
    """
    current = current_user_text.strip()
    if should_suppress_visit_alerts(
        current_user_text, flow_just_switched=flow_just_switched
    ):
        return False

    scoped = user_messages_for_flow(history, current_user_text, flow_path)
    if not scoped.strip():
        return False

    path = (flow_path or "").strip().lower()

    if path == "alquiler":
        return rent_visit_ready_for_alert(
            history, current_user_text, flow_path
        )

    if user_signals_real_interest_current_message(current_user_text):
        return True

    prop = extract_property_ref(
        "",
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        history=history,
        current_user_text=current_user_text,
        user_only=True,
    )
    if not prop:
        return False

    if _PROPERTY_CHOICE_RE.search(current):
        return True

    prop_lower = prop.lower()
    if prop_lower in current.lower():
        if len(prop) >= 10 or any(ch.isdigit() for ch in prop):
            return True
    return False
