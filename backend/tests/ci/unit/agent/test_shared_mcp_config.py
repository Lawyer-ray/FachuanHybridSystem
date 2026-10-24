"""shared_mcp exposure 开关测试 —— FACHUAN_MCP_EXPOSURE 灰度 knob 的行为契约。

背景：pi 的工具面 exposure 默认 codemode（工具不声明给模型，模型调不了），
本仓库因此显式写 ``direct``（400 工具全量声明，~60k+ token 常驻上下文）。
``deferred``（内置 tool_search 按需加载）是省上下文的灰度选项，但不能贸然
切默认（OpenAI 兼容网关上延迟加载会丢 prompt cache）。所以做成环境变量：
默认不变，实验时可切。本文件守护三件事：

1. 默认仍是 direct（不误伤现有会话）；
2. 合法值（deferred 等）原样写入两种部署形态（共享 HTTP / stdio 回退）；
3. 非法值告警并回退 direct，而不是把 typo 静默写进配置。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from apps.agent.pi.shared_mcp import EXPOSURE_ENV, resolve_exposure, write_pi_mcp_config


@pytest.fixture(autouse=True)
def _clean_exposure_env(monkeypatch: pytest.MonkeyPatch):
    """每个用例独立控制 exposure 环境变量，互不泄漏。"""
    monkeypatch.delenv(EXPOSURE_ENV, raising=False)
    yield


def _load(tmp_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((tmp_path / "mcp.json").read_text(encoding="utf-8"))
    server: dict[str, Any] = data["mcpServers"]["fachuan"]
    return server


class TestResolveExposure:
    def test_default_is_direct(self) -> None:
        assert resolve_exposure() == "direct"

    @pytest.mark.parametrize("value", ["deferred", "DEFERRED", " Direct "])
    def test_valid_values_normalized(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv(EXPOSURE_ENV, value)
        assert resolve_exposure() == value.strip().lower()

    def test_invalid_value_warns_and_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(EXPOSURE_ENV, "lazy")

        with caplog.at_level(logging.WARNING, logger="apps.agent.pi.shared_mcp"):
            assert resolve_exposure() == "direct"

        assert any(EXPOSURE_ENV in r.message for r in caplog.records), "非法值必须留下 warning，不许静默"


class TestWritePiMcpConfig:
    def test_shared_mode_writes_resolved_exposure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_MCP_SHARED", "1")
        monkeypatch.setenv(EXPOSURE_ENV, "deferred")

        write_pi_mcp_config(tmp_path)

        server = _load(tmp_path)
        assert server["type"] == "streamable-http"
        assert server["exposure"] == "deferred"

    def test_stdio_fallback_also_writes_exposure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """stdio 回退分支曾漏写 exposure → 落回 pi 默认 codemode，工具全废。"""
        monkeypatch.setenv("FACHUAN_MCP_SHARED", "0")

        path = write_pi_mcp_config(tmp_path)

        server = _load(path.parent)
        assert "command" in server
        assert server["exposure"] == "direct"

    def test_default_stays_direct(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_MCP_SHARED", "1")

        write_pi_mcp_config(tmp_path)

        assert _load(tmp_path)["exposure"] == "direct"


class TestMcpTimeout:
    """pi 侧每请求超时必须 > client 侧 LLM 工具的 180s。

    pi 默认 60s 会先掐断（工具侧 180 的努力作废）——mcp.json 必须显式
    写 timeout。双端超时关系见 shared_mcp.write_pi_config 注释。
    """

    def test_shared_mode_writes_timeout_over_180(self, tmp_path, monkeypatch):
        import json

        from apps.agent.pi import shared_mcp

        monkeypatch.setenv("FACHUAN_MCP_SHARED", "1")
        path = shared_mcp.write_pi_config(tmp_path / "cfg")
        cfg = json.loads(path.read_text())
        assert cfg["mcpServers"]["fachuan"]["timeout"] > 180

    def test_stdio_mode_writes_timeout_over_180(self, tmp_path, monkeypatch):
        import json

        from apps.agent.pi import shared_mcp

        monkeypatch.setenv("FACHUAN_MCP_SHARED", "0")
        path = shared_mcp.write_pi_config(tmp_path / "cfg2")
        cfg = json.loads(path.read_text())
        assert cfg["mcpServers"]["fachuan"]["timeout"] > 180
