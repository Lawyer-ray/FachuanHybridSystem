"""LawVerificationService 单元测试。

覆盖入参校验、凭证不存在（404）、跨律所凭证（403）与成功路径
（mock 私有 API adapter 与 verify_references），异常类型/错误码与
API 时期完全一致。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ExternalServiceError, NotFoundError, PermissionDenied, ValidationException
from apps.legal_research.services.law_verification_service import LawVerificationService, sanitize_weike_login_url


def _user(law_firm_id: int | None = 1) -> SimpleNamespace:
    return SimpleNamespace(is_authenticated=True, is_superuser=False, law_firm_id=law_firm_id)


def _cred(law_firm_id: int | None = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=6,
        account="jtnfalawoa",
        password="cipher",
        url="https://law.wkinfo.com.cn/login",
        lawyer=SimpleNamespace(law_firm_id=law_firm_id),
    )


def _mock_manager(cred: SimpleNamespace) -> MagicMock:
    manager = MagicMock()
    manager.select_related.return_value.get.return_value = cred
    return manager


def test_sanitize_weike_login_url_whitelist() -> None:
    assert sanitize_weike_login_url("https://law.wkinfo.com.cn/login") == "https://law.wkinfo.com.cn/login"
    assert sanitize_weike_login_url("") is None
    assert sanitize_weike_login_url("http://law.wkinfo.com.cn/login") is None  # 非 https
    assert sanitize_weike_login_url("https://evil.example.com/login") is None  # 非白名单域


def test_check_empty_text_rejected() -> None:
    with pytest.raises(ValidationException, match="text 不能为空") as exc_info:
        LawVerificationService().check_references(text="   ", credential_id=6, user=_user())
    assert exc_info.value.code == "TEXT_REQUIRED"


def test_check_credential_not_found() -> None:
    with patch("apps.organization.models.AccountCredential") as mock_cred_model:
        mock_cred_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_cred_model.objects.select_related.return_value.get.side_effect = mock_cred_model.DoesNotExist
        with pytest.raises(NotFoundError) as exc_info:
            LawVerificationService().check_references(text="《民法典》第一百四十三条", credential_id=6, user=_user())
    assert exc_info.value.code == "CREDENTIAL_NOT_FOUND"


def test_check_foreign_firm_credential_forbidden() -> None:
    cred = _cred(law_firm_id=99)  # 凭证属于其他律所
    with patch("apps.organization.models.AccountCredential") as mock_cred_model:
        mock_cred_model.objects = _mock_manager(cred)
        with pytest.raises(PermissionDenied) as exc_info:
            LawVerificationService().check_references(text="《民法典》第一百四十三条", credential_id=6, user=_user(1))
    assert exc_info.value.code == "CREDENTIAL_FORBIDDEN"


def test_check_superuser_bypasses_firm_check() -> None:
    """superuser 可用任意律所凭证（与 LegalResearchTaskService 同口径）。"""
    cred = _cred(law_firm_id=99)
    superuser = SimpleNamespace(is_authenticated=True, is_superuser=True, law_firm_id=None)
    with (
        patch("apps.organization.models.AccountCredential") as mock_cred_model,
        patch("apps.core.security.secret_codec.SecretCodec") as mock_codec_cls,
        patch("plugins.weike_api_private.adapter.PrivateWeikeApiAdapter") as mock_adapter_cls,
        patch("plugins.weike_api_private.law_verification.verify_references") as mock_verify,
    ):
        mock_cred_model.objects = _mock_manager(cred)
        mock_codec_cls.return_value.try_decrypt.return_value = "plain-password"
        mock_adapter_cls.return_value.open_http_session.return_value = MagicMock()
        mock_verify.return_value = [{"law_name": "民法典", "status": "valid"}]

        result = LawVerificationService().check_references(
            text="《民法典》第一百四十三条", credential_id=6, user=superuser
        )

    assert result["total"] == 1
    assert result["references"][0]["law_name"] == "民法典"
    login_kwargs = mock_adapter_cls.return_value.open_http_session.call_args.kwargs
    assert login_kwargs["login_url"] == "https://law.wkinfo.com.cn/login"


def test_check_login_failure_raises_external_service_error() -> None:
    cred = _cred(law_firm_id=1)
    with (
        patch("apps.organization.models.AccountCredential") as mock_cred_model,
        patch("apps.core.security.secret_codec.SecretCodec") as mock_codec_cls,
        patch("plugins.weike_api_private.adapter.PrivateWeikeApiAdapter") as mock_adapter_cls,
    ):
        mock_cred_model.objects = _mock_manager(cred)
        mock_codec_cls.return_value.try_decrypt.return_value = "plain-password"
        mock_adapter_cls.return_value.open_http_session.side_effect = RuntimeError("boom")
        with pytest.raises(ExternalServiceError) as exc_info:
            LawVerificationService().check_references(text="《民法典》第一百四十三条", credential_id=6, user=_user(1))
    assert exc_info.value.code == "WEIKE_LOGIN_FAILED"
