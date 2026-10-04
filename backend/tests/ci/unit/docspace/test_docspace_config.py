"""DocSpace 配置读取单元测试。

锁定 config.py 与 SystemConfig 的契约：
- 未配置 / 未激活时返回默认值，is_configured() 为 False；
- portal URL 去尾部斜杠；
- is_secret 配置走 Fernet 加解密透明还原；
- folder_id 自动发现的网络调用、异常兜底与进程级缓存。
"""

from __future__ import annotations

import httpx
import pytest

from apps.docspace import config as docspace_config
from apps.docspace.config import (
    _discover_my_folder_id,
    get_api_token,
    get_portal_url,
    get_root_folder_id,
    is_configured,
)


@pytest.fixture(autouse=True)
def _reset_folder_cache():
    """每个用例前后清空进程级 folder_id 缓存，避免跨用例污染。"""
    docspace_config._discovered_folder_id = None
    yield
    docspace_config._discovered_folder_id = None


def _set_config(key: str, value: str, *, is_secret: bool = False, is_active: bool = True) -> None:
    """写入配置项。测试库可能已被 _system_config_data 种子预置同名 key，用 update_or_create 兜住。"""
    from apps.core.models.system_config import SystemConfig

    SystemConfig.objects.update_or_create(
        key=key,
        defaults={
            "value": value,
            "is_secret": is_secret,
            "is_active": is_active,
            "category": SystemConfig.Category.DOCSPACE,
        },
    )


class TestPortalAndToken:
    @pytest.mark.django_db
    def test_unconfigured_returns_defaults(self) -> None:
        assert get_portal_url() == ""
        assert get_api_token() == ""
        assert is_configured() is False

    @pytest.mark.django_db
    def test_portal_url_trims_trailing_slash(self) -> None:
        _set_config("DOCSPACE_PORTAL_URL", "https://ds.example.com/")
        assert get_portal_url() == "https://ds.example.com"
        assert is_configured() is False  # token 仍缺失

    @pytest.mark.django_db
    def test_both_set_makes_configured(self) -> None:
        _set_config("DOCSPACE_PORTAL_URL", "https://ds.example.com")
        _set_config("DOCSPACE_API_TOKEN", "plain-token")
        assert get_api_token() == "plain-token"
        assert is_configured() is True

    @pytest.mark.django_db
    def test_inactive_config_ignored(self) -> None:
        _set_config("DOCSPACE_PORTAL_URL", "https://ds.example.com", is_active=False)
        assert get_portal_url() == ""
        assert is_configured() is False

    @pytest.mark.django_db
    def test_secret_token_roundtrip(self) -> None:
        from apps.core.security.secret_codec import SecretCodec

        _set_config("DOCSPACE_API_TOKEN", SecretCodec().encrypt("s3cret-token"), is_secret=True)
        assert get_api_token() == "s3cret-token"


class TestFolderDiscovery:
    def test_returns_zero_without_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(docspace_config, "get_portal_url", lambda: "")
        monkeypatch.setattr(docspace_config, "get_api_token", lambda: "tok")
        assert _discover_my_folder_id() == 0

    def test_discovers_from_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(docspace_config, "get_portal_url", lambda: "https://ds.example.com")
        monkeypatch.setattr(docspace_config, "get_api_token", lambda: "tok")

        def fake_get(url: str, **kwargs: object) -> httpx.Response:
            assert url == "https://ds.example.com/api/2.0/files/@my"
            assert kwargs["headers"]["Authorization"] == "Bearer tok"  # type: ignore[index]
            return httpx.Response(200, json={"response": {"current": {"id": 33}}}, request=httpx.Request("GET", url))

        fake_client = type("_FakeHttpClient", (), {"get": staticmethod(fake_get)})()
        monkeypatch.setattr(docspace_config, "get_sync_http_client", lambda: fake_client)
        assert _discover_my_folder_id() == 33

    def test_http_error_returns_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(docspace_config, "get_portal_url", lambda: "https://ds.example.com")
        monkeypatch.setattr(docspace_config, "get_api_token", lambda: "tok")

        def raise_get(url: str, **kwargs: object) -> httpx.Response:
            # 挂上 request 让 raise_for_status 走真实的 5xx 分支
            return httpx.Response(500, request=httpx.Request("GET", url))

        fake_client = type("_FakeHttpClient", (), {"get": staticmethod(raise_get)})()
        monkeypatch.setattr(docspace_config, "get_sync_http_client", lambda: fake_client)
        assert _discover_my_folder_id() == 0

    def test_root_folder_id_cached_per_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = []

        def fake_discover() -> int:
            calls.append(1)
            return 55

        monkeypatch.setattr(docspace_config, "_discover_my_folder_id", fake_discover)
        assert get_root_folder_id() == 55
        assert get_root_folder_id() == 55
        assert len(calls) == 1
