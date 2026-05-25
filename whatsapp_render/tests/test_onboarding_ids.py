from __future__ import annotations

import os
from unittest.mock import patch

from app.onboarding.ids import is_invalid_waba_id, normalize_waba_id


def test_is_invalid_waba_id_matches_app_id() -> None:
    with patch.dict(os.environ, {"META_APP_ID": "1372844231335665"}, clear=False):
        assert is_invalid_waba_id("1372844231335665")
        assert not is_invalid_waba_id("2397672964053788")


def test_normalize_waba_id_strips_invalid() -> None:
    with patch.dict(os.environ, {"META_APP_ID": "999"}, clear=False):
        assert normalize_waba_id("999") == ""
        assert normalize_waba_id(" 888 ") == "888"
