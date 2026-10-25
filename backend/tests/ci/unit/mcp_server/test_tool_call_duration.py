"""``_t`` 工具调用耗时日志(2026-10-25 审计五十一轮)。

此前单工具耗时无处可查:AgentRun 只有 run 级聚合、消息表只有调用时刻、
共享 MCP 日志只有 HTTP 级 ``POST /mcp``——「AI 很慢」排障只能靠猜。
现在每次调用一行 INFO(>30s 升 WARNING);配套 ``mcp_server`` logger
单独配 INFO(root 是 WARNING,不配则 INFO 全吞)。
"""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Any
from unittest import mock

import pytest


def _server_module() -> Any:
    return importlib.import_module("mcp_server.server")


class TestLogToolDuration:
    def test_fast_call_logs_info(self, caplog: pytest.LogCaptureFixture) -> None:
        mod = _server_module()

        with caplog.at_level("INFO", logger="mcp_server.server"):
            mod._log_tool_duration("fast_tool", time.monotonic() - 0.001)

        assert any("fast_tool" in r.message and r.levelname == "INFO" for r in caplog.records)

    def test_slow_call_escalates_to_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        mod = _server_module()

        elapsed_s = mod._SLOW_TOOL_MS / 1000 + 1
        with caplog.at_level("INFO", logger="mcp_server.server"):
            mod._log_tool_duration("slow_tool", time.monotonic() - elapsed_s)

        assert any("SLOW" in r.message and r.levelname == "WARNING" for r in caplog.records)


class TestTimedWrapper:
    """``_t`` 包裹层记耗时不破坏既有契约(返回值透传/ValueError 翻译)。"""

    @staticmethod
    def _wrap(func: Any) -> Any:
        """在**不污染**注册表的前提下拿到 _t 的包裹函数(mcp.tool 打桩)。"""
        mod = _server_module()
        with mock.patch.object(mod.mcp, "tool", return_value=lambda f: f):
            return mod._t(func)

    @pytest.mark.asyncio
    async def test_async_tool_passes_through_and_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        async def fake_async_tool(x: int) -> int:
            return x * 2

        wrapped = self._wrap(fake_async_tool)

        with caplog.at_level("INFO", logger="mcp_server.server"):
            result = await wrapped(21)

        assert result == 42
        assert any("fake_async_tool" in r.message for r in caplog.records)

    def test_sync_tool_passes_through_and_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        def fake_sync_tool() -> str:
            return "ok"

        wrapped = self._wrap(fake_sync_tool)

        with caplog.at_level("INFO", logger="mcp_server.server"):
            result = wrapped()

        assert result == "ok"
        assert any("fake_sync_tool" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_valueerror_translation_untouched(self, caplog: pytest.LogCaptureFixture) -> None:
        """既有契约回归守卫:ValueError 仍翻译成 FachuanApiError(ToolError 子类)。"""
        mod = _server_module()

        async def picky_tool() -> None:
            raise ValueError("case_id/contract_id 至多传一个")

        wrapped = self._wrap(picky_tool)

        with caplog.at_level("INFO", logger="mcp_server.server"):
            with pytest.raises(mod.FachuanApiError, match="至多传一个"):
                await wrapped()

        # 失败调用同样留耗时记录
        assert any("picky_tool" in r.message for r in caplog.records)


class TestLoggingConfigEntry:
    def test_mcp_server_logger_configured_at_info(self) -> None:
        """root 是 WARNING——mcp_server 若无独立条目,工具耗时 INFO 会被整层吞掉。"""
        logging_mod = importlib.import_module("apps.core.infrastructure.logging")

        with mock.patch.object(logging_mod, "_safe_get_config", lambda key, default=None: default):
            config = logging_mod.get_logging_config(Path("/tmp"), debug=False)

        entry = config["loggers"]["mcp_server"]
        assert entry["level"] == "INFO"
        assert entry["propagate"] is False
        assert "console" in entry["handlers"]
