from __future__ import annotations

from app.capture_flow import append_user_flow_message, prior_user_messages_for_flow
from app.conversation import build_model_messages, build_user_message_for_llm


def test_prior_user_messages_excludes_current() -> None:
    capture = append_user_flow_message({}, "compra", "busco casa")
    capture = append_user_flow_message(capture, "compra", "en centro")
    prior = prior_user_messages_for_flow("esa tiene patio?", "compra", capture)
    assert prior == ["busco casa", "en centro"]


def test_build_user_message_listing_followup_with_history() -> None:
    body = build_user_message_for_llm(
        "esa casa tiene patio?",
        prior_user_messages=["me interesa la opción 1", "mostrame opciones"],
        listing_followup=True,
    )
    assert "listado" in body.lower()
    assert "Mensaje anterior 1" in body
    assert "opción 1" in body.lower()
    assert "Consulta actual" in body
    assert "patio" in body


def test_build_model_messages_single_user_role() -> None:
    messages = build_model_messages(
        "system text",
        "hola",
        prior_user_messages=["antes"],
        listing_followup=True,
    )
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "antes" in messages[1]["content"]
    assert "hola" in messages[1]["content"]
