from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from apps.automation.api.main_api import get_config
from apps.core.exceptions import PermissionDenied


@dataclass
class _User:
    id: int = 1
    is_authenticated: bool = True
    is_staff: bool = False
    is_superuser: bool = False
    is_admin: bool = False


def _make_request(*, user: _User) -> Mock:
    request = Mock()
    request.user = user
    request.path = "/automation/config"
    request.META = {"REMOTE_ADDR": "127.0.0.1"}
    return request


def _assert_no_sensitive_keys(obj) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert isinstance(k, str)
            lk = k.lower()
            assert "secret" not in lk
            assert "token" not in lk
            assert lk not in {"key", "apikey", "api_key", "access_key", "secret_key"}
            _assert_no_sensitive_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_no_sensitive_keys(v)


def test_automation_config_requires_admin():
    request = _make_request(user=_User(is_authenticated=True))
    with pytest.raises(PermissionDenied):
        get_config(request)


def test_automation_config_returns_sanitized_config():
    request = _make_request(user=_User(is_authenticated=True, is_staff=True))
    data = get_config(request)

    assert set(data.keys()) == {"document_processing", "court_sms", "feishu"}
    assert isinstance(data["document_processing"], dict)
    assert isinstance(data["court_sms"], dict)
    assert isinstance(data["feishu"], dict)

    assert "configured" in data["feishu"]
    assert isinstance(data["feishu"]["configured"], bool)

    _assert_no_sensitive_keys(data)
