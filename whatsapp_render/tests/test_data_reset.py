from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_reset_chat_data_requires_database() -> None:
    with patch("app.main.get_engine", return_value=None):
        client = TestClient(app)
        res = client.get("/reset-chat-data")
    assert res.status_code == 503


def test_reset_chat_data_public_get() -> None:
    deleted = {
        "chat_messages": 10,
        "chat_sessions": 3,
        "client_leads": 2,
        "client_waitlist": 1,
    }
    with (
        patch("app.main.get_engine", return_value=MagicMock()),
        patch(
            "app.main.clear_operational_chat_tables",
            return_value=deleted,
        ),
    ):
        client = TestClient(app)
        res = client.get("/reset-chat-data")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["deleted"] == deleted
