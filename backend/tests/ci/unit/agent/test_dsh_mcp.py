"""``dsh_mcp`` —— 给 dsh 接法穿 430 个 MCP 业务工具的 patch 层。

只验**不需要 dsh 子进程、不需要真 MCP** 的部分：

1. patch 文本形状：``serverName: fachuan``（审批按全名匹配的硬约束）、
   ``streamable-http``、Authorization 头、``failOnStartupError: true``；
2. token 处理：**不落日志**、文件 ``0600``、无 token 返回 ``None`` 而不是写一份
   注定 401 的配置；
3. 与 ``dsh_config`` 的接线顺序：MCP 层排在内置层之后、``FACHUAN_DSH_PATCHES``
   之前（后写的同 id 条目胜出，部署方要能覆盖它）。

「工具真的被发现」由 ``scripts/verify_dsh_mcp.py``（仓库根）端到端验（真 dsh +
真 MCP 握手），不在本文件——那需要 node runtime 与装好的 mcp-client 插件。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.agent.backends import dsh_mcp
from apps.agent.backends.dsh_config import DSH_HOME_ENV, build_config
from apps.agent.pi.shared_mcp import McpEndpoint

_TOKEN = "tok-abc123"  # pragma: allowlist secret


def _endpoint() -> McpEndpoint:
    return McpEndpoint(host="127.0.0.1", port=8011)


def _provider() -> object:
    class _P:
        base_url = "http://gw.example/v1"
        api_keys = "sk-test"  # pragma: allowlist secret
        default_model = "kimi-2.6"
        extra_models = ""
        api_key_models = ""

    return _P()


class TestPatchBody:
    def test_server_name_is_fachuan(self) -> None:
        """``serverName`` 必须是 fachuan：四级审批按 ``mcp__fachuan__<name>`` 匹配。"""
        body = dsh_mcp.patch_body(_endpoint(), _TOKEN)
        assert f"serverName: {dsh_mcp.SERVER_NAME}" in body
        assert dsh_mcp.SERVER_NAME == "fachuan"

    def test_transport_and_url(self) -> None:
        body = dsh_mcp.patch_body(_endpoint(), _TOKEN)
        assert "transport: streamable-http" in body
        assert '"http://127.0.0.1:8011/mcp"' in body

    def test_authorization_header_holds_the_token(self) -> None:
        body = dsh_mcp.patch_body(_endpoint(), _TOKEN)
        assert f'Authorization: "Bearer {_TOKEN}"' in body

    def test_fail_on_startup_error_is_enabled(self) -> None:
        """默认 false 会把「连不上 / 401」变成静默无工具——必须打开。"""
        assert "failOnStartupError: true" in dsh_mcp.patch_body(_endpoint(), _TOKEN)

    def test_tool_call_timeout_exceeds_server_side(self) -> None:
        """mcp_server 侧文书类工具是 180s，调用方超时必须大于它。"""
        assert dsh_mcp.TOOL_CALL_TIMEOUT_MS > 180_000

    def test_token_special_characters_are_quoted(self) -> None:
        """token 里出现 ``"`` / ``\\`` 时不能破坏 YAML 结构。"""
        body = dsh_mcp.patch_body(_endpoint(), 'a"b\\c')
        assert 'Authorization: "Bearer a\\"b\\\\c"' in body


