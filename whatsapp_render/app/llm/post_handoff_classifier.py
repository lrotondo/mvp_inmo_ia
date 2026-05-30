from __future__ import annotations

import json
import re
from enum import Enum

from app.listing_context import user_wants_alternate_listing
from app.llm.deepseek import chat_completion
from app.search_profile import user_requests_new_search

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)

_THANKS_RE = re.compile(
    r"^\s*("
    r"gracias|muchas\s+gracias|ok|okay|dale|listo|perfecto|genial|"
    r"excelente|buen[ií]simo|chau|adi[oó]s|hasta\s+luego|nos\s+vemos|"
    r"de\s+nada|bueno|bien"
    r")[\s!.]*$",
    re.I,
)

_ATTRIBUTE_QUESTION_RE = re.compile(
    r"\b("
    r"tiene|tienen|hay\s+|cu[aá]nto|cu[aá]ntos|cu[aá]l|"
    r"metros?|m2|pileta|cochera|mascotas?|expensas?|"
    r"caracter[ií]sticas?|precio|incluye|acepta|admite|"
    r"dormitorios?|ambientes?|patio|balc[oó]n|ascensor"
    r")\b|\?",
    re.I,
)


class PostHandoffCategory(str, Enum):
    THANKS = "thanks"
    PROPERTY_QUESTION = "property_question"
    NEW_SEARCH = "new_search"


def _parse_category_json(raw: str) -> PostHandoffCategory | None:
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
    for member in PostHandoffCategory:
        if cat == member.value:
            return member
    return None


def classify_post_handoff_fallback(
    user_text: str,
    *,
    capture_data: dict | None = None,
) -> PostHandoffCategory:
    body = (user_text or "").strip()
    if not body:
        return PostHandoffCategory.THANKS
    if _THANKS_RE.match(body):
        return PostHandoffCategory.THANKS
    if user_requests_new_search(body, capture_data) or user_wants_alternate_listing(body):
        return PostHandoffCategory.NEW_SEARCH
    if _ATTRIBUTE_QUESTION_RE.search(body):
        return PostHandoffCategory.PROPERTY_QUESTION
    if re.search(
        r"\b("
        r"busco|quiero|necesito|otras?\s+opciones|m[aá]s\s+opciones|"
        r"empezar\s+de\s+nuevo|de\s+nuevo|comprar|alquilar|vender"
        r")\b",
        body,
        re.I,
    ):
        return PostHandoffCategory.NEW_SEARCH
    return PostHandoffCategory.PROPERTY_QUESTION


def _system_prompt() -> str:
    return (
        "Sos un clasificador de mensajes post-handoff inmobiliario. "
        "El cliente ya recibió confirmación de que un asesor humano lo contactará. "
        "Clasificá el mensaje entrante en EXACTAMENTE una categoría. "
        "Respondé SOLO JSON válido: {\"category\": \"...\"}.\n\n"
        "Categorías:\n"
        "- thanks: agradecimiento o despedida cordial sin nueva consulta "
        "(ej. gracias, ok, perfecto, genial, chau, dale).\n"
        "- property_question: pregunta concreta sobre el contexto ya registrado "
        "(visita: esa propiedad; waitlist: opciones vistas o requisitos; "
        "captación: su propiedad o el proceso de tasación).\n"
        "- new_search: quiere buscar otras opciones, cambiar de rubro, "
        "empezar de nuevo, comprar/alquilar/vender algo distinto."
    )


async def classify_post_handoff_message(
    *,
    user_text: str,
    handoff_kind: str,
    context_ref: str,
    property_context_block: str,
    flow_path: str,
    capture_data: dict | None = None,
    log_context: dict | None = None,
) -> PostHandoffCategory:
    body = (user_text or "").strip()
    if not body:
        return PostHandoffCategory.THANKS

    user = (
        f"Rama: {flow_path}\n"
        f"Tipo de cierre (handoff): {handoff_kind or '(sin dato)'}\n"
        f"Referencia registrada: {context_ref or '(sin ref)'}\n\n"
        f"### Contexto disponible\n{property_context_block or '(sin contexto)'}\n\n"
        f"### Mensaje del cliente\n{body}"
    )
    ctx = dict(log_context or {})
    ctx["prompt_source"] = "post_handoff_classify"
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
    return classify_post_handoff_fallback(body, capture_data=capture_data)
