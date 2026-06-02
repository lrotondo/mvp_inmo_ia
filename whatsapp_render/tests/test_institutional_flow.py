from __future__ import annotations

from app.institutional_flow import build_institutional_reply
from app.llm.institutional_classifier import InstitutionalCategory
from app.prompts.templates import (
    build_institutional_missing_data_reply,
)
from app.tenant_service import InstitutionalProfile


def test_build_institutional_reply_hours() -> None:
    profile = InstitutionalProfile(
        office_hours="Lun a Vie 9 a 18",
        office_address="Calle 1",
        social_links="https://instagram.com/x",
    )
    text = build_institutional_reply(InstitutionalCategory.OFFICE_HOURS, profile)
    assert "horarios de atención" in text.lower()
    assert "Lun a Vie 9 a 18" in text


def test_build_institutional_reply_missing_field() -> None:
    profile = InstitutionalProfile(
        office_hours=None,
        office_address=None,
        social_links=None,
    )
    text = build_institutional_reply(InstitutionalCategory.OFFICE_LOCATION, profile)
    assert text == build_institutional_missing_data_reply()