class TestEnsureMcpPatch:
    @pytest.fixture(autouse=True)
    def _no_real_spawn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """不起真共享 MCP：本文件只验「写文件 + 日志」这条线。"""
        monkeypatch.setattr(dsh_mcp, "ensure_shared_server", lambda *a, **kw: _endpoint())
        monkeypatch.setattr(dsh_mcp, "_port_open", lambda endpoint: True)
        monkeypatch.setattr(dsh_mcp, "_resolve_endpoint", _endpoint)

    def test_returns_none_without_token(self, tmp_path: Path) -> None:
        """无身份不写 patch：写了只会让 dsh 以 401 失败，把「能对话」变成「起不来」。"""
        assert dsh_mcp.ensure_mcp_patch(str(tmp_path), user_token="") is None
        assert not (tmp_path / dsh_mcp.PATCH_FILENAME).exists()

    def test_writes_private_patch_file(self, tmp_path: Path) -> None:
        path = dsh_mcp.ensure_mcp_patch(str(tmp_path), user_token=_TOKEN)
        assert path is not None
        assert Path(path).is_file()
        # 文件里有律师 token，必须是 0600。
        assert oct(os.stat(path).st_mode)[-3:] == "600"
        assert _TOKEN in Path(path).read_text(encoding="utf-8")

    def test_token_never_reaches_logs(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """日志会被收集到你不知道的哪里，token 一律不出现（MEDIUM 审计口径）。"""
        with caplog.at_level("DEBUG"):
            dsh_mcp.ensure_mcp_patch(str(tmp_path), user_token=_TOKEN)
        assert _TOKEN not in caplog.text
        # 但要能据此定位「这轮有没有带 token」：记长度而不是取值。
        assert f"token 长度={len(_TOKEN)}" in caplog.text

    def test_warns_when_token_missing(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING"):
            dsh_mcp.ensure_mcp_patch(str(tmp_path), user_token="")
        assert "无工具但可对话" in caplog.text

    def test_shared_disabled_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """``FACHUAN_MCP_SHARED=0`` 时 dsh 这份 HTTP patch 无意义，如实降级。"""
        monkeypatch.setattr(dsh_mcp, "shared_enabled", lambda: False)
        assert dsh_mcp.ensure_mcp_patch(str(tmp_path), user_token=_TOKEN) is None

    def test_rewrite_is_idempotent(self, tmp_path: Path) -> None:
        """每轮都会重写（token 会变），不能留下 ``.tmp`` 残余文件。"""
        first = dsh_mcp.ensure_mcp_patch(str(tmp_path), user_token=_TOKEN)
        second = dsh_mcp.ensure_mcp_patch(str(tmp_path), user_token="tok-2")  # pragma: allowlist secret
        assert first == second
        assert not list(tmp_path.glob("*.tmp"))


class TestConfigWiring:
    @pytest.fixture(autouse=True)
    def _stub_mcp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dsh_mcp, "ensure_shared_server", lambda *a, **kw: _endpoint())
        monkeypatch.setattr(dsh_mcp, "_port_open", lambda endpoint: True)
        monkeypatch.setattr(dsh_mcp, "_resolve_endpoint", _endpoint)

    def test_mcp_patch_included_when_token_given(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path))
        monkeypatch.delenv("FACHUAN_DSH_PATCHES", raising=False)
        config = build_config(user_id=1, provider=_provider(), user_token=_TOKEN)
        assert config is not None
        names = [Path(path).name for path in config.patches]
        # 顺序有意义：收紧 → 路由 → 工具面（后写的同 id 条目胜出）。
        assert names == ["fachuan-lockdown.patch.yml", "fachuan-provider.patch.yml", dsh_mcp.PATCH_FILENAME]

    def test_mcp_patch_absent_without_token(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path))
        monkeypatch.delenv("FACHUAN_DSH_PATCHES", raising=False)
        config = build_config(user_id=1, provider=_provider(), user_token="")
        assert config is not None
        assert all(Path(path).name != dsh_mcp.PATCH_FILENAME for path in config.patches)

    def test_deployment_patches_come_last(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """部署侧 ``FACHUAN_DSH_PATCHES`` 能覆盖 MCP 层，必须排在它之后。"""
        deployment = tmp_path / "deploy.patch.yml"
        deployment.write_text("[]", encoding="utf-8")
        monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path / "homes"))
        monkeypatch.setenv("FACHUAN_DSH_PATCHES", str(deployment))
        config = build_config(user_id=1, provider=_provider(), user_token=_TOKEN)
        assert config is not None
        names = [Path(path).name for path in config.patches]
        assert names[-1] == "deploy.patch.yml"
        assert names[-2] == dsh_mcp.PATCH_FILENAME
