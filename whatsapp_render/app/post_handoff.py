from __future__ import annotations

from typing import Any

from app.catalog import get_catalog_for_flow
from app.catalog_profiles import format_row_compact
from app.conversation import build_model_messages
from app.listing_context import (
    build_active_property_context_block,
    load_last_listing_rows,
    load_last_viewed_property_row,
)
from app.llm.deepseek import chat_completion
from app.llm.post_handoff_classifier import (
    PostHandoffCategory,
    classify_post_handoff_message,
)
from app.search_profile import get_intake_raw_text, mark_intake_prompt_sent
from app.session_lifecycle import get_handoff_context_ref, get_handoff_kind
from app.session_state import SessionState, capture_summary_text, resolve_flow_path
from app.waitlist_flow import get_waitlist_raw_text

_CHAT_MAX_TOKENS = 256


def _listing_summary_for_waitlist(
    catalog_path: str | None,
    capture_data: dict[str, Any] | None,
    branch: str,
) -> str:
    rows = load_last_listing_rows(catalog_path, capture_data)
    lines: list[str] = []
    for index, row in enumerate(rows, start=1):
        compact = format_row_compact(row, branch)
        if compact:
            lines.append(f"Opción {index}: {compact}")
    return "\n".join(lines)


def build_handoff_context_block(
    capture_data: dict[str, Any] | None,
    *,
    handoff_kind: str,
    catalog_path: str | None,
    flow_path: str,
) -> str:
    kind = (handoff_kind or "").strip().lower()
    capture = capture_data or {}

    if kind == "visit":
        row = load_last_viewed_property_row(
            capture,
            catalog_csv_path=catalog_path,
        )
        if row is not None:
            block = build_active_property_context_block(row, branch=flow_path)
            if block:
                return block
        ref = get_handoff_context_ref(capture)
        return f"Propiedad de interés registrada: {ref}" if ref else ""

    if kind == "waitlist":
        parts: list[str] = []
        listing = _listing_summary_for_waitlist(catalog_path, capture, flow_path)
        if listing.strip():
            parts.append(f"Opciones que vio el cliente:\n{listing}")
        intake = get_intake_raw_text(capture)
        if intake.strip():
            parts.append(f"Búsqueda original: {intake}")
        waitlist = get_waitlist_raw_text(capture)
        if waitlist.strip():
            parts.append(f"Datos de lista de espera: {waitlist}")
        ref = get_handoff_context_ref(capture)
        if ref.strip():
            parts.insert(0, f"Contexto registrado: {ref}")
        return "\n\n".join(parts)

    if kind == "captacion":
        summary = capture_summary_text(capture)
        if summary.strip():
            return f"Datos de captación registrados: {summary}"
        ref = get_handoff_context_ref(capture)
        return f"Captación registrada: {ref}" if ref else ""

    ref = get_handoff_context_ref(capture)
    return ref or ""


def resolve_handoff_catalog_path(
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    capture_data: dict[str, Any] | None,
) -> str | None:
    _name, _branch, path = get_catalog_for_flow(
        flow_path,
        catalog_sale_path,
        catalog_rent_path,
    )
    if path:
        return path
    raw = (capture_data or {}).get("last_listing")
    if isinstance(raw, dict):
        stored = str(raw.get("catalog_path") or "").strip()
        if stored:
            return stored
    viewed = (capture_data or {}).get("last_viewed_property")
    if isinstance(viewed, dict):
        stored = str(viewed.get("catalog_path") or "").strip()
        if stored:
            return stored
    return None


