"""共享 MCP 把 agent 会话头透传给 REST（写端点兜底的入口 C 依赖它）。

## 为什么锁这个

REST 的写端点靠 `X-Fachuan-Session` 区分「agent 在调」与「律师在页面上点」。
MCP 早先只透传 `Authorization`，于是 agent 的写请求在 REST 侧看起来跟律师手动
操作一模一样——多栏拒写在 REST 层永远不触发，且**没有任何报错**（静默失效）。

四条口径：有会话就带头；会话为空就不带；stdio 服务账号分支同样带头；
HTTP 模式缺 Bearer 仍必须报错（不许因为加了会话头就削弱 2026-10-28 那条升权红线）。
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from mcp_server.client import FachuanApiError, FachuanClient
from mcp_server.identity import request_authorization, request_session_id


@pytest.fixture(autouse=True)
def _reset_contextvars() -> Any:
    """两个 ContextVar 都是进程级状态，测试间必须清干净（否则串到别的文件）。"""
    token = request_authorization.set("")
    session_token = request_session_id.set("")
    try:
        yield
    finally:
        request_authorization.reset(token)
        request_session_id.reset(session_token)


@pytest.fixture
def client() -> FachuanClient:
    c = FachuanClient()
    c._access_token = "service-token"
    c._expires_at = time.time() + 9999
    return c


class TestSessionHeaderPassthrough:
    def test_session_header_rides_along_with_bearer(self, client: FachuanClient) -> None:
        request_authorization.set("Bearer lawyer-token")
        request_session_id.set("sess-abc")

        headers = client._headers()

        assert headers["Authorization"] == "Bearer lawyer-token"
        assert headers["x-fachuan-session"] == "sess-abc"

    def test_empty_session_sends_no_header(self, client: FachuanClient) -> None:
        """stdio / 脚本 / 后台任务没有会话：不带头，REST 侧按律师手动操作放行。"""
        request_authorization.set("Bearer lawyer-token")

        assert client._headers() == {"Authorization": "Bearer lawyer-token"}

    def test_stdio_service_account_branch_also_carries_session(
        self, client: FachuanClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FACHUAN_MCP_TRANSPORT", raising=False)
        request_session_id.set("sess-stdio")

        headers = client._headers()

        assert headers["Authorization"] == "Bearer service-token"
        assert headers["x-fachuan-session"] == "sess-stdio"

    def test_http_mode_without_bearer_still_fails_closed(
        self, client: FachuanClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """会话头不是身份：HTTP 模式没有 Bearer 仍直接报错（不许回退服务账号）。"""
        monkeypatch.setenv("FACHUAN_MCP_TRANSPORT", "streamable-http")
        request_session_id.set("sess-abc")

        with pytest.raises(FachuanApiError, match="共享 MCP 未收到调用方身份"):
            client._headers()
