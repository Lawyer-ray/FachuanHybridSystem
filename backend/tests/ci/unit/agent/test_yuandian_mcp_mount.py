"""元典 MCP 挂进 pi ``mcp.json`` 的契约测试。

## 为什么单开一份

元典的 4 个 MCP Server（law 5 工具 / case 4 / company 26 / securities 6）是**远端
HTTP** server，和法穿自己那份 stdio/共享 HTTP 形态不同：没有进程可管，只有一条
``mcpServers`` 条目 + 一把 Bearer key。

这里守护几件「坏了也不会报错」的事：

1. **key 不落盘**：``mcp.json`` 是常驻明文文件（会话目录会被下一个用户复用，也会
   进磁盘快照/备份），只许出现 ``${FACHUAN_YUANDIAN_API_KEY}`` 占位；
2. **``type`` 用我们在 pi 上验证过的取值**（``streamable-http``），不是官方示例的
   ``http``——两者写错时只表现为「工具不出现」；
3. **没 key 或总开关关闭就一条元典 server 都不挂**：带空 key 的 server 每条
   ``tools/list`` 都 401，却仍把这批查不了的工具声明给模型；
4. **``hallucination`` 不在清单里**：它仅 VIP 可用；
5. **多把 key 按 pi 进程轮转**：不是永远用第一把；
6. **读配置失败、密文解不开都降级为「未配置」**，且日志里不出现配置值。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from django.core.exceptions import SynchronousOnlyOperation
from django.db import DatabaseError

from apps.core.services import yuandian_settings as settings_module
from apps.core.services.yuandian_settings import (
    API_KEYS_CONFIG_KEY,
    API_KEYS_ENV_KEY,
    MCP_ENABLED_CONFIG_KEY,
    YUANDIAN_MCP_BASE_URL,
    YUANDIAN_MCP_SERVERS,
    YuandianSettings,
    load_yuandian_settings,
    pick_api_key,
    split_api_keys,
    yuandian_mcp_enabled,
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


class _AsyncContextSystemConfig:
    """模拟在 async 上下文里直接调同步 ORM：Django 抛 ``SynchronousOnlyOperation``。

    它直接继承 ``Exception``，不是 ``DatabaseError``——旧实现正是漏了这一类。
    """

    def get_value(self, key: str, default: str = "") -> str:
        raise SynchronousOnlyOperation("You cannot call this from an async context")


#: 「密文解不开」的形态：``SystemConfigService.get_value`` 解密失败时不抛，原样返回密文。
_UNDECRYPTABLE = "enc:v1:bm90LWEtdmFsaWQtZmVybmV0LXRva2Vu"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """key 有 env 回落，先清掉宿主机上可能存在的同名变量。"""
    monkeypatch.delenv(API_KEYS_ENV_KEY, raising=False)
    monkeypatch.delenv(_YUANDIAN_KEY_ENV, raising=False)
    yield


def _stub_settings(monkeypatch: pytest.MonkeyPatch, *, keys: tuple[str, ...], enabled: bool = True) -> None:
    """替换两个读配置口径（key 池与总开关），不碰数据库与缓存。"""
    monkeypatch.setattr(settings_module, "load_yuandian_settings", lambda **kwargs: YuandianSettings(api_keys=keys))
    monkeypatch.setattr(settings_module, "yuandian_mcp_enabled", lambda **kwargs: enabled)


@pytest.fixture
def with_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """把元典当成「已配两把 key、开关开启」。"""
    _stub_settings(monkeypatch, keys=(_KEY_1, _KEY_2))


@pytest.fixture
def with_one_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_settings(monkeypatch, keys=(_KEY_1,))


@pytest.fixture
def without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_settings(monkeypatch, keys=())


@pytest.fixture
def switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """配了 key，但总开关关闭。"""
    _stub_settings(monkeypatch, keys=(_KEY_1, _KEY_2), enabled=False)


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
        """读库失败只降级成空 key，不抛。"""
        settings = load_yuandian_settings(config_service=_FailingSystemConfig())  # type: ignore[arg-type]

        assert settings.api_keys == ()

    def test_survives_sync_orm_in_async_context(self, caplog: pytest.LogCaptureFixture) -> None:
        """``SynchronousOnlyOperation`` 不是 ``DatabaseError``：旧实现接不住，直接抛给调用方。"""
        with caplog.at_level(logging.WARNING, logger=settings_module.__name__):
            settings = load_yuandian_settings(config_service=_AsyncContextSystemConfig())  # type: ignore[arg-type]

        assert settings.api_keys == ()
        record = next(r for r in caplog.records if r.name == settings_module.__name__)
        assert record.config_key == API_KEYS_CONFIG_KEY  # type: ignore[attr-defined]
        assert record.error_type == "SynchronousOnlyOperation"  # type: ignore[attr-defined]

    def test_undecryptable_value_is_not_used_as_key(self, caplog: pytest.LogCaptureFixture) -> None:
        """密文解不开时 ``get_value`` 原样返回密文：不能把它当成一把 key 发给元典。"""
        service = _FakeSystemConfig({API_KEYS_CONFIG_KEY: _UNDECRYPTABLE})

        with caplog.at_level(logging.WARNING, logger=settings_module.__name__):
            settings = load_yuandian_settings(config_service=service)  # type: ignore[arg-type]

        assert settings.api_keys == ()
        assert _UNDECRYPTABLE not in caplog.text, "密文不许进日志"
        assert any(r.name == settings_module.__name__ for r in caplog.records), "解密失败必须留下 warning"

    def test_undecryptable_value_through_real_config_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """走真实 ``SystemConfigService.get_value`` + ``_maybe_decrypt``（只替换仓储与缓存）。

        锁住的前提是「解密失败返回密文而不是抛」——若哪天那边改成抛，这条用例会提醒
        本模块补上对应的异常类型。
        """
        from apps.core.services import system_config_service as service_module

        class _Row:
            is_active = True
            value = _UNDECRYPTABLE

        class _Repo:
            def get_by_key(self, key: str) -> _Row | None:
                return _Row() if key == API_KEYS_CONFIG_KEY else None

        class _DictCache:
            def __init__(self) -> None:
                self._data: dict[str, Any] = {}

            def get(self, key: str) -> Any:
                return self._data.get(key)

            def set(self, key: str, value: Any, timeout: int | None = None) -> None:
                self._data[key] = value

        monkeypatch.setattr(service_module, "cache", _DictCache())
        service = service_module.SystemConfigService(repository=_Repo())  # type: ignore[arg-type]

        assert load_yuandian_settings(config_service=service).api_keys == ()

    def test_repr_does_not_leak_keys(self) -> None:
        assert _KEY_1 not in repr(YuandianSettings(api_keys=(_KEY_1,)))

    def test_split_api_keys_keeps_order_and_dedups(self) -> None:
        raw = f"{_KEY_1}\r\n  {_KEY_2}  \n\n {_KEY_1} \n test-key-3"

        assert split_api_keys(raw) == (_KEY_1, _KEY_2, "test-key-3")

    def test_split_api_keys_does_not_split_on_commas(self) -> None:
        # key 里可能出现逗号/分号，只按行切——多切一刀就是两把废 key。
        assert split_api_keys("test-key,a\ntest-key;b") == ("test-key,a", "test-key;b")


class TestYuandianMcpEnabled:
    @pytest.mark.parametrize("raw", ["", "true", "TRUE", " 1 ", "yes", "on", "随便写"])
    def test_enabled_unless_explicitly_off(self, raw: str) -> None:
        service = _FakeSystemConfig({MCP_ENABLED_CONFIG_KEY: raw})

        assert yuandian_mcp_enabled(config_service=service) is True  # type: ignore[arg-type]
        assert service.requested == [MCP_ENABLED_CONFIG_KEY]

    @pytest.mark.parametrize("raw", ["false", "False", " 0 ", "no", "OFF"])
    def test_disabled_values(self, raw: str) -> None:
        service = _FakeSystemConfig({MCP_ENABLED_CONFIG_KEY: raw})

        assert yuandian_mcp_enabled(config_service=service) is False  # type: ignore[arg-type]

    def test_missing_config_means_enabled(self) -> None:
        """没初始化过默认配置的环境：保持「配了 key 就挂」的既有行为。"""
        assert yuandian_mcp_enabled(config_service=_FakeSystemConfig()) is True  # type: ignore[arg-type]

    @pytest.mark.parametrize("service", [_FailingSystemConfig(), _AsyncContextSystemConfig()])
    def test_read_failure_means_enabled(self, service: Any) -> None:
        """读开关失败按默认值「开」：与 key 读失败的降级口径一致（没 key 照样不挂）。"""
        assert yuandian_mcp_enabled(config_service=service) is True


class TestPickApiKey:
    def test_empty_pool_returns_empty_string(self) -> None:
        assert pick_api_key(()) == ""

    def test_single_key_is_always_the_same(self) -> None:
        assert {pick_api_key((_KEY_1,)) for _ in range(5)} == {_KEY_1}

    def test_consecutive_picks_rotate(self) -> None:
        first, second = pick_api_key((_KEY_1, _KEY_2)), pick_api_key((_KEY_1, _KEY_2))

        assert {first, second} == {_KEY_1, _KEY_2}

    def test_rotation_is_even_across_threads(self) -> None:
        picks: list[str] = []
        lock = threading.Lock()

        def worker() -> None:
            for _ in range(25):
                key = pick_api_key((_KEY_1, _KEY_2))
                with lock:
                    picks.append(key)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert Counter(picks) == {_KEY_1: 50, _KEY_2: 50}


# ── mcp.json 挂载 ─────────────────────────────────────────────
class TestMcpServersMerge:
    def test_without_keys_no_yuandian_server_is_mounted(self, tmp_path: Path, without_keys: None) -> None:
        """没配 key：``mcpServers`` 只有法穿自己那一条，且不抛。"""
        from apps.agent.pi import shared_mcp

        path = shared_mcp.write_pi_mcp_config(tmp_path)

        assert list(_mcp_json(path.parent)) == ["fachuan"]

    def test_switched_off_no_yuandian_server_is_mounted(self, tmp_path: Path, switched_off: None) -> None:
        """总开关关闭：即使配了 key，``mcpServers`` 也只有法穿自己那一条。"""
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
        assert self._acquire_env(monkeypatch)[_YUANDIAN_KEY_ENV] in {_KEY_1, _KEY_2}

    def test_consecutive_processes_get_different_keys(self, monkeypatch: pytest.MonkeyPatch, with_keys: None) -> None:
        """多把 key：每拉起一个 pi 进程换下一把（旧实现恒为第一把）。"""
        first = self._acquire_env(monkeypatch)[_YUANDIAN_KEY_ENV]
        second = self._acquire_env(monkeypatch)[_YUANDIAN_KEY_ENV]

        assert {first, second} == {_KEY_1, _KEY_2}

    def test_single_key_is_reused(self, monkeypatch: pytest.MonkeyPatch, with_one_key: None) -> None:
        envs = [self._acquire_env(monkeypatch)[_YUANDIAN_KEY_ENV] for _ in range(3)]

        assert envs == [_KEY_1, _KEY_1, _KEY_1]

    def test_env_var_is_absent_without_keys(self, monkeypatch: pytest.MonkeyPatch, without_keys: None) -> None:
        """没 key 时这个变量**不存在**（不是空串——空串会展开成 ``Bearer `` 无效头）。"""
        assert _YUANDIAN_KEY_ENV not in self._acquire_env(monkeypatch)

    def test_env_var_is_absent_when_switched_off(self, monkeypatch: pytest.MonkeyPatch, switched_off: None) -> None:
        """总开关关闭：配了 key 也不注入（与 ``mcp.json`` 不挂元典 server 同口径）。"""
        assert _YUANDIAN_KEY_ENV not in self._acquire_env(monkeypatch)


# ── 系统配置默认项：只有 API Key 与 MCP 总开关 ────────────────────
class TestYuandianDefaultConfigs:
    def test_only_api_keys_and_switch_are_seeded(self) -> None:
        """平台地址/挂载清单/并发上限是代码常量，不该在后台配置页留空壳。"""
        from apps.core.admin._system_config_data._service_configs import get_enterprise_data_configs

        items = {item["key"]: item for item in get_enterprise_data_configs() if item["key"].startswith("YUANDIAN_")}

        assert sorted(items) == sorted([API_KEYS_CONFIG_KEY, MCP_ENABLED_CONFIG_KEY])
        assert items[API_KEYS_CONFIG_KEY]["is_secret"] is True, "API Key 必须加密落库"
        assert items[MCP_ENABLED_CONFIG_KEY]["is_secret"] is False
        assert items[MCP_ENABLED_CONFIG_KEY]["value"] == "true", "默认开启，保持既有行为"
        assert items[MCP_ENABLED_CONFIG_KEY]["category"] == "enterprise_data"

    def test_switch_renders_as_dropdown(self) -> None:
        """开关是封闭取值：后台渲染成下拉框，且每个选项都能被 ``yuandian_mcp_enabled`` 正确解析。"""
        from apps.core.admin.forms.system_config_admin_form import _ENUM_CONFIGS

        choices = dict(_ENUM_CONFIGS[MCP_ENABLED_CONFIG_KEY])
        assert set(choices) == {"true", "false"}
        for raw, expected in (("true", True), ("false", False)):
            service = _FakeSystemConfig({MCP_ENABLED_CONFIG_KEY: raw})
            assert yuandian_mcp_enabled(config_service=service) is expected  # type: ignore[arg-type]

    def test_api_keys_is_multiline(self) -> None:
        """多把 key 每行一个：Admin 表单按 ``_MULTI_KEY_CONFIGS`` 渲染成多行框。"""
        from apps.core.admin.forms.system_config_admin_form import _MULTI_KEY_CONFIGS

        assert API_KEYS_CONFIG_KEY in _MULTI_KEY_CONFIGS
