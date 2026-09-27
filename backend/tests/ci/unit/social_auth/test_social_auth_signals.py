"""SystemConfig 变更 → 社交登录 Provider 配置缓存失效（信号）。

这段逻辑原先挂在 ``SystemConfigAdmin.save_model`` 里，但它让 core 反向依赖
业务 app ``social_auth``（被结构测试的冻结基线拦下）。改成 social_auth 自己
监听信号后，这里锁住行为不退化：本分类键、被借用的共用凭证、改名、删除。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from apps.core.models import SystemConfig
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
class TestProviderConfigInvalidation:
    def test_social_auth_key_clears_that_provider(self, cached_providers: None) -> None:
        SystemConfig.objects.create(key="SOCIAL_AUTH_FEISHU_APP_ID", value="cli_x", category="social_auth")

        assert "feishu" not in _cached()
        # 其它平台不受影响
        assert "wechat" in _cached()

    def test_borrowed_shared_credential_clears_providers(self, cached_providers: None) -> None:
        """扫码登录复用 IM 群聊的飞书应用凭证，改共用键同样要失效。"""
        SystemConfig.objects.create(key="FEISHU_APP_SECRET", value="s", category="feishu", is_secret=True)

        assert _cached() == set()

    def test_renaming_away_from_prefix_still_clears(self, cached_providers: None) -> None:
        """旧键命中前缀、新键不命中：只看新键会漏掉这次失效。"""
        config = SystemConfig.objects.create(key="SOCIAL_AUTH_FEISHU_ENABLED", value="false", category="social_auth")
        _refill()

        config.key = "SOMETHING_ELSE"
        config.save()

        assert "feishu" not in _cached()

    def test_delete_clears_provider(self, cached_providers: None) -> None:
        config = SystemConfig.objects.create(key="SOCIAL_AUTH_WECHAT_ENABLED", value="true", category="social_auth")
        _refill()

        config.delete()

        assert "wechat" not in _cached()

    def test_unrelated_key_keeps_cache(self, cached_providers: None) -> None:
        SystemConfig.objects.create(key="SOME_UNRELATED_KEY", value="v", category="general")

        assert _cached() == {"feishu", "wechat"}
