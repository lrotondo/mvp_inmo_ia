from __future__ import annotations

from app.conversation_flow import _wants_visit
from app.visit_intent import (
    conversation_bare_me_interesa,
    conversation_requests_viewing,
    conversation_wants_visit,
)

_CAPTURE_WITH_VIEWED = {
    "last_viewed_property": {
        "id": "8",
        "catalog_path": "data/tenants/inmobiliaria_cowork_alquiler.csv",
        "branch": "alquiler",
    },
}


def test_conversation_bare_me_interesa_positive() -> None:
    assert conversation_bare_me_interesa("me interesa")
    assert conversation_bare_me_interesa("Me interesa!")
    assert conversation_bare_me_interesa("me interesa.")


def test_conversation_bare_me_interesa_negative() -> None:
    assert not conversation_bare_me_interesa("")
    assert not conversation_bare_me_interesa("me interesa la opción 2")
    assert not conversation_bare_me_interesa("me interesa la de saavedra")


def test_wants_visit_bare_me_interesa_after_ficha_compra() -> None:
    assert _wants_visit("compra", "me interesa", _CAPTURE_WITH_VIEWED)
    assert not _wants_visit("compra", "me interesa", {})


def test_wants_visit_bare_me_interesa_after_ficha_alquiler() -> None:
    assert _wants_visit("alquiler", "me interesa", _CAPTURE_WITH_VIEWED)


def test_wants_visit_si_without_bot_offer_is_false() -> None:
    assert not _wants_visit("alquiler", "si", _CAPTURE_WITH_VIEWED)
    assert not _wants_visit("alquiler", "me interesa", {})


def test_conversation_requests_viewing_after_interest() -> None:
    assert conversation_requests_viewing("me gusta, se puede ver?")
    assert conversation_requests_viewing("Me gusta! ¿Se puede ver?")
    assert conversation_requests_viewing("¿Cuándo la puedo ver?")
    assert conversation_requests_viewing("quiero conocerla en persona")
    assert not conversation_requests_viewing("me gusta el living")
    assert not conversation_requests_viewing("se puede ver el precio en la web")


def test_wants_visit_me_gusta_se_puede_ver_after_ficha() -> None:
    msg = "me gusta, se puede ver?"
    assert conversation_requests_viewing(msg)
    assert not conversation_wants_visit(msg)
    assert _wants_visit("compra", msg, _CAPTURE_WITH_VIEWED)
    assert _wants_visit("alquiler", msg, _CAPTURE_WITH_VIEWED)
    assert not _wants_visit("alquiler", msg, {})
