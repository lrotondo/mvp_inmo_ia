from pathlib import Path

from app.catalog import load_properties_for_catalog_path
from app.catalog_search import select_listing_candidates
from app.capture_flow import append_user_flow_message
from app.search_profile import build_search_profile
from app.turn_handler import TurnContext, plan_turn, resolve_turn_kind, TurnKind

_RENT_CSV = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "tenants"
    / "inmobiliaria_cowork_alquiler.csv"
)


def test_listing_kind_when_profile_complete() -> None:
    capture = append_user_flow_message(
        {},
        "alquiler",
        "alquiler casa 2 dormitorios sin preferencia de zona",
    )
    profile = build_search_profile(capture, "mostrame opciones", "alquiler")
    assert profile.is_complete
    kind = resolve_turn_kind(
        "alquiler",
        profile=profile,
        current_user_text="mostrame opciones",
        capture_data=capture,
    )
    assert kind == TurnKind.LISTING


def test_alquiler_casa_candidates_real_ids() -> None:
    rows = load_properties_for_catalog_path(str(_RENT_CSV))
    blob = "casa 2 dormitorios sin preferencia de zona"
    ids, _ = select_listing_candidates(
        rows,
        blob,
        branch="alquiler",
    )
    assert ids
    assert all(i in {"5", "8", "1", "2", "3", "4", "6", "7"} for i in ids)
    assert "villa urquiza" not in " ".join(ids).lower()


def test_plan_turn_listing_has_candidates() -> None:
    ctx = TurnContext(
        tenant_name="Test",
        flow_path="alquiler",
        catalog_sale_path=None,
        catalog_rent_path=str(_RENT_CSV),
        capture_data=append_user_flow_message(
            {},
            "alquiler",
            "casa 2 dormitorios sin preferencia de zona",
        ),
    )
    plan = plan_turn(ctx, "ver ideas")
    assert plan.kind == TurnKind.LISTING
    assert plan.candidate_ids
