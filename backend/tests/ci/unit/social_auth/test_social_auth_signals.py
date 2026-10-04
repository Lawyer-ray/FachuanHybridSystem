"""社交登录配置变更 → Provider 配置缓存失效（信号）。

配置独立成 ``SocialAuthProvider`` 表后有两个监听对象：

1. 本表任何增删改 → 整体失效；
2. ``SystemConfig`` 只关心**被借用的共用凭证键**（飞书扫码登录凭证留空时
   复用 IM 群聊的 ``FEISHU_APP_ID`` / ``FEISHU_APP_SECRET``）。

这段逻辑原先挂在 ``SystemConfigAdmin.save_model`` 里，但它让 core 反向依赖
业务 app ``social_auth``（被结构测试的冻结基线拦下）。改成 social_auth 自己
监听信号后，这里锁住行为不退化。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from apps.core.models import SystemConfig
from apps.social_auth.models import SocialAuthProvider
from apps.social_auth.providers import ProviderConfig, ProviderRegistry


def _config(name: str) -> ProviderConfig:
    return ProviderConfig(name=name, display_name=name, client_id="cid", client_secret="sec")


@pytest.fixture
def cached_providers() -> Iterator[None]:
    """给 feishu / wechat 塞一份假缓存，测完清干净，避免污染其它用例。"""
    ProviderRegistry._configs = {"feishu": _config("feishu"), "wechat": _config("wechat")}
    yield
    ProviderRegistry._configs = {}


def _cached() -> set[str]:
    return set(ProviderRegistry._configs)


def _refill() -> None:
    ProviderRegistry._configs = {"feishu": _config("feishu"), "wechat": _config("wechat")}


@pytest.mark.django_db
class TestProviderRowInvalidation:
    def test_provider_row_save_clears_cache(self, cached_providers: None) -> None:
        """平台配置行保存 → 缓存整体失效。

        刻意**不是**「只清单个平台」：``_configs`` 只装已启用的 Provider，局部清除
        会让该名字从缓存消失，而读取方以「缓存是否为空」判断要不要重建 —— 缓存里
        还有别的平台时就不重建，新启用的 Provider 会长期缺席。回归见
        ``test_social_auth_coverage.py::TestProviderRegistry::test_newly_enabled_provider_appears_after_invalidation``。
        """
        SocialAuthProvider.objects.create(name="github", display_name="GitHub")

        assert _cached() == set()

    def test_provider_row_update_via_save_clears_cache(self, cached_providers: None) -> None:
        provider = SocialAuthProvider.objects.create(name="github", display_name="GitHub")
        _refill()

        provider.enabled = False
        provider.save()

        assert _cached() == set()

    def test_provider_row_delete_clears_cache(self, cached_providers: None) -> None:
        provider = SocialAuthProvider.objects.create(name="wechat", display_name="微信")
        _refill()

        provider.delete()

        assert _cached() == set()


@pytest.mark.django_db
class TestBorrowedCredentialInvalidation:
    def test_borrowed_shared_credential_clears_providers(self, cached_providers: None) -> None:
        """扫码登录复用 IM 群聊的飞书应用凭证，改共用键同样要失效。"""
        SystemConfig.objects.create(key="FEISHU_APP_SECRET", value="s", category="feishu", is_secret=True)

        assert _cached() == set()

    def test_borrowed_credential_delete_clears_cache(self, cached_providers: None) -> None:
        config = SystemConfig.objects.create(key="FEISHU_APP_ID", value="cli_x", category="feishu")
        _refill()

        config.delete()

        assert _cached() == set()

    def test_unrelated_system_config_key_keeps_cache(self, cached_providers: None) -> None:
        """社交登录配置已不在 SystemConfig 里，普通键的增删不再影响缓存。"""
        SystemConfig.objects.create(key="SOME_UNRELATED_KEY", value="v", category="general")

        assert _cached() == {"feishu", "wechat"}
