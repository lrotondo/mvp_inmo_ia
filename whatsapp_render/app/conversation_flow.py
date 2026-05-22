"""
Flujo de conversación lineal (único punto de decisión).

Fases:
  triage → intake → listing → after_listing (chat / detalle / visita)
  captacion (chat hasta datos completos)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.catalog import get_catalog_for_flow, load_properties_for_catalog_path
from app.catalog_search import select_listing_candidates
from app.capture_flow import append_user_flow_message
from app.conversation import build_model_messages
from app.llm.deepseek import chat_completion
from app.listing_context import (
    build_listing_catalog_block,
    listing_already_shown,
    load_last_listing_rows,
    merge_last_listing_into_capture,
    property_ref_from_listing_choice,
    resolve_listing_choice_row,
    user_requests_fresh_listing,
    user_requests_more_photos,
    user_showed_property_selection,
)
from app.property_matching import extract_property_ref
from app.prompts.templates import (
    CLOSING_CAPTACION_TEXT,
    build_chat_system_prompt,
    build_triage_message,
    format_visit_handoff,
)
from app.search_profile import (
    SearchProfile,
    build_search_profile,
    merge_search_profile_into_capture,
)
from app.session_state import (
    capture_is_complete,
    merge_capture_from_conversation,
)
from app.visit_intent import (
    conversation_requests_human,
    conversation_wants_visit,
    conversation_wants_visit_rent,
)

logger = logging.getLogger(__name__)

_LISTING_INTRO = (
    "¡Buenísimo! Te comparto algunas opciones que encajan con lo que buscás:"
)
_LISTING_CLOSING = "¿Cuál te llama más la atención para pasarte más detalles?"
_LISTING_EMPTY = (
    "Por ahora no tengo opciones que coincidan con tu búsqueda. "
    "¿Querés ampliar zona, tipo o presupuesto?"
)

_CHAT_MAX_TOKENS = 256

_QUESTION_ON_LISTING_RE = re.compile(
    r"\b("
    r"tiene|tienen|hay\s+|cu[aá]nto|cu[aá]ntos|cu[aá]l|"
    r"metros?|m2|pileta|cochera|mascotas?|expensas?|"
    r"caracter[ií]sticas?|diferencia|comparar|acepta|incluye"
    r")\b|\?",
    re.I,
)

_OPTION_INDEX_RE = re.compile(
    r"\b(?:opci[oó]n|la\s+opci[oó]n|el\s+de|la\s+de)\s*(?:n[°º]?\s*)?(\d+)\b",
    re.I,
)
_ORDINAL_RE = re.compile(
    r"\b(?:la|el)?\s*(primera|segunda|tercera|cuarta|primer|segundo|tercer|cuarto)\b",
    re.I,
)
_ORDINAL_INDEX = {
    "primera": 1,
    "primer": 1,
    "segunda": 2,
    "segundo": 2,
    "tercera": 3,
    "tercer": 3,
    "cuarta": 4,
    "cuarto": 4,
}


class Phase(str, Enum):
    TRIAGE = "triage"
    INTAKE = "intake"
    LISTING = "listing"
    DETAIL = "detail"
    GENERAL = "general"
    CAPTACION = "captacion"


@dataclass
class FlowContext:
    tenant_name: str
    flow_path: str
    catalog_sale_path: str | None
    catalog_rent_path: str | None
    system_prompt_override: str | None = None
    capture_data: dict[str, Any] | None = None


@dataclass(init=False)
class FlowPlan:
    phase: Phase
    profile: SearchProfile | None
    catalog_path: str | None
    candidate_ids: list[str]
    property_ref: str = ""
    row_count: int = 0

    @property
    def kind(self) -> Phase:
        return self.phase

    @property
    def catalog_path_used(self) -> str | None:
        return self.catalog_path

    def __init__(
        self,
        *,
        phase: Phase | None = None,
        kind: Phase | None = None,
        profile: SearchProfile | None,
        catalog_path: str | None = None,
        catalog_path_used: str | None = None,
        candidate_ids: list[str] | None = None,
        property_ref: str = "",
        row_count: int = 0,
    ) -> None:
        self.phase = phase or kind or Phase.GENERAL
        self.profile = profile
        self.catalog_path = catalog_path or catalog_path_used
        self.candidate_ids = list(candidate_ids or [])
        self.property_ref = property_ref
        self.row_count = row_count


@dataclass
class FlowResult:
    text: str
    phase: str
    plan: FlowPlan
    capture_data: dict[str, Any]
    alerts: list[str]
    property_ref: str
    catalog_path: str | None
    candidate_ids: list[str]
    bot_paused: bool = False


def _listing_index(text: str) -> int | None:
    body = (text or "").strip()
    if not body:
        return None
    m = _OPTION_INDEX_RE.search(body)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    m = re.search(r"\bla\s+(\d+)\b", body, re.I)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    m = _ORDINAL_RE.search(body)
    if m:
        return _ORDINAL_INDEX.get(m.group(1).lower())
    return None


def _wants_visit(flow_path: str, text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if conversation_requests_human(t):
        return True
    if flow_path == "alquiler":
        return conversation_wants_visit_rent(t)
    return conversation_wants_visit(t)


def _is_detail_pick(text: str) -> bool:
    """Elección de opción o más fotos (no preguntas sobre características)."""
    t = (text or "").strip()
    if not t or user_requests_fresh_listing(t):
        return False
    if user_requests_more_photos(t) or user_showed_property_selection(t):
        return True
    idx = _listing_index(t)
    if idx is None:
        return False
    if _QUESTION_ON_LISTING_RE.search(t):
        return False
    return True


def decide_phase(
    flow_path: str,
    *,
    profile: SearchProfile | None,
    user_text: str,
    capture_data: dict[str, Any] | None,
    catalog_path: str | None,
) -> Phase:
    path = (flow_path or "nuevo").strip().lower()
    if path == "captacion":
        return Phase.CAPTACION
    if path == "nuevo":
        return Phase.TRIAGE
    if path not in ("compra", "alquiler"):
        return Phase.GENERAL

    if profile is None or not profile.is_complete:
        return Phase.INTAKE

    if user_requests_fresh_listing(user_text) or not listing_already_shown(
        catalog_csv_path=catalog_path,
        capture_data=capture_data,
    ):
        return Phase.LISTING

    if _wants_visit(path, user_text):
        return Phase.GENERAL

    if _is_detail_pick(user_text):
        return Phase.DETAIL

    return Phase.GENERAL


def plan_message(ctx: FlowContext, user_text: str) -> FlowPlan:
    flow_path = ctx.flow_path
    capture = ctx.capture_data
    profile: SearchProfile | None = None
    catalog_path: str | None = None
    candidate_ids: list[str] = []

    if flow_path in ("compra", "alquiler"):
        profile = build_search_profile(capture, user_text, flow_path)
        _n, _b, catalog_path = get_catalog_for_flow(
            flow_path,
            ctx.catalog_sale_path,
            ctx.catalog_rent_path,
        )
        if profile.is_complete and catalog_path:
            rows = load_properties_for_catalog_path(catalog_path)
            candidate_ids, _ = select_listing_candidates(
                rows,
                profile.criteria_blob(),
                branch=flow_path,
            )

    phase = decide_phase(
        flow_path,
        profile=profile,
        user_text=user_text,
        capture_data=capture,
        catalog_path=catalog_path,
    )

    property_ref = extract_property_ref(
        "",
        flow_path=flow_path,
        catalog_sale_path=ctx.catalog_sale_path,
        catalog_rent_path=ctx.catalog_rent_path,
        current_user_text=user_text,
    )

    return FlowPlan(
        phase=phase,
        profile=profile,
        catalog_path=catalog_path,
        candidate_ids=candidate_ids,
        property_ref=property_ref,
    )


def _build_listing_text(plan: FlowPlan) -> str:
    if not plan.candidate_ids:
        return _LISTING_EMPTY
    tag = f"[LISTADO:{','.join(plan.candidate_ids)}]"
    return f"{_LISTING_INTRO}\n\n{tag}\n\n{_LISTING_CLOSING}"


def build_detail_outbound(user_text: str, *, listing_rows: list) -> str:
    """Texto introductorio antes de enviar ficha/detalle (tests y delivery)."""
    return _detail_intro(user_text, listing_rows)


def _detail_intro(user_text: str, listing_rows: list) -> str:
    row = resolve_listing_choice_row(user_text, listing_rows)
    titulo = str(row.get("Titulo", "")).strip() if row else ""
    if user_requests_more_photos(user_text):
        return (
            f"Te comparto más fotos y el detalle de *{titulo}* 👇"
            if titulo
            else "Te comparto más fotos y el detalle de esa opción 👇"
        )
    if titulo:
        return f"¡Excelente elección! Te paso la ficha de *{titulo}* 👇"
    return "¡Excelente elección! Te paso la ficha con todos los detalles 👇"


async def _chat_reply(ctx: FlowContext, user_text: str, plan: FlowPlan) -> str:
    catalog_block = ""
    if plan.catalog_path:
        rows = load_last_listing_rows(plan.catalog_path, ctx.capture_data)
        if rows:
            branch = plan.profile.branch if plan.profile else ctx.flow_path
            catalog_block = build_listing_catalog_block(rows, branch=branch)
    if not catalog_block and ctx.flow_path == "captacion":
        catalog_block = "(No aplica catálogo de búsqueda.)"

    system = build_chat_system_prompt(
        tenant_name=ctx.tenant_name,
        flow_path=ctx.flow_path,
        catalog_block=catalog_block,
        system_prompt_override=ctx.system_prompt_override,
    )
    messages = build_model_messages(system, user_text)
    return await chat_completion(messages, max_tokens=_CHAT_MAX_TOKENS)


async def build_reply(ctx: FlowContext, user_text: str, plan: FlowPlan) -> str:
    if plan.phase == Phase.TRIAGE:
        return build_triage_message(ctx.tenant_name)

    if plan.phase == Phase.INTAKE and plan.profile:
        q = plan.profile.next_question()
        return q or "Contame qué buscás y te ayudo."

    if plan.phase == Phase.LISTING:
        return _build_listing_text(plan)

    if plan.phase == Phase.DETAIL:
        rows = load_last_listing_rows(plan.catalog_path, ctx.capture_data)
        return _detail_intro(user_text, rows)

    if plan.phase == Phase.GENERAL and _wants_visit(ctx.flow_path, user_text):
        return format_visit_handoff(plan.property_ref)

    return await _chat_reply(ctx, user_text, plan)


async def handle_turn(
    *,
    tenant_name: str,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    system_prompt_override: str | None,
    capture_data: dict[str, Any],
    user_text: str,
    session_flow_path: str,
) -> FlowResult:
    """Un turno completo: plan → texto → capture → alertas."""
    ctx = FlowContext(
        tenant_name=tenant_name,
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        system_prompt_override=system_prompt_override,
        capture_data=dict(capture_data),
    )
    plan = plan_message(ctx, user_text)
    text = await build_reply(ctx, user_text, plan)

    out_capture = dict(capture_data)
    if plan.profile and flow_path in ("compra", "alquiler"):
        out_capture = merge_search_profile_into_capture(out_capture, plan.profile)

    if plan.phase == Phase.LISTING and plan.candidate_ids:
        out_capture = merge_last_listing_into_capture(
            out_capture,
            property_ids=plan.candidate_ids,
            branch=flow_path,
            catalog_path=plan.catalog_path,
        )
    elif plan.phase == Phase.LISTING and user_requests_fresh_listing(user_text):
        out_capture.pop("last_listing", None)

    property_ref = plan.property_ref
    rows = load_last_listing_rows(plan.catalog_path, out_capture)
    if plan.phase == Phase.DETAIL and rows:
        ref = property_ref_from_listing_choice(user_text, rows)
        if ref.strip():
            property_ref = ref.strip()

    alerts: list[str] = []
    bot_paused = False

    if flow_path == "captacion":
        cap = dict(out_capture)
        from app.session_state import SessionState

        cap = merge_capture_from_conversation(
            SessionState(flow_path="captacion", capture_data=cap),
            user_text,
        )
        out_capture = cap
        if capture_is_complete(cap):
            alerts.append("ALERTA_CAPTACION_PROPIETARIO")
            text = CLOSING_CAPTACION_TEXT
            bot_paused = True

    if flow_path == "compra" and _wants_visit(flow_path, user_text):
        alerts.append("ALERTA_VENTA")
        text = format_visit_handoff(property_ref)

    if flow_path == "alquiler" and _wants_visit(flow_path, user_text):
        alerts.append("ALERTA_ALQUILER")
        text = format_visit_handoff(property_ref)

    out_capture = append_user_flow_message(out_capture, flow_path, user_text)

    return FlowResult(
        text=text.strip(),
        phase=plan.phase.value,
        plan=plan,
        capture_data=out_capture,
        alerts=alerts,
        property_ref=property_ref,
        catalog_path=plan.catalog_path,
        candidate_ids=plan.candidate_ids,
        bot_paused=bot_paused,
    )
