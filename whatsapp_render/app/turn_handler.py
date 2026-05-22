from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.catalog import get_catalog_for_flow, load_properties_for_catalog_path
from app.catalog_search import select_listing_candidates
from app.conversation import HistoryTurn, build_model_messages
from app.llm.deepseek import chat_completion, chat_short
from app.detail_media import user_wants_specific_property_detail
from app.property_matching import extract_property_ref
from app.prompts.flow_master import build_turn_system_prompt
from app.search_profile import (
    SearchProfile,
    build_search_profile,
    merge_search_profile_into_capture,
)
logger = logging.getLogger(__name__)

_LISTING_INTRO_FALLBACK = (
    "¡Buenísimo! Te comparto algunas opciones del catálogo que encajan con lo que buscás:"
)
_LISTING_CLOSING = "¿Cuál te llama más la atención para pasarte más detalles?"
_LISTING_EMPTY = (
    "Por ahora no tengo opciones en el catálogo que coincidan exactamente con tu búsqueda. "
    "¿Querés ampliar zona, tipo o presupuesto y lo revisamos?"
)


class TurnKind(str, Enum):
    TRIAGE = "triage"
    INTAKE = "intake"
    LISTING = "listing"
    DETAIL = "detail"
    CAPTACION = "captacion"
    GENERAL = "general"


@dataclass
class TurnContext:
    tenant_name: str
    flow_path: str
    catalog_sale_path: str | None
    catalog_rent_path: str | None
    system_prompt_override: str | None = None


@dataclass
class TurnPlan:
    kind: TurnKind
    profile: SearchProfile | None
    catalog_path_used: str | None
    candidate_ids: list[str]
    row_count: int
    property_ref: str = ""


@dataclass
class TurnLLMResult:
    raw_answer: str
    clean_answer: str


def resolve_turn_kind(
    flow_path: str,
    *,
    profile: SearchProfile | None,
    current_user_text: str,
) -> TurnKind:
    path = (flow_path or "nuevo").strip().lower()
    if path == "captacion":
        return TurnKind.CAPTACION
    if path == "nuevo":
        return TurnKind.TRIAGE
    if path in ("compra", "alquiler"):
        if user_wants_specific_property_detail(current_user_text):
            return TurnKind.DETAIL
        if profile and profile.is_complete:
            return TurnKind.LISTING
        return TurnKind.INTAKE
    return TurnKind.GENERAL


def plan_turn(
    ctx: TurnContext,
    history: list[HistoryTurn],
    user_text: str,
) -> TurnPlan:
    flow_path = ctx.flow_path
    profile: SearchProfile | None = None
    candidate_ids: list[str] = []
    catalog_path_used: str | None = None
    row_count = 0

    if flow_path in ("compra", "alquiler"):
        profile = build_search_profile(history, user_text, flow_path)
        _count, _block, catalog_path_used = get_catalog_for_flow(
            flow_path,
            ctx.catalog_sale_path,
            ctx.catalog_rent_path,
        )
        if profile.is_complete and catalog_path_used:
            all_rows = load_properties_for_catalog_path(catalog_path_used)
            candidate_ids, picked = select_listing_candidates(
                all_rows,
                profile.criteria_blob(),
                branch=flow_path,
                catalog_path=catalog_path_used,
            )
            row_count = len(picked)
            logger.info(
                "turn_plan listing flow=%s ids=%s path=%r rows=%s",
                flow_path,
                candidate_ids,
                catalog_path_used,
                row_count,
            )

    kind = resolve_turn_kind(
        flow_path,
        profile=profile,
        current_user_text=user_text,
    )

    property_ref = extract_property_ref(
        "",
        flow_path=flow_path,
        catalog_sale_path=ctx.catalog_sale_path,
        catalog_rent_path=ctx.catalog_rent_path,
        history=history,
        current_user_text=user_text,
        user_only=True,
    )

    return TurnPlan(
        kind=kind,
        profile=profile,
        catalog_path_used=catalog_path_used,
        candidate_ids=candidate_ids,
        row_count=row_count,
        property_ref=property_ref,
    )


async def build_listing_outbound(
    plan: TurnPlan,
    *,
    tenant_name: str,
) -> str:
    ids = plan.candidate_ids
    if not ids:
        return _LISTING_EMPTY

    tag = f"[LISTADO:{','.join(ids)}]"
    system = build_turn_system_prompt(
        tenant_name=tenant_name,
        flow_path=plan.profile.branch if plan.profile else "compra",
        turn_kind=TurnKind.LISTING.value,
        catalog_block="",
    )
    user_hint = (
        "El sistema enviará automáticamente las fotos de las opciones. "
        "Escribí solo 1-2 líneas de intro amable y nada más (sin listar propiedades, "
        "sin precios, sin barrios, sin numeración)."
    )
    intro = await chat_short(system, user_hint)
    if not intro or _looks_like_property_list(intro):
        intro = _LISTING_INTRO_FALLBACK
    return f"{intro.strip()}\n\n{tag}\n\n{_LISTING_CLOSING}"


def build_intake_outbound(profile: SearchProfile) -> str:
    question = profile.next_question()
    if question:
        return question
    return "Contame un poco más de lo que buscás y te ayudo a encontrar opciones."


def _looks_like_property_list(text: str) -> bool:
    import re

    from app.listing_delivery import _line_looks_invented_property

    for line in (text or "").splitlines():
        if _line_looks_invented_property(line.strip()):
            return True
    return bool(
        re.search(
            r"\b\d+[\.\)]\s*(?:casa|depto|departamento)\b",
            text or "",
            re.I,
        )
    )


async def generate_turn_reply(
    ctx: TurnContext,
    history: list[HistoryTurn],
    user_text: str,
    plan: TurnPlan,
) -> str:
    if plan.kind == TurnKind.LISTING and plan.profile:
        return await build_listing_outbound(plan, tenant_name=ctx.tenant_name)

    if plan.kind == TurnKind.INTAKE and plan.profile:
        return build_intake_outbound(plan.profile)

    catalog_block = ""
    if plan.kind not in (TurnKind.LISTING, TurnKind.INTAKE):
        if ctx.flow_path == "captacion":
            catalog_block = "(No aplica catálogo.)"
        elif ctx.flow_path == "nuevo":
            catalog_block = "(Catálogo oculto hasta definir compra o alquiler.)"

    system_prompt = build_turn_system_prompt(
        tenant_name=ctx.tenant_name,
        flow_path=ctx.flow_path,
        turn_kind=plan.kind.value,
        catalog_block=catalog_block,
        system_prompt_override=ctx.system_prompt_override,
    )
    messages = build_model_messages(system_prompt, history, user_text)
    return await chat_completion(messages, max_tokens=512)


def session_capture_with_profile(
    session: SessionState,
    profile: SearchProfile | None,
    flow_path: str,
) -> dict[str, Any]:
    if profile is None or flow_path not in ("compra", "alquiler"):
        return dict(session.capture_data)
    return merge_search_profile_into_capture(session.capture_data, profile)
