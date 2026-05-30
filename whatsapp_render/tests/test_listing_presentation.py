from __future__ import annotations

from app.conversation_flow import FlowPlan, Phase, _build_listing_text
from app.listing_delivery import ensure_listado_from_candidates
from app.prompts.templates import (
    build_listing_closing,
    build_listing_intro,
)
from app.search_profile import SearchProfile

SALE_CSV = "data/tenants/inmobiliaria_cowork_venta.csv"


def test_listing_intro_singular() -> None:
    assert "una opción" in build_listing_intro(option_count=1)
    assert "algunas opciones" not in build_listing_intro(option_count=1)


def test_listing_intro_plural() -> None:
    assert "algunas opciones" in build_listing_intro(option_count=2)
    assert "una opción" not in build_listing_intro(option_count=2)


def test_listing_closing_singular() -> None:
    closing = build_listing_closing(option_count=1)
    assert "¿Te llama la atención" in closing
    assert "Cuál" not in closing


def test_listing_closing_plural() -> None:
    closing = build_listing_closing(option_count=3)
    assert "¿Cuál te llama más la atención" in closing


def test_build_listing_text_single_option_uses_singular() -> None:
    plan = FlowPlan(
        phase=Phase.LISTING,
        profile=SearchProfile(
            branch="alquiler",
            property_type="casa",
            property_types=("casa",),
            intake_complete=True,
        ),
        catalog_path="data/x.csv",
        candidate_ids=["42"],
    )
    text = _build_listing_text(plan)
    assert "una opción que encaja" in text
    assert "algunas opciones" not in text
    assert "¿Te llama la atención" in text
    assert "¿Cuál te llama" not in text
    assert "[LISTADO:42]" in text


def test_build_listing_text_multiple_options_uses_plural() -> None:
    plan = FlowPlan(
        phase=Phase.LISTING,
        profile=SearchProfile(
            branch="alquiler",
            property_type="casa",
            property_types=("casa",),
            intake_complete=True,
        ),
        catalog_path="data/x.csv",
        candidate_ids=["42", "43"],
    )
    text = _build_listing_text(plan)
    assert "algunas opciones que encajan" in text
    assert "¿Cuál te llama más la atención" in text


def test_ensure_listado_default_closing_singular() -> None:
    msg = "¡Perfecto, vamos encaminados!"
    out = ensure_listado_from_candidates(msg, ["9778241"], SALE_CSV)
    assert "[LISTADO:9778241]" in out
    assert "¿Te llama la atención" in out
    assert "Alguna de estas opciones" not in out


def test_ensure_listado_default_closing_plural() -> None:
    msg = "¡Perfecto, vamos encaminados!"
    out = ensure_listado_from_candidates(
        msg,
        ["9778241", "9764933"],
        SALE_CSV,
    )
    assert "Alguna de estas opciones te llama la atención" in out
