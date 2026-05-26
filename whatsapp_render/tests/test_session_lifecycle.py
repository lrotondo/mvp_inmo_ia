from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.session_lifecycle import (
    apply_session_restart,
    get_last_inbound_at,
    had_advisor_handoff,
    is_initial_greeting,
    is_session_idle_over_threshold,
    mark_advisor_handoff_completed,
    should_auto_restart_session,
    touch_last_inbound_at,
)


def test_is_initial_greeting_pure() -> None:
    assert is_initial_greeting("hola")
    assert is_initial_greeting("Buenos días")
    assert is_initial_greeting("hey!")


def test_is_initial_greeting_not_with_intent() -> None:
    assert not is_initial_greeting("hola quiero alquilar")
    assert not is_initial_greeting("quiero comprar")
    assert not is_initial_greeting("la opción 2")


def test_should_restart_after_idle_greeting() -> None:
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=25)
    capture = {"last_inbound_at": last.isoformat()}
    assert should_auto_restart_session(capture, "hola", last, now=now)


def test_should_not_restart_recent_greeting() -> None:
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=2)
    capture = {"last_inbound_at": last.isoformat()}
    assert not should_auto_restart_session(capture, "hola", last, now=now)


def test_should_restart_after_handoff_even_if_recent() -> None:
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(minutes=30)
    capture = mark_advisor_handoff_completed({}, now=now)
    capture = touch_last_inbound_at(capture, last)
    assert had_advisor_handoff(capture)
    assert should_auto_restart_session(capture, "hola", last, now=now)


def test_should_not_restart_idle_without_greeting() -> None:
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=30)
    capture = {"last_inbound_at": last.isoformat()}
    assert not should_auto_restart_session(capture, "la opción 2", last, now=now)


def test_apply_session_restart_clears_state() -> None:
    state = apply_session_restart()
    assert state.flow_path == "nuevo"
    assert state.capture_data == {}
    assert not state.bot_paused


def test_get_last_inbound_at_fallback_to_session_updated() -> None:
    updated = datetime(2026, 5, 20, 8, 0, tzinfo=timezone.utc)
    assert get_last_inbound_at({}, updated) == updated


def test_touch_last_inbound_at_persists() -> None:
    now = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
    capture = touch_last_inbound_at({}, now)
    assert get_last_inbound_at(capture, None) == now


def test_is_session_idle_over_threshold() -> None:
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=25)
    assert is_session_idle_over_threshold(last, now=now, hours=24)
    assert not is_session_idle_over_threshold(
        now - timedelta(hours=10),
        now=now,
        hours=24,
    )
