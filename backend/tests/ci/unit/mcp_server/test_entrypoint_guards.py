"""``mcp_server.__main__`` 的启动护栏（纯函数级：不起服务、不连 DB、不占长端口）。

这些函数决定的是「共享 MCP 起不起来、切换时会不会把旧实例挂死」，三条都曾经或差点
静默失效：

- ``_graceful_timeout``：默认值比单次工具调用上限（200s）还短时，蓝绿切换会在部署
  瞬间切断正在跑的长工具，看起来像「部署偶发失败」；
- ``_side_port``：非法值不能被当成某个端口的 int，否则候选实例会监听错端口、
  就绪校验永远打不到它；
- ``_probe_conflict``：SO_REUSEPORT 让「第二个实例」不再 `EADDRINUSE` 秒退，而是绑
  成功并分走一半流量（一份进程跑旧代码），这条探针是唯一的 fail-fast。
"""

from __future__ import annotations

import logging
import socket

import pytest

from mcp_server.__main__ import (
    DEFAULT_GRACEFUL_TIMEOUT_SECONDS,
    GRACEFUL_TIMEOUT_ENV,
    SIDE_PORT_ENV,
    _graceful_timeout,
    _probe_conflict,
    _side_port,
)


def test_graceful_timeout_default_covers_single_tool_call_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认值必须大于单次工具调用上限 200s，否则切换会切断在飞的长工具。"""
    monkeypatch.delenv(GRACEFUL_TIMEOUT_ENV, raising=False)

    assert DEFAULT_GRACEFUL_TIMEOUT_SECONDS == 240
    assert _graceful_timeout() == 240
    assert _graceful_timeout() > 200


def test_graceful_timeout_empty_value_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GRACEFUL_TIMEOUT_ENV, "   ")

    assert _graceful_timeout() == DEFAULT_GRACEFUL_TIMEOUT_SECONDS


@pytest.mark.parametrize("raw", ["0", "-1", "-240"])
def test_graceful_timeout_zero_or_negative_is_uvicorn_default(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    """``0``/负数 → ``None`` = 沿用 uvicorn 默认（无限等）。

    这条行为本身**危险**（旧实例可能永挂），但它是有意的逃生口：接口保持可观测，
    调用方（``scripts/shared_mcp.sh``）才有责任拒绝把 0 当真值传下来。
    """
    monkeypatch.setenv(GRACEFUL_TIMEOUT_ENV, raw)

    assert _graceful_timeout() is None


def test_graceful_timeout_invalid_value_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """非法字符串 → 默认值 + warning（配置写错时「略久一点」比「立刻失效」安全）。"""
    monkeypatch.setenv(GRACEFUL_TIMEOUT_ENV, "30s")

    with caplog.at_level(logging.WARNING, logger="mcp_server.__main__"):
        assert _graceful_timeout() == DEFAULT_GRACEFUL_TIMEOUT_SECONDS
    assert any(GRACEFUL_TIMEOUT_ENV in record.getMessage() for record in caplog.records)


def test_graceful_timeout_positive_value_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GRACEFUL_TIMEOUT_ENV, "90")

    assert _graceful_timeout() == 90


def test_side_port_unset_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SIDE_PORT_ENV, raising=False)

    assert _side_port() is None


def test_side_port_valid_value_is_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SIDE_PORT_ENV, "8091")

    assert _side_port() == 8091


def test_side_port_invalid_value_is_none_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """非法值必须当「没配」：蓝绿候选宁可不加 side 监听，也不能监听一个错端口。"""
    monkeypatch.setenv(SIDE_PORT_ENV, "side")

    with caplog.at_level(logging.WARNING, logger="mcp_server.__main__"):
        assert _side_port() is None
    assert any(SIDE_PORT_ENV in record.getMessage() for record in caplog.records)


def test_probe_conflict_detects_listening_instance() -> None:
    """端口已有监听者 → ``True``（造冲突用本地临时端口，不依赖外部服务）。"""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        port = holder.getsockname()[1]

        assert _probe_conflict("127.0.0.1", port) is True
    finally:
        holder.close()


def test_probe_conflict_returns_false_for_free_port() -> None:
    """端口空闲 → ``False``（探针自己必须能绑上并立刻释放，别把端口占成冲突）。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    finally:
        probe.close()

    assert _probe_conflict("127.0.0.1", port) is False
    # 探针已释放：紧跟着再探一次仍然空闲（否则探针会把端口锁死，服务反而起不来）。
    assert _probe_conflict("127.0.0.1", port) is False
