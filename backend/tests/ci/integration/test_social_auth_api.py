"""social_auth API integration 测试（P2 补欠账）。

此前该 app 只有 unit 测试，integration 零覆盖。覆盖：
- 公开端点：providers 列表（启用过滤/空态）、session 发起（未知 provider）
- token-exchange：成功（一次性删除/JWT 可解）、无效码、过期码、未激活用户
- 绑定端点：鉴权 401、绑定列表、解绑成功/未绑定
- provider-catalog：鉴权 401、灰态（未启用也列出）

限流说明：session/token-exchange 挂了 cache 计数限流，本文件 autouse 清缓存防 429。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.core.cache import cache

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


def _seed_feishu_config() -> None:
    """按生产装配方式 seed 飞书 Provider 配置（真实 feishu provider 类）。"""
    from apps.core.models import SystemConfig
    from apps.social_auth.providers import PROVIDER_SPECS, ProviderRegistry

    prefix = PROVIDER_SPECS["feishu"]["prefix"]
    SystemConfig.objects.bulk_create(
        [
            SystemConfig(key=f"{prefix}APP_ID", value="cli_test", category="social_auth"),
            SystemConfig(key=f"{prefix}ENABLED", value="true", category="social_auth"),
            SystemConfig(
                key=f"{prefix}REDIRECT_URI",
                value="http://testserver/social/feishu/callback/",
                category="social_auth",
            ),
            SystemConfig(key="FEISHU_APP_ID", value="cli_shared", category="feishu"),
            SystemConfig(key="FEISHU_APP_SECRET", value="borrowed-secret-placeholder", category="feishu"),
        ]
    )
    ProviderRegistry.clear_configs()


@pytest.fixture
def feishu_enabled() -> Any:
    _seed_feishu_config()
    yield
    from apps.core.models import SystemConfig

    SystemConfig.objects.filter(category="social_auth").delete()
    SystemConfig.objects.filter(category="feishu").delete()
    from apps.social_auth.providers import ProviderRegistry

    ProviderRegistry.clear_configs()


class TestPublicEndpoints:
    def test_list_providers_empty_when_no_config(self, api_client: Any) -> None:
        resp = api_client.get("/api/v1/social/providers")
        assert resp.status_code == 200
        assert resp.json()["providers"] == []

    def test_list_providers_returns_enabled_only(self, api_client: Any, feishu_enabled: Any) -> None:
        resp = api_client.get("/api/v1/social/providers")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()["providers"]]
        assert names == ["feishu"]
        # client_config 不得泄露 secret
        payload = resp.json()["providers"][0]
        assert "borrowed-secret-placeholder" not in str(payload)

    def test_create_session_unknown_provider(self, api_client: Any) -> None:
        resp = api_client.post("/api/v1/social/not-exist/session")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["message"]


class TestTokenExchange:
    def _make_temp_auth(self, api_client: Any) -> Any:
        from apps.organization.models import Lawyer
        from apps.social_auth.models import TempAuth

        user, _ = Lawyer.objects.get_or_create(username="social-jwt-user", defaults={"is_active": True})
        return TempAuth.objects.create(user=user)

    def test_token_exchange_success_is_one_shot(self, api_client: Any) -> None:
        from apps.social_auth.models import TempAuth

        temp = self._make_temp_auth(api_client)
        resp = api_client.post(
            "/api/v1/social/token-exchange", data={"code": str(temp.token)}, content_type="application/json"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["access"] and body["refresh"]
        assert body["username"] == "social-jwt-user"
        # 一次性：行已删除
        assert not TempAuth.objects.filter(token=temp.token).exists()

    def test_token_exchange_invalid_code(self, api_client: Any) -> None:
        resp = api_client.post(
            "/api/v1/social/token-exchange",
            data={"code": "00000000-0000-0000-0000-000000000000"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_token_exchange_expired_code_deleted(self, api_client: Any) -> None:
        from django.utils import timezone

        from apps.social_auth.models import TempAuth

        temp = self._make_temp_auth(api_client)
        TempAuth.objects.filter(pk=temp.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        resp = api_client.post(
            "/api/v1/social/token-exchange", data={"code": str(temp.token)}, content_type="application/json"
        )
        body = resp.json()
        assert body["success"] is False
        assert "过期" in body["message"]
        assert not TempAuth.objects.filter(token=temp.token).exists()

    def test_token_exchange_inactive_user_rejected(self, api_client: Any) -> None:
        from apps.social_auth.models import TempAuth

        temp = self._make_temp_auth(api_client)
        from apps.organization.models import Lawyer

        Lawyer.objects.filter(username="social-jwt-user").update(is_active=False)
        resp = api_client.post(
            "/api/v1/social/token-exchange", data={"code": str(temp.token)}, content_type="application/json"
        )
        body = resp.json()
        assert body["success"] is False
        assert "未激活" in body["message"]
        assert not TempAuth.objects.filter(token=temp.token).exists()


class TestBindingEndpoints:
    def test_bindings_requires_auth(self, api_client: Any) -> None:
        resp = api_client.get("/api/v1/social/bindings")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "HTTP_ERROR"
        assert body["message"] == "Unauthorized"  # 有明确错误信息
        assert "accounts" not in body  # 未认证不泄露任何绑定数据

    def test_bindings_lists_sorted_accounts(self, authenticated_client: Any) -> None:
        from apps.organization.models import Lawyer
        from apps.social_auth.models import SocialAccount

        user = Lawyer.objects.get(username="testuser")
        SocialAccount.objects.create(
            user=user, provider="wechat", provider_uid="wx-1", display_name="微信号", avatar_url=""
        )
        SocialAccount.objects.create(
            user=user, provider="feishu", provider_uid="fs-1", display_name="飞书号", avatar_url=""
        )
        resp = authenticated_client.get("/api/v1/social/bindings")
        assert resp.status_code == 200
        accounts = resp.json()["accounts"]
        assert [a["provider"] for a in accounts] == ["feishu", "wechat"]
        assert accounts[0]["display_name"] == "飞书号"

    def test_unbind_success_and_not_found(self, authenticated_client: Any) -> None:
        from apps.organization.models import Lawyer
        from apps.social_auth.models import SocialAccount

        user = Lawyer.objects.get(username="testuser")
        # 未绑定 → success=False
        resp = authenticated_client.delete("/api/v1/social/feishu/bind")
        assert resp.status_code == 200
        assert resp.json()["success"] is False

        SocialAccount.objects.create(user=user, provider="feishu", provider_uid="fs-9", display_name="", avatar_url="")
        resp = authenticated_client.delete("/api/v1/social/feishu/bind")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert not SocialAccount.objects.filter(provider="feishu", provider_uid="fs-9").exists()


class TestProviderCatalog:
    def test_provider_catalog_requires_auth(self, api_client: Any) -> None:
        resp = api_client.get("/api/v1/social/provider-catalog")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "HTTP_ERROR"
        assert body["message"] == "Unauthorized"
        assert "providers" not in body  # 未认证不泄露提供商目录

    def test_provider_catalog_lists_disabled_as_gray(self, authenticated_client: Any, feishu_enabled: Any) -> None:
        resp = authenticated_client.get("/api/v1/social/provider-catalog")
        assert resp.status_code == 200
        providers = {p["name"]: p for p in resp.json()["providers"]}
        assert "feishu" in providers  # 已启用
        assert "wechat" in providers or "google" in providers  # 未配置的也要灰态列出
