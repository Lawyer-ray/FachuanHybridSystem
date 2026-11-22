"""元典 MCP 挂进 pi ``mcp.json`` 的契约测试。

## 为什么单开一份

元典的 4 个 MCP Server（law 5 工具 / case 4 / company 26 / securities 6）是**远端
HTTP** server，和法穿自己那份 stdio/共享 HTTP 形态不同：没有进程可管，只有一条
``mcpServers`` 条目 + 一把 Bearer key。

这里守护四件「坏了也不会报错」的事：

1. **key 不落盘**：``mcp.json`` 是常驻明文文件（会话目录会被下一个用户复用，也会
   进磁盘快照/备份），只许出现 ``${FACHUAN_YUANDIAN_API_KEY}`` 占位；
2. **``type`` 用我们在 pi 上验证过的取值**（``streamable-http``），不是官方示例的
   ``http``——两者写错时只表现为「工具不出现」；
3. **没 key 就一条元典 server 都不挂**：带空 key 的 server 每条 ``tools/list`` 都
   401，却仍把这批查不了的工具声明给模型；
4. **``hallucination`` 不在清单里**：它仅 VIP 可用。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from django.db import DatabaseError

from apps.core.services import yuandian_settings as settings_module
from apps.core.services.yuandian_settings import (
    API_KEYS_CONFIG_KEY,
    API_KEYS_ENV_KEY,
    YUANDIAN_MCP_BASE_URL,
    YUANDIAN_MCP_SERVERS,
    YuandianSettings,
    load_yuandian_settings,
    split_api_keys,
)

_KEY_1 = "test-key-1"  # pragma: allowlist secret
_KEY_2 = "test-key-2"  # pragma: allowlist secret
_YUANDIAN_KEY_ENV = "FACHUAN_YUANDIAN_API_KEY"


class _FakeSystemConfig:
    """只实现 ``get_value``，避免单测碰库。"""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = dict(values or {})
        self.requested: list[str] = []

    def get_value(self, key: str, default: str = "") -> str:
        self.requested.append(key)
        return self._values.get(key, default)


class _FailingSystemConfig:
    """模拟读库失败。

    抛 ``DatabaseError``（真实 DB 故障的形态）而不是 ``RuntimeError``：后者会逼生产
    代码把捕获放宽到 ``RuntimeError``，那就和白名单没区别了——本仓棘轮也不允许。
    """

    def get_value(self, key: str, default: str = "") -> str:
        raise DatabaseError("数据库访问被禁止（模拟读库失败）")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """key 有 env 回落，先清掉宿主机上可能存在的同名变量。"""
    monkeypatch.delenv(API_KEYS_ENV_KEY, raising=False)
    monkeypatch.delenv(_YUANDIAN_KEY_ENV, raising=False)
    yield


@pytest.fixture
def with_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """把元典当成「已配 key」（替换读库口径，不碰数据库）。"""
    monkeypatch.setattr(
        settings_module,
        "load_yuandian_settings",
        lambda **kwargs: YuandianSettings(api_keys=(_KEY_1, _KEY_2)),
    )


@pytest.fixture
def without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module, "load_yuandian_settings", lambda **kwargs: YuandianSettings())


def _mcp_json(config_dir: Path) -> dict[str, Any]:
    server_map: dict[str, Any] = json.loads((config_dir / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    return server_map


# ── 常量与 key 解析 ────────────────────────────────────────────
class TestYuandianConstants:
    def test_mcp_servers_are_the_four_verified_ones(self) -> None:
        assert YUANDIAN_MCP_SERVERS == ("law", "case", "company", "securities")

    def test_hallucination_is_not_in_servers(self) -> None:
        """``hallucination`` 仅 VIP 可用：挂上去只会给模型一批查不了的工具。

        它现在**根本不在常量里**（不是运行时过滤），这条断言锁住「没人往回加」。
        """
        assert "hallucination" not in YUANDIAN_MCP_SERVERS

    def test_base_url_is_the_open_platform_without_trailing_slash(self) -> None:
        # 拼接口径是 ``f"{base}/mcp/{name}/stream"``，尾部带斜杠会拼出 ``//mcp``。
        assert YUANDIAN_MCP_BASE_URL == "https://open.chineselaw.com"


class TestLoadYuandianSettings:
    def test_reads_only_the_api_keys_config_key(self) -> None:
        service = _FakeSystemConfig({API_KEYS_CONFIG_KEY: f"{_KEY_1}\n{_KEY_2}\n"})

        settings = load_yuandian_settings(config_service=service)  # type: ignore[arg-type]

        assert settings.api_keys == (_KEY_1, _KEY_2)
        assert service.requested == [API_KEYS_CONFIG_KEY], "元典只应有 API Key 一个配置项"

    def test_defaults_to_no_keys_when_store_is_empty(self) -> None:
        settings = load_yuandian_settings(config_service=_FakeSystemConfig())  # type: ignore[arg-type]

        assert settings.api_keys == ()

    def test_falls_back_to_env_when_store_has_no_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(API_KEYS_ENV_KEY, f"{_KEY_1}\n{_KEY_2}")
        service = _FakeSystemConfig({API_KEYS_CONFIG_KEY: "  \n \n"})

        settings = load_yuandian_settings(config_service=service)  # type: ignore[arg-type]

        assert settings.api_keys == (_KEY_1, _KEY_2)

    def test_survives_broken_store(self) -> None:
        """读库失败（含「在 async 上下文直接读」）只降级成空 key，不抛。"""
        settings = load_yuandian_settings(config_service=_FailingSystemConfig())  # type: ignore[arg-type]

        assert settings.api_keys == ()

    def test_repr_does_not_leak_keys(self) -> None:
        assert _KEY_1 not in repr(YuandianSettings(api_keys=(_KEY_1,)))

    def test_split_api_keys_keeps_order_and_dedups(self) -> None:
        raw = f"{_KEY_1}\r\n  {_KEY_2}  \n\n {_KEY_1} \n test-key-3"

        assert split_api_keys(raw) == (_KEY_1, _KEY_2, "test-key-3")

    def test_split_api_keys_does_not_split_on_commas(self) -> None:
        # key 里可能出现逗号/分号，只按行切——多切一刀就是两把废 key。
        assert split_api_keys("test-key,a\ntest-key;b") == ("test-key,a", "test-key;b")


# ── mcp.json 挂载 ─────────────────────────────────────────────
class TestMcpServersMerge:
    def test_without_keys_no_yuandian_server_is_mounted(self, tmp_path: Path, without_keys: None) -> None:
        """没配 key：``mcpServers`` 只有法穿自己那一条，且不抛。"""
        from apps.agent.pi import shared_mcp

        path = shared_mcp.write_pi_mcp_config(tmp_path)

        assert list(_mcp_json(path.parent)) == ["fachuan"]

    def test_configured_servers_are_mounted_with_pi_verified_shape(self, tmp_path: Path, with_keys: None) -> None:
        from apps.agent.pi import shared_mcp

        path = shared_mcp.write_pi_mcp_config(tmp_path)

        servers = _mcp_json(path.parent)
        assert list(servers) == [
            "fachuan",
            f"yuandian-{YUANDIAN_MCP_SERVERS[0]}",
            f"yuandian-{YUANDIAN_MCP_SERVERS[1]}",
            f"yuandian-{YUANDIAN_MCP_SERVERS[2]}",
            f"yuandian-{YUANDIAN_MCP_SERVERS[3]}",
        ]
        entry = servers["yuandian-case"]
        assert entry["type"] == "streamable-http", "必须用 pi 上验证过的 type，不是官方示例的 http"
        assert entry["url"] == f"{YUANDIAN_MCP_BASE_URL}/mcp/case/stream"
        assert entry["headers"]["Accept"] == "application/json, text/event-stream"
        assert entry["headers"]["Authorization"] == f"Bearer ${{{_YUANDIAN_KEY_ENV}}}"

    def test_plaintext_key_never_reaches_disk(self, tmp_path: Path, with_keys: None) -> None:
        """红线：``mcp.json`` 里搜不到 key 明文，只有 env 占位。"""
        from apps.agent.pi import shared_mcp

        path = shared_mcp.write_pi_mcp_config(tmp_path)
        text = path.read_text(encoding="utf-8")

        assert _KEY_1 not in text, "key 明文落盘了"
        assert _KEY_2 not in text, "第二把 key 也不许落盘"
        assert text.count(f"${{{_YUANDIAN_KEY_ENV}}}") == len(YUANDIAN_MCP_SERVERS)

    def test_full_config_and_mcp_only_config_agree(self, tmp_path: Path, with_keys: None) -> None:
        """正式链路（``write_pi_config``）与手工写配置（``write_pi_mcp_config``）同一份口径。"""
        from apps.agent.pi import shared_mcp

        full = shared_mcp.write_pi_config(tmp_path / "full")
        mcp_only = shared_mcp.write_pi_mcp_config(tmp_path / "mcp-only")

        assert list(_mcp_json(full.parent)) == list(_mcp_json(mcp_only.parent))
        assert set(_mcp_json(full.parent)) == {"fachuan"} | {f"yuandian-{name}" for name in YUANDIAN_MCP_SERVERS}


# ── pi 子进程 env 注入 ────────────────────────────────────────
class _CapturingSession:
    last_extra_env: dict[str, str] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_extra_env = dict(kwargs.get("extra_env") or {})

    async def start(self) -> None:
        await asyncio.sleep(0)

    async def close(self, *, abort_running: bool = False) -> None:
        return None


class TestPoolInjectsYuandianKeyEnv:
    def _acquire_env(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
        from apps.agent.pi import pool as pool_module

        monkeypatch.setattr(pool_module, "write_pi_config", lambda *a, **k: None)
        monkeypatch.setattr(pool_module, "PiRpcSession", _CapturingSession)
        monkeypatch.setattr(
            pool_module,
            "layout",
            lambda: (Path("/tmp/stub-work"), Path("/tmp/stub-config"), Path("/tmp/stub-sessions")),
        )

        async def run() -> None:
            pool = pool_module.PiProcessPool(pool_module.PoolConfig(size=1, mcp_endpoint=None))
            async with pool.acquire():
                pass

        asyncio.run(run())
        return _CapturingSession.last_extra_env

    def test_key_is_injected_into_child_env(self, monkeypatch: pytest.MonkeyPatch, with_keys: None) -> None:
        assert self._acquire_env(monkeypatch)[_YUANDIAN_KEY_ENV] == _KEY_1

    def test_env_var_is_absent_without_keys(self, monkeypatch: pytest.MonkeyPatch, without_keys: None) -> None:
        """没 key 时这个变量**不存在**（不是空串——空串会展开成 ``Bearer `` 无效头）。"""
        assert _YUANDIAN_KEY_ENV not in self._acquire_env(monkeypatch)


# ── 系统配置默认项只剩 API Key ────────────────────────────────
class TestYuandianDefaultConfigs:
    def test_only_api_keys_is_seeded(self) -> None:
        """平台地址/挂载清单/并发上限是代码常量，不该在后台配置页留空壳。"""
        from apps.core.admin._system_config_data._service_configs import get_enterprise_data_configs

        yuandian_items = [item for item in get_enterprise_data_configs() if item["key"].startswith("YUANDIAN_")]

        assert [item["key"] for item in yuandian_items] == [API_KEYS_CONFIG_KEY]
        assert yuandian_items[0]["is_secret"] is True, "API Key 必须加密落库"

    def test_api_keys_is_multiline(self) -> None:
        """多把 key 每行一个：Admin 表单按 ``_MULTI_KEY_CONFIGS`` 渲染成多行框。"""
        from apps.core.admin.forms.system_config_admin_form import _MULTI_KEY_CONFIGS

        assert API_KEYS_CONFIG_KEY in _MULTI_KEY_CONFIGS
