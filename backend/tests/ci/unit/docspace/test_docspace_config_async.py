"""docspace.config 异步与异常兜底路径测试。

补齐同步测试未覆盖的分支：_get_system_config 异常兜底、
_aget_system_config 四分支（缺省/明文/加密/异常）、aget_portal_url /
aget_api_token、aget_root_folder_id 的缓存与发现、_adiscover_my_folder_id
的未配置/成功/异常三分支（HTTP 一律 mock）。

async 用例的数据准备放在同步 fixture（async 上下文禁 sync ORM）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.docspace import config as docspace_config


@pytest.fixture(autouse=True)
def _reset_folder_cache():
    """每个用例前后清空进程级 folder_id 缓存，避免跨用例污染。"""
    docspace_config._discovered_folder_id = None
    yield
    docspace_config._discovered_folder_id = None


def _set_config(key: str, value: str, *, is_secret: bool = False, is_active: bool = True) -> None:
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


@pytest.fixture
def plain_portal(db: None) -> str:
    """portal 原始值带尾斜杠：_aget 返回原值，aget_portal_url 负责去斜杠。"""
    _set_config("DOCSPACE_PORTAL_URL", "https://async.example.com/")
    return "https://async.example.com/"


@pytest.fixture
def plain_token(db: None) -> str:
    _set_config("DOCSPACE_API_TOKEN", "tok-async")
    return "tok-async"


@pytest.fixture
def encrypted_token(db: None) -> str:
    from apps.core.security.secret_codec import SecretCodec

    _set_config("DOCSPACE_API_TOKEN", SecretCodec().encrypt("secret-token-async"), is_secret=True)
    return "secret-token-async"


@pytest.fixture
def plain_secret(db: None) -> str:
    _set_config("DOCSPACE_API_TOKEN", "plain-secret", is_secret=True)
    return "plain-secret"


class TestSyncGetSystemConfigFallback:
    @pytest.mark.django_db
    def test_orm_failure_returns_default(self) -> None:
        with patch(
            "apps.core.models.system_config.SystemConfig.objects.filter",
            side_effect=RuntimeError("db not ready"),
        ):
            assert docspace_config._get_system_config("DOCSPACE_PORTAL_URL", "fallback") == "fallback"


class TestAsyncGetSystemConfig:
    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_missing_key_returns_default(self) -> None:
        assert await docspace_config._aget_system_config("DOCSPACE_NOPE", "dft") == "dft"

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_plain_value_returned(self, plain_portal: str) -> None:
        assert await docspace_config._aget_system_config("DOCSPACE_PORTAL_URL", "") == plain_portal

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_encrypted_secret_decrypted(self, encrypted_token: str) -> None:
        assert await docspace_config._aget_system_config("DOCSPACE_API_TOKEN", "") == encrypted_token

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_plain_secret_returned_as_is(self, plain_secret: str) -> None:
        assert await docspace_config._aget_system_config("DOCSPACE_API_TOKEN", "") == plain_secret

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_exception_returns_default(self) -> None:
        with patch(
            "apps.core.models.system_config.SystemConfig.objects.filter",
            side_effect=RuntimeError("async db not ready"),
        ):
            assert await docspace_config._aget_system_config("DOCSPACE_PORTAL_URL", "fb") == "fb"


class TestAsyncPortalAndToken:
    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_aget_portal_url_trims_slash(self, plain_portal: str) -> None:
        assert await docspace_config.aget_portal_url() == plain_portal.rstrip("/")

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_aget_api_token(self, plain_token: str) -> None:
        assert await docspace_config.aget_api_token() == plain_token


class TestAsyncRootFolderId:
    @pytest.mark.asyncio
    async def test_cached_value_returned_without_discovery(self) -> None:
        docspace_config._discovered_folder_id = 88
        with patch(
            "apps.docspace.config._adiscover_my_folder_id",
            new=AsyncMock(side_effect=AssertionError("不应触发发现")),
        ):
            assert await docspace_config.aget_root_folder_id() == 88

    @pytest.mark.asyncio
    async def test_discovery_result_cached(self) -> None:
        with patch("apps.docspace.config._adiscover_my_folder_id", new=AsyncMock(return_value=66)):
            assert await docspace_config.aget_root_folder_id() == 66
        assert docspace_config._discovered_folder_id == 66


def _async_client_mock(response: MagicMock | None = None, *, get_side_effect: Exception | None = None) -> MagicMock:
    """构造 httpx.AsyncClient 替身：async with → client.get(...) → response。"""
    instance = MagicMock()
    if get_side_effect is not None:
        instance.get = AsyncMock(side_effect=get_side_effect)
    else:
        instance.get = AsyncMock(return_value=response)
    client_cls = MagicMock()
    client_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
    client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return client_cls


class TestAsyncDiscoverMyFolderId:
    @pytest.mark.asyncio
    async def test_unconfigured_returns_zero(self) -> None:
        with (
            patch("apps.docspace.config.aget_portal_url", new=AsyncMock(return_value="")),
            patch("apps.docspace.config.aget_api_token", new=AsyncMock(return_value="t")),
        ):
            assert await docspace_config._adiscover_my_folder_id() == 0

    @pytest.mark.asyncio
    async def test_http_success_returns_folder_id(self) -> None:
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"response": {"current": {"id": 321}}}
        client_cls = _async_client_mock(response)

        with (
            patch("apps.docspace.config.aget_portal_url", new=AsyncMock(return_value="https://ds.example.com")),
            patch("apps.docspace.config.aget_api_token", new=AsyncMock(return_value="tok")),
            patch("apps.docspace.config.httpx.AsyncClient", client_cls),
        ):
            assert await docspace_config._adiscover_my_folder_id() == 321

        client_cls.assert_called_once_with(timeout=10.0)
        instance = client_cls.return_value.__aenter__.return_value
        instance.get.assert_awaited_once_with(
            "https://ds.example.com/api/2.0/files/@my",
            headers={"Authorization": "Bearer tok"},
        )

    @pytest.mark.asyncio
    async def test_http_error_returns_zero(self) -> None:
        client_cls = _async_client_mock(get_side_effect=RuntimeError("network down"))

        with (
            patch("apps.docspace.config.aget_portal_url", new=AsyncMock(return_value="https://ds.example.com")),
            patch("apps.docspace.config.aget_api_token", new=AsyncMock(return_value="tok")),
            patch("apps.docspace.config.httpx.AsyncClient", client_cls),
        ):
            assert await docspace_config._adiscover_my_folder_id() == 0


class TestSyncDiscoverFallback:
    def test_sync_discover_http_failure_returns_zero(self) -> None:
        with (
            patch("apps.docspace.config.get_portal_url", return_value="https://ds.example.com"),
            patch("apps.docspace.config.get_api_token", return_value="tok"),
            patch(
                "apps.docspace.config.get_sync_http_client",
                side_effect=RuntimeError("client unavailable"),
            ),
        ):
            assert docspace_config._discover_my_folder_id() == 0

    def test_sync_discover_missing_token_returns_zero(self) -> None:
        with (
            patch("apps.docspace.config.get_portal_url", return_value="https://ds.example.com"),
            patch("apps.docspace.config.get_api_token", return_value=""),
        ):
            assert docspace_config._discover_my_folder_id() == 0
