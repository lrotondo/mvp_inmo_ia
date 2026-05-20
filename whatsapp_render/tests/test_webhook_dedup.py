from __future__ import annotations

from app.webhook_dedup import claim_inbound_message_id


def test_claim_message_id_once() -> None:
    mid = "wamid.test.unique.001"
    assert claim_inbound_message_id(mid) is True
    assert claim_inbound_message_id(mid) is False


def test_empty_message_id_always_claims() -> None:
    assert claim_inbound_message_id("") is True
    assert claim_inbound_message_id("") is True