async def post_handoff_property_reply(
    *,
    tenant_name: str,
    flow_path: str,
    user_text: str,
    handoff_kind: str,
    context_ref: str,
    property_context_block: str,
    log_context: dict | None = None,
) -> str:
    name = (tenant_name or "").strip() or "la inmobiliaria"
    kind = (handoff_kind or "").strip().lower()
    kind_label = {
        "visit": "visita a propiedad",
        "waitlist": "lista de espera",
        "captacion": "captación de propiedad para vender",
    }.get(kind, "consulta registrada")

    system = (
        f"Sos el asistente de WhatsApp de {name} (inmobiliaria).\n"
        f"El cliente ya cerró el flujo de {kind_label}; un asesor humano lo contactará.\n\n"
        "Reglas:\n"
        "- Respondé la pregunta concreta usando SOLO el contexto provisto.\n"
        "- No inventes datos, precios ni características.\n"
        "- No ofrezcas visitas, listados ni [LISTADO:ids].\n"
        "- No propongas fechas de visita; el asesor coordina.\n"
        "- Si el dato no está en el contexto, decilo brevemente.\n"
        "- Respuestas cortas (2-4 líneas), tono amable."
    )
    if property_context_block.strip():
        system += (
            f"\n\n### CONTEXTO REGISTRADO\n{property_context_block.strip()}\n"
            f"Referencia: {context_ref or '(sin ref)'}"
        )

    messages = build_model_messages(system, user_text)
    ctx = dict(log_context or {})
    ctx["prompt_source"] = "post_handoff_reply"
    ctx["handoff_kind"] = kind
    try:
        return (
            await chat_completion(messages, max_tokens=_CHAT_MAX_TOKENS, log_context=ctx)
        ).strip()
    except RuntimeError:
        return (
            "Un asesor del equipo ya tiene tu consulta registrada y se comunicará pronto. "
            "Si necesitás algo más sobre esa propiedad, podés consultarnos cuando te contacten."
        )


def build_new_search_reply(
    *,
    tenant_name: str,
    user_text: str,
) -> tuple[str, str]:
    """Tras reinicio: flow_path resuelto + mensaje de apertura."""
    session = SessionState(flow_path="nuevo", capture_data={})
    flow_path = resolve_flow_path(session, user_text)
    from app.prompts.templates import build_intake_bundle_question, build_triage_message

    if flow_path in ("compra", "alquiler"):
        return flow_path, build_intake_bundle_question(flow_path)
    if flow_path == "captacion":
        return flow_path, (
            f"Hola, soy el asistente de *{(tenant_name or '').strip() or 'la inmobiliaria'}*. "
            "Contame sobre la propiedad que querés vender o tasar."
        )
    return "nuevo", build_triage_message(tenant_name)


async def handle_post_handoff_turn(
    *,
    tenant_name: str,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    capture_data: dict[str, Any],
    user_text: str,
    wa_id: str = "",
) -> tuple[str, dict[str, Any], str, bool, bool, str | None]:
    """
    Retorna: text, capture_data, phase, skip_outbound, skip_property_delivery, flow_path_override
    """
    handoff_kind = get_handoff_kind(capture_data)
    context_ref = get_handoff_context_ref(capture_data)
    catalog_path = resolve_handoff_catalog_path(
        flow_path,
        catalog_sale_path,
        catalog_rent_path,
        capture_data,
    )
    context_block = build_handoff_context_block(
        capture_data,
        handoff_kind=handoff_kind,
        catalog_path=catalog_path,
        flow_path=flow_path,
    )

    category = await classify_post_handoff_message(
        user_text=user_text,
        handoff_kind=handoff_kind,
        context_ref=context_ref,
        property_context_block=context_block,
        flow_path=flow_path,
        capture_data=capture_data,
        log_context={"flow_path": flow_path, "wa_id": wa_id, "handoff_kind": handoff_kind},
    )

    if category == PostHandoffCategory.THANKS:
        return "", dict(capture_data), "post_handoff_thanks", True, True, None

    if category == PostHandoffCategory.NEW_SEARCH:
        new_flow, reply = build_new_search_reply(
            tenant_name=tenant_name,
            user_text=user_text,
        )
        new_capture: dict[str, Any] = {}
        if new_flow in ("compra", "alquiler"):
            new_capture = mark_intake_prompt_sent(new_capture)
        return reply, new_capture, "post_handoff_new_search", False, True, new_flow

    reply = await post_handoff_property_reply(
        tenant_name=tenant_name,
        flow_path=flow_path,
        user_text=user_text,
        handoff_kind=handoff_kind,
        context_ref=context_ref,
        property_context_block=context_block,
        log_context={"flow_path": flow_path, "wa_id": wa_id},
    )
    return reply, dict(capture_data), "post_handoff_property_question", False, True, None
