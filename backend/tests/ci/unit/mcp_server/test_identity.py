"""mcp_server 按请求透传用户身份（confused deputy 修复的 server 侧）。

链路：ASGI 中间件读 Authorization → ContextVar → ``client._headers`` 透传。
重点验证 ContextVar 能跨到工作线程（同步工具经 anyio/asyncio ``to_thread`` 执行）。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest import mock

import httpx
import pytest

with mock.patch.dict(
    "os.environ",
    {
        "FACHUAN_BASE_URL": "http://testserver/api/v1",
        "FACHUAN_USERNAME": "testuser",
        "FACHUAN_PASSWORD": "testpass",  # pragma: allowlist secret
    },
    clear=False,
):
    from mcp_server.client import FachuanClient

from mcp_server.identity import RequestAuthMiddleware, passthrough_authorization, request_authorization


@pytest.fixture(autouse=True)
def _reset_request_authorization() -> Any:
    """ContextVar 是进程级状态，测试间必须清干净，否则会串到 client 测试里。"""
    token = request_authorization.set("")
    yield
    request_authorization.reset(token)


# ===================================================================
# passthrough_authorization 判定
# ===================================================================


class TestPassthroughRule:
    def test_valid_bearer_is_returned_verbatim(self) -> None:
        request_authorization.set("Bearer abc.def.ghi")
        assert passthrough_authorization() == "Bearer abc.def.ghi"

    def test_case_insensitive_scheme(self) -> None:
        request_authorization.set("bearer xyz")
        assert passthrough_authorization() == "bearer xyz"

    @pytest.mark.parametrize("raw", ["", "   ", "Bearer", "Bearer ", "Basic dXNlcjpwYXNz", "Token abc"])
    def test_invalid_or_missing_falls_back(self, raw: str) -> None:
        """空 token（pi 的 ${FACHUAN_USER_TOKEN} 展开为空）与非 Bearer 方案都回退服务账号。"""
        request_authorization.set(raw)
        assert passthrough_authorization() == ""


# ===================================================================
# ASGI 中间件 → ContextVar → 工作线程
# ===================================================================


class TestMiddleware:
    @pytest.mark.asyncio
    async def test_sets_contextvar_and_reaches_worker_thread(self) -> None:
        seen: dict[str, str] = {}

        async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
            seen["in_task"] = passthrough_authorization()
            # 同步工具由 to_thread 执行：context 必须被拷进线程
            seen["in_thread"] = await asyncio.to_thread(passthrough_authorization)

        scope = {
            "type": "http",
            "headers": [(b"content-type", b"application/json"), (b"authorization", b"Bearer user-token")],
        }
        await RequestAuthMiddleware(app)(scope, None, None)

        assert seen == {"in_task": "Bearer user-token", "in_thread": "Bearer user-token"}

    @pytest.mark.asyncio
    async def test_non_http_scope_untouched(self) -> None:
        called: list[str] = []

        async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
            called.append(passthrough_authorization())

        await RequestAuthMiddleware(app)({"type": "lifespan"}, None, None)
        assert called == [""]

    @pytest.mark.asyncio
    async def test_missing_header_leaves_empty(self) -> None:
        async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
            assert passthrough_authorization() == ""

        await RequestAuthMiddleware(app)({"type": "http", "headers": []}, None, None)


# ===================================================================
# client：透传优先，无透传回退服务账号
# ===================================================================


class TestClientPassthrough:
    @pytest.fixture()
    def fc(self) -> FachuanClient:
        c = FachuanClient()
        c._http = mock.MagicMock(spec=httpx.Client)
        c._access_token = "service-token"
        c._expires_at = 10**12  # 远未过期，_ensure_token 不发网络请求
        return c

    def test_prefers_request_identity(self, fc: FachuanClient) -> None:
        request_authorization.set("Bearer lawyer-token")
        assert fc._headers() == {"Authorization": "Bearer lawyer-token"}

    def test_falls_back_to_service_account(self, fc: FachuanClient) -> None:
        assert fc._headers() == {"Authorization": "Bearer service-token"}

    def test_passthrough_skips_service_login(self, fc: FachuanClient) -> None:
        """有律师身份时不应触发服务账号登录/刷新（避免无谓的 token/pair）。"""
        fc._access_token = ""  # 本该触发 _obtain_token
        request_authorization.set("Bearer lawyer-token")
        assert fc._headers() == {"Authorization": "Bearer lawyer-token"}
        fc._http.post.assert_not_called()

    def test_request_methods_carry_passthrough(self, fc: FachuanClient) -> None:
        request_authorization.set("Bearer lawyer-token")
        fc._http.get.return_value = httpx.Response(
            200, json={"ok": True}, request=httpx.Request("GET", "http://testserver/api/v1/x")
        )
        fc.get("/x")
        assert fc._http.get.call_args[1]["headers"] == {"Authorization": "Bearer lawyer-token"}
