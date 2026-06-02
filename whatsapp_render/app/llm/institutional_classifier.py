from __future__ import annotations

import json
import os
import re
from enum import Enum

from app.llm.deepseek import chat_completion

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)

_HOURS_RE = re.compile(
    r"\b("
    r"horario?s?|atienden|atencion|atenci[oó]n|abren|cierran|"
    r"abierto|cerrado|s[aá]bados?|domingos?|feriados?"
    r")\b",
    re.I,
)
_LOCATION_RE = re.compile(
    r"\b("
    r"d[oó]nde\s+est[aá]n|ubicaci[oó]n|direcci[oó]n|"
    r"c[oó]mo\s+llego|d[oó]nde\s+quedan|sucursal|oficina"
    r")\b",
    re.I,
)
_SOCIAL_RE = re.compile(
    r"\b("
    r"instagram|facebook|linkedin|tiktok|twitter|"
    r"redes\s+sociales?|p[aá]gina\s+web|sitio\s+web|"
    r"whatsapp\s+business|link\s+de\s+"
    r")\b",
    re.I,
)
_PROPERTY_INTENT_RE = re.compile(
    r"\b("
    r"opci[oó]n\s*\d+|la\s+opci[oó]n|precio|alquilar|comprar|vender|"
    r"visitar|visita|dormitorio|ambiente|expensas|pileta|cochera|"
    r"m[aá]s\s+opciones|busco|propiedad|depto|departamento"
    r")\b",
    re.I,
)


class InstitutionalCategory(str, Enum):
    NONE = "none"
    OFFICE_HOURS = "office_hours"
    OFFICE_LOCATION = "office_location"
    SOCIAL_LINKS = "social_links"


def institutional_classifier_enabled() -> bool:
    raw = os.environ.get("INSTITUTIONAL_CLASSIFIER_ENABLED", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _parse_category_json(raw: str) -> InstitutionalCategory | None:
    body = (raw or "").strip()
    if not body:
        return None
    match = _JSON_BLOCK_RE.search(body)
    if match:
        body = match.group(1).strip()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", body, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    cat = str(data.get("category") or "").strip().lower()
    for member in InstitutionalCategory:
        if cat == member.value:
            return member
    return None


def classify_institutional_fallback(user_text: str) -> InstitutionalCategory:
    body = (user_text or "").strip()
    if not body:
        return InstitutionalCategory.NONE
    if _PROPERTY_INTENT_RE.search(body) and not (
        _HOURS_RE.search(body) or _LOCATION_RE.search(body) or _SOCIAL_RE.search(body)
    ):
        return InstitutionalCategory.NONE
    if _HOURS_RE.search(body) and not _LOCATION_RE.search(body) and not _SOCIAL_RE.search(
        body
    ):
        return InstitutionalCategory.OFFICE_HOURS
    if _SOCIAL_RE.search(body):
        return InstitutionalCategory.SOCIAL_LINKS
    if _LOCATION_RE.search(body):
        return InstitutionalCategory.OFFICE_LOCATION
    return InstitutionalCategory.NONE


def _system_prompt() -> str:
    return (
        "Sos un clasificador de consultas institucionales para una inmobiliaria. "
        "Clasificá el mensaje del cliente en EXACTAMENTE una categoría. "
        'Respondé SOLO JSON válido: {"category": "..."}.\n\n'
        "Categorías:\n"
        "- none: búsqueda o consulta sobre propiedades (precio, opción 2, visita a un "
        "depto, más opciones, comprar/alquilar/vender, características de un inmueble).\n"
        "- office_hours: horarios de atención de la inmobiliaria (cuándo atienden, "
        "si abren sábados, etc.).\n"
        "- office_location: dónde está la inmobiliaria, dirección de la oficina, "
        "cómo llegar (NO dirección de una propiedad del listado).\n"
        "- social_links: redes sociales, Instagram, Facebook, página web de la "
        "inmobiliaria.\n\n"
        "Si el mensaje mezcla temas, elegí la intención principal. "
        "Ante duda sobre una propiedad concreta, usá none."
    )


async def classify_institutional_message(
    *,
    user_text: str,
    flow_path: str,
    recent_user_messages: str = "",
    log_context: dict | None = None,
) -> InstitutionalCategory:
    body = (user_text or "").strip()
    if not body or not institutional_classifier_enabled():
        return InstitutionalCategory.NONE

    context_block = (recent_user_messages or "").strip()
    user = (
        f"Rama de conversación: {flow_path or 'nuevo'}\n\n"
        f"### Mensajes recientes del cliente\n"
        f"{context_block or '(sin historial)'}\n\n"
        f"### Mensaje actual\n{body}"
    )
    ctx = dict(log_context or {})
    ctx["prompt_source"] = "institutional_classify"
    try:
        raw = await chat_completion(
            [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": user},
            ],
            max_tokens=64,
            log_context=ctx,
        )
        parsed = _parse_category_json(raw)
        if parsed is not None:
            return parsed
    except RuntimeError:
        pass
    return classify_institutional_fallback(body)
