from __future__ import annotations

from app.conversation_flow import _wants_visit
from app.visit_intent import conversation_bare_me_interesa

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
    assert not _wants_visit("alquiler", "me interesa", {})
