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
    r"mostr[aá](?:me)?\s+opci[oó]nes|qu[eé]\s+disponible|mostr[aá]me"
    r")\b",
    re.I,
)

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
    r"no\s+tengo\s+zona|sin\s+zona\s+definida|no\s+tengo\s+barrio|"
    r"cualquier\s+zona|sin\s+preferencia\s+de\s+zona|no\s+importa\s+la\s+zona|"
    r"no\s+tengo\s+ubicaci[oó]n\s+definida|sin\s+ubicaci[oó]n\s+definida"
    r")\b",
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


def user_declined_zone_preference(user_messages_text: str) -> bool:
    return bool(_NO_DEFINED_ZONE_RE.search(user_messages_text))


def extract_property_ref(
    conversation_text: str,
    *,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    history: list[HistoryTurn] | None = None,
    current_user_text: str = "",
    user_only: bool = False,
) -> str:
    if user_only and history is not None:
        blob = format_user_messages_plain(history, current_user_text).lower()
    else:
        blob = conversation_text.lower()

    skip_barrio = user_declined_zone_preference(blob)
    best = ""
    best_len = 0

    for csv_path in catalog_paths_for_flow(flow_path, catalog_sale_path, catalog_rent_path):
        for row in load_properties_for_catalog_path(csv_path):
            candidates: list[str] = []
            row_id = str(row.get("ID", "")).strip()
            direccion = str(row.get("Direccion", "")).strip()
            barrio = str(row.get("Barrio", "")).strip()
            if row_id:
                candidates.append(row_id)
                candidates.append(f"ID {row_id}")
            if direccion:
                candidates.append(direccion)
            if barrio and len(barrio) >= 5 and not skip_barrio:
                candidates.append(barrio)

            for cand in candidates:
                key = cand.lower()
                if len(key) < 4 or key not in blob:
                    continue
                if len(key) > best_len:
                    best = cand
                    best_len = len(key)

    return best


def conversation_wants_visit(conversation_text: str) -> bool:
    return bool(_VISIT_RE.search(conversation_text))


def conversation_requests_human(conversation_text: str) -> bool:
    return bool(_HUMAN_CONTACT_RE.search(conversation_text))


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


def format_conversation_for_classifier(
    history: list[HistoryTurn],
    current_user_text: str = "",
) -> str:
    """Solo mensajes del cliente — el asesor bot no cuenta como intención del usuario."""
    lines: list[str] = []
    for turn in history:
        if turn.role == "user" and turn.content.strip():
            lines.append(f"Cliente: {turn.content.strip()}")
    if current_user_text.strip():
        lines.append(f"Cliente: {current_user_text.strip()}")
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
) -> bool:
    """
    Puerta determinista tras el clasificador LLM.
    Evita leads por 'decime qué tenés', datos inferidos del catálogo o mensajes del bot.
    """
    plain = format_user_messages_plain(history, current_user_text)
    if not plain.strip():
        return False

    if user_signals_real_interest(history, current_user_text):
        return True

    current = current_user_text.strip()
    if current and current_message_is_browse_only(current):
        if not _PROPERTY_CHOICE_RE.search(current):
            if not conversation_wants_visit(current) and not conversation_requests_human(current):
                return False

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

    if _PROPERTY_CHOICE_RE.search(plain):
        return True
    if conversation_wants_visit(plain) or conversation_requests_human(plain):
        return True

    # ID o dirección mencionada explícitamente por el cliente (no solo barrio suelto)
    prop_lower = prop.lower()
    if prop_lower in plain.lower():
        if len(prop) >= 10 or any(ch.isdigit() for ch in prop):
            return True
    return False
