from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.capture_flow import append_user_flow_message, prior_user_messages_for_flow
from app.llm.institutional_classifier import (
    InstitutionalCategory,
    classify_institutional_message,
    institutional_classifier_enabled,
)
from app.listing_context import (
    _listing_index_from_text,
    user_requests_fresh_listing,
    user_requests_more_photos,
    user_showed_property_selection,
    user_wants_alternate_listing,
)
from app.prompts.templates import (
    build_institutional_hours_reply,
    build_institutional_location_reply,
    build_institutional_missing_data_reply,
    build_institutional_social_reply,
)
from app.tenant_service import InstitutionalProfile, fetch_institutional_profile

logger = logging.getLogger(__name__)


def should_skip_institutional_classification(user_text: str) -> bool:
    """Prefiltro: intención clara de propiedad/listado sin llamar al LLM."""
    body = (user_text or "").strip()
    if not body:
        return True
    if _listing_index_from_text(body) is not None:
        return True
    if user_requests_fresh_listing(body):
        return True
    if user_wants_alternate_listing(body):
        return True
    if user_showed_property_selection(body):
        return True
    if user_requests_more_photos(body):
        return True
    return False


def _field_for_category(
    category: InstitutionalCategory,
    profile: InstitutionalProfile,
) -> str | None:
    if category == InstitutionalCategory.OFFICE_HOURS:
        return profile.office_hours
    if category == InstitutionalCategory.OFFICE_LOCATION:
        return profile.office_address
    if category == InstitutionalCategory.SOCIAL_LINKS:
        return profile.social_links
    return None


def build_institutional_reply(
    category: InstitutionalCategory,
    profile: InstitutionalProfile,
) -> str:
    value = _field_for_category(category, profile)
    if not (value or "").strip():
        return build_institutional_missing_data_reply()
    if category == InstitutionalCategory.OFFICE_HOURS:
        return build_institutional_hours_reply(value)
    if category == InstitutionalCategory.OFFICE_LOCATION:
        return build_institutional_location_reply(value)
    if category == InstitutionalCategory.SOCIAL_LINKS:
        return build_institutional_social_reply(value)
    return build_institutional_missing_data_reply()


async def try_handle_institutional_turn(
    *,
    flow_path: str,
    phone_number_id: str,
    user_text: str,
    capture_data: dict[str, Any],
    wa_id: str = "",
) -> tuple[str, dict[str, Any]] | None:
    """
    Si el mensaje es consulta institucional, devuelve (texto, capture actualizado).
    Si no aplica, devuelve None.
    """
    body = (user_text or "").strip()
    if not body or not phone_number_id.strip():
        return None
    if not institutional_classifier_enabled():
        return None
    if should_skip_institutional_classification(body):
        logger.info("institutional_classify skipped_prefilter flow=%s", flow_path)
        return None

    profile = await asyncio.to_thread(fetch_institutional_profile, phone_number_id)
    if profile is None:
        return None

    prior = prior_user_messages_for_flow(body, flow_path, capture_data, max_prior=2)
    recent = "\n".join(f"- {m}" for m in prior) if prior else ""

    category = await classify_institutional_message(
        user_text=body,
        flow_path=flow_path,
        recent_user_messages=recent,
        log_context={"flow_path": flow_path, "wa_id": wa_id},
    )
    logger.info(
        "institutional_classify category=%s flow=%s wa_id=%s",
        category.value,
        flow_path,
        wa_id,
    )
    if category == InstitutionalCategory.NONE:
        return None

    text = build_institutional_reply(category, profile)
    out_capture = append_user_flow_message(dict(capture_data), flow_path, body)
    return text.strip(), out_capture
