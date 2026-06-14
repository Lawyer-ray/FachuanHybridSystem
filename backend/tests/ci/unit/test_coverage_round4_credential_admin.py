"""Coverage round 4: account_credential_admin_service.py."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from django.utils import timezone

from apps.organization.services.credential.account_credential_admin_service import (
    AccountCredentialAdminService,
    BatchLoginResult,
    LoginResult,
)


def _make_service():
    svc = AccountCredentialAdminService.__new__(AccountCredentialAdminService)
    svc._token_service = None
    svc._automation_service = None
    svc._credential_service = None
    return svc


def _make_credential(**kwargs):
    cred = MagicMock()
    cred.id = kwargs.get("id", 1)
    cred.site_name = kwargs.get("site_name", "court_zxfw")
    cred.account = kwargs.get("account", "test_user")
    return cred


class TestLoginResult:
    def test_success_result(self):
        r = LoginResult(success=True, duration=1.5, token="abc123")
        assert r.success is True
        assert r.duration == 1.5
        assert r.token == "abc123"
        assert r.error_message is None

    def test_failure_result(self):
        r = LoginResult(success=False, duration=0.5, error_message="fail")
        assert r.success is False
        assert r.error_message == "fail"


class TestBatchLoginResult:
    def test_fields(self):
        r = BatchLoginResult(success_count=2, error_count=1, total_duration=3.0, message="msg")
        assert r.success_count == 2
        assert r.error_count == 1


class TestSingleAutoLogin:
    def test_unsupported_site(self):
        svc = _make_service()
        cred = _make_credential(site_name="other_site")
        svc._credential_service = MagicMock()
        svc._credential_service.get_credential_by_id.return_value = cred
        result = svc.single_auto_login(1, "admin")
        assert result.success is False
        assert "不支持" in result.error_message


class TestExecuteSingleLoginSuccess:
    def test_success_path(self):
        svc = _make_service()
        cred = _make_credential()
        svc._token_service = MagicMock()
        svc._automation_service = MagicMock()
        svc._credential_service = MagicMock()
        with patch("apps.organization.services.credential.account_credential_admin_service._run_async", return_value="token_abc"):
            result = svc._execute_single_login(cred, "admin", "manual_trigger_admin")
        assert result.success is True
        assert result.token == "token_abc"
        svc._credential_service.update_login_success.assert_called_once_with(1)

    def test_failure_no_token(self):
        svc = _make_service()
        cred = _make_credential()
        svc._token_service = MagicMock()
        svc._automation_service = MagicMock()
        svc._credential_service = MagicMock()
        with patch("apps.organization.services.credential.account_credential_admin_service._run_async", return_value=None):
            result = svc._execute_single_login(cred, "admin", "manual_trigger_admin")
        assert result.success is False
        assert "未返回Token" in result.error_message
        svc._credential_service.update_login_failure.assert_called_once_with(1)

    def test_exception_path(self):
        svc = _make_service()
        cred = _make_credential()
        svc._token_service = MagicMock()
        svc._automation_service = MagicMock()
        svc._credential_service = MagicMock()
        with patch("apps.organization.services.credential.account_credential_admin_service._run_async", side_effect=RuntimeError("network fail")):
            result = svc._execute_single_login(cred, "admin", "manual_trigger_admin")
        assert result.success is False
        assert "network fail" in result.error_message
        svc._credential_service.update_login_failure.assert_called_once_with(1)


class TestBatchAutoLogin:
    def test_empty_credentials(self):
        svc = _make_service()
        svc._credential_service = MagicMock()
        svc._credential_service.filter_by_ids_and_site.return_value = []
        result = svc.batch_auto_login([1, 2], "admin")
        assert result.success_count == 0
        assert "没有找到" in result.message

    def test_mixed_results(self):
        svc = _make_service()
        c1 = _make_credential(id=1)
        c2 = _make_credential(id=2)
        svc._credential_service = MagicMock()
        svc._credential_service.filter_by_ids_and_site.return_value = [c1, c2]
        svc._automation_service = MagicMock()
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LoginResult(success=True, duration=1.0, token="tok")
            return LoginResult(success=False, duration=0.5, error_message="fail")

        svc._execute_single_login = MagicMock(side_effect=side_effect)
        result = svc.batch_auto_login([1, 2], "admin")
        assert result.success_count == 1
        assert result.error_count == 1
        assert result.total_duration == 1.5


class TestRecordLoginHistory:
    def test_success_recording(self):
        svc = _make_service()
        svc._automation_service = MagicMock()
        cred = _make_credential()
        start = timezone.now()
        end = timezone.now()
        svc._record_login_history(
            credential=cred, success=True, duration=1.0,
            trigger_reason="test", start_time=start, end_time=end, token="abcdef12345"
        )
        svc._automation_service.create_token_acquisition_history_internal.assert_called_once()

    def test_failure_recording(self):
        svc = _make_service()
        svc._automation_service = MagicMock()
        cred = _make_credential()
        start = timezone.now()
        end = timezone.now()
        svc._record_login_history(
            credential=cred, success=False, duration=1.0,
            trigger_reason="test", start_time=start, end_time=end, error_message="timeout"
        )
        svc._automation_service.create_token_acquisition_history_internal.assert_called_once()

    def test_recording_exception_swallowed(self):
        svc = _make_service()
        svc._automation_service = MagicMock()
        svc._automation_service.create_token_acquisition_history_internal.side_effect = RuntimeError("db err")
        cred = _make_credential()
        start = timezone.now()
        end = timezone.now()
        # Should not raise
        svc._record_login_history(
            credential=cred, success=True, duration=1.0,
            trigger_reason="test", start_time=start, end_time=end, token="tok"
        )


class TestCredentialServiceProperty:
    def test_lazy_load(self):
        svc = _make_service()
        with patch("apps.organization.services.credential.account_credential_service.AccountCredentialService") as MockCS:
            mock_cs = MagicMock()
            MockCS.return_value = mock_cs
            assert svc.credential_service is mock_cs
            # Cached
            assert svc.credential_service is mock_cs


class TestTokenServiceProperty:
    def test_lazy_load(self):
        svc = _make_service()
        with patch("apps.core.dependencies.build_auto_token_acquisition_service") as mock_b:
            mock_ts = MagicMock()
            mock_b.return_value = mock_ts
            assert svc.token_service is mock_ts
            assert svc.token_service is mock_ts


class TestAutomationServiceProperty:
    def test_lazy_load(self):
        svc = _make_service()
        with patch("apps.core.interfaces.ServiceLocator") as MockSL:
            mock_as = MagicMock()
            MockSL.get_automation_service.return_value = mock_as
            assert svc.automation_service is mock_as
            assert svc.automation_service is mock_as
