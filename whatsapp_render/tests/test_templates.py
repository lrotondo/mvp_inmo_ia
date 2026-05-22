from __future__ import annotations

from app.prompts.templates import (
    build_chat_system_prompt,
    build_triage_message,
    format_visit_handoff,
)


def test_build_triage_message() -> None:
    msg = build_triage_message("Espacios360")
    assert "comprar" in msg.lower()
    assert "alquilar" in msg.lower()


def test_build_chat_system_prompt_includes_catalog() -> None:
    prompt = build_chat_system_prompt(
        tenant_name="Test",
        flow_path="alquiler",
        catalog_block="Opción 1: depto centro",
    )
    assert "OPCIONES MOSTRADAS" in prompt
    assert "Opción 1" in prompt
    assert "Prohibido usar [LISTADO:ids]" in prompt
    assert "patio" in prompt.lower()


def test_format_visit_handoff() -> None:
    text = format_visit_handoff("ID 5")
    assert "asesor" in text.lower()
    assert "ID 5" in text
