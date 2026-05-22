import httpx

from app.meta_client import (
    MetaSendError,
    _parse_meta_error_payload,
    _should_retry_meta_send,
)


def _response(status: int, body: dict) -> httpx.Response:
    import json

    return httpx.Response(
        status_code=status,
        json=body,
        request=httpx.Request("POST", "https://graph.facebook.com/v22.0/1/messages"),
    )


def test_parse_transient_oauth_code_2():
    resp = _response(
        400,
        {
            "error": {
                "message": "Service temporarily unavailable",
                "code": 2,
                "is_transient": True,
            }
        },
    )
    transient, code, _ = _parse_meta_error_payload(resp)
    assert transient is True
    assert code == 2
    assert _should_retry_meta_send(resp, attempt=1, max_attempts=4)


def test_no_retry_on_permanent_400():
    resp = _response(
        400,
        {"error": {"message": "Invalid parameter", "code": 100}},
    )
    transient, _, _ = _parse_meta_error_payload(resp)
    assert transient is False
    assert not _should_retry_meta_send(resp, attempt=1, max_attempts=4)


def test_meta_send_error_fields():
    err = MetaSendError(
        message="fail",
        status_code=400,
        error_code=2,
        is_transient=True,
    )
    assert err.is_transient
    assert "fail" in str(err)
