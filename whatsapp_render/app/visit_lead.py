from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.llm.deepseek import chat_completion

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)


@dataclass
class VisitLeadSummary:
    interest_summary: str
    conversation_summary: str


def _parse_classifier_json(raw: str) -> VisitLeadSummary | None:
    body = (raw or "").strip()
    if not body:
        return None
    match = _JSON_BLOCK_RE.search(body)
    if match:
        body = match.group(1).strip()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    interest = str(data.get("interest_summary") or "").strip()
    conversation = str(data.get("conversation_summary") or "").strip()
    if not interest and not conversation:
        return None
    return VisitLeadSummary(
        interest_summary=interest,
        conversation_summary=conversation or interest,
    )


def visit_lead_fallback(
    *,
    flow_path: str,
    visit_interest_text: str,
    visit_schedule_raw: str,
    property_ref: str = "",
    user_messages: str = "",
) -> VisitLeadSummary:
    prop = (property_ref or "").strip()
    interest = (visit_interest_text or "").strip()
    schedule = (visit_schedule_raw or "").strip()
    branch = (flow_path or "").strip().lower()
    label = "alquiler" if branch == "alquiler" else "compra"
    interest_line = interest or "Interés en visitar una propiedad"
    if prop:
        interest_line = f"{interest_line} ({prop})"
    parts = [
        f"Cliente en {label}: {interest_line}.",
    ]
    if schedule:
        parts.append(f"Preferencias de visita: {schedule}.")
    if (user_messages or "").strip():
        parts.append("Contexto adicional en mensajes del cliente.")
    conversation = " ".join(parts)
    return VisitLeadSummary(
        interest_summary=interest_line[:300],
        conversation_summary=conversation[:800],
    )


async def summarize_visit_lead(
    *,
    flow_path: str,
    user_messages: str,
    visit_interest_text: str,
    visit_schedule_raw: str,
    property_ref: str = "",
    property_context: str = "",
    log_context: dict | None = None,
) -> VisitLeadSummary:
    """Resume conversación + preferencias de visita para el lead interno."""
    system = (
        "Sos un asistente inmobiliario. El cliente quiere visitar una propiedad "
        "y ya indicó preferencias de días/horarios. "
        "Respondé SOLO JSON válido con claves: interest_summary, conversation_summary. "
        "interest_summary: una línea (propiedad + intención de visita). "
        "conversation_summary: 2-4 oraciones en prosa para el equipo (búsqueda, "
        "opciones vistas, propiedad de interés, preferencias de visita). "
        "No inventes datos; usá solo el contexto provisto."
    )
    user = (
        f"Rama: {flow_path}\n\n"
        f"### Mensaje de interés en visita\n{visit_interest_text or '(sin dato)'}\n\n"
        f"### Preferencias de días/horarios\n{visit_schedule_raw or '(sin dato)'}\n\n"
        f"### Propiedad de referencia\n{property_ref or '(sin ref)'}\n\n"
        f"### Contexto de propiedad\n{property_context or '(sin detalle)'}\n\n"
        f"### Mensajes del cliente en esta conversación\n{user_messages or '(sin historial)'}"
    )
    ctx = dict(log_context or {})
    ctx["prompt_source"] = "visit_lead_summarize"
    try:
        raw = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=400,
            log_context=ctx,
        )
        parsed = _parse_classifier_json(raw)
        if parsed:
            return parsed
    except RuntimeError:
        pass
    return visit_lead_fallback(
        flow_path=flow_path,
        visit_interest_text=visit_interest_text,
        visit_schedule_raw=visit_schedule_raw,
        property_ref=property_ref,
        user_messages=user_messages,
    )
