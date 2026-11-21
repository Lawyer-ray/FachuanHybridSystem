"""三个 agent 后端必须尊重 ``RunContext.api_key``（编排层轮次级 key 分配）。

## 背景（实测账）

律所 LiteLLM 网关对**每把** key 限 ``max_parallel_requests=3``，超了返 429 +
``retry-after: 60``。``_next_key`` 是**全局轮转计数**：它不知道哪把 key 已经满了，
也不保证同一轮的三个 agent 拿到互不相同的 key。所以「三 agent 用三把 key」只能由
编排层按轮次分配（``backends/key_scheduler`` → ``RunContext.api_key``），后端的职责
只剩一条：**有值就照着用，没有才回落到 ``_next_key``**。

## 本文件守护三件事

1. **有值就用**：openai-agents / dsh / pi 三个后端都不许再调 ``_next_key`` 覆盖
   编排层的分配。覆盖不会报错，只表现为「偶尔某栏卡 60 秒」——最难查的一类故障。
2. **无值不变**：``api_key=None`` 时仍走 ``_next_key``，现有调用方（``compact_service``
   这类不传 key 的路径）行为逐字不变。
3. **key 不进日志**：明文 key 与 ``user_token`` 同级，日志里出现即红灯（需要标识时
   用 ``key_scheduler.fingerprint``）。

pi 那条链最长（``PiBackend`` → ``PiProcessPool.acquire`` → ``write_pi_config`` →
``write_models_json`` → ``build_models_json``），每一跳都单独钉住：任何一跳漏传，
key 都会静默回落到轮转，而链路上没有任何报错。
"""

from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any, cast

import pytest

from apps.agent.backends import RunContext

#: 判别哨兵：出现在日志里即红灯。
_SECRET = "sk-orchestrated-0001"  # pragma: allowlist secret


class _Session:
    session_id = "sess-1"


def _ctx(*, api_key: str | None) -> RunContext:
    """最小 ``RunContext``：只关心 ``api_key`` 这一栏，其余给合法值。"""
    return RunContext(
        run_id="sess-1:pi:1",
        session=_Session(),
        user_id=None,
        prompt="你好",
        user_token="tok",
        model="kimi-2.6",
        tool_selection=None,
        api_key=api_key,
    )


# ── openai-agents ───────────────────────────────────────────────────


def _openai_module() -> Any:
    """``openai_agents_backend`` 顶层 ``import agents``：SDK 没装时跳过这一路。"""
    pytest.importorskip("agents", reason="openai-agents SDK 未安装，跳过 openai-agents 后端用例")
    from apps.agent.backends import openai_agents_backend

    return openai_agents_backend


def _gateway_settings(**overrides: Any) -> Any:
    """网关配置快照桩（``GatewaySettings`` 的形状）。"""
    fields: dict[str, Any] = {
        "name": "律所 kimi",
        "concurrency_per_key": 3,
        "base_url": "http://gw.internal:4000/v1",
        "api_keys": ("k1", "k2"),
        "models": ("kimi-2.6",),
        "default_model": "kimi-2.6",
        "enable_thinking": False,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestOpenAiAgentsKey:
    """``gateway_from_settings`` / ``_resolve_gateway`` 的 key 选择。"""

    def test_settings_key_override_skips_rotation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _openai_module()
        rotated: list[list[str]] = []

        def _next(keys: list[str], **_kw: object) -> str:
            rotated.append(keys)
            return "rotated"

        monkeypatch.setattr(module, "_next_key", _next)
        gateway = module.gateway_from_settings(_gateway_settings(), None, api_key=_SECRET)
        assert gateway == ("http://gw.internal:4000/v1", _SECRET, "kimi-2.6")
        assert rotated == [], "编排层指定了 key 就不许再轮转（会把分配结果覆盖掉）"

    def test_settings_without_key_still_rotates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """兼容底线：不传 ``api_key`` 时行为与引入该参数前逐字一致。"""
        module = _openai_module()
        monkeypatch.setattr(module, "_next_key", lambda keys, **_kw: "rotated")
        gateway = module.gateway_from_settings(_gateway_settings(), None)
        assert gateway is not None
        assert gateway[1] == "rotated"

    def test_backend_resolves_gateway_with_ctx_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """调用方必须把 ``ctx.api_key`` 真的传下去——参数加了但没接线等于没做。"""
        module = _openai_module()
        monkeypatch.setattr(module, "get_gateway_settings", lambda hint: _gateway_settings())
        monkeypatch.setattr(module, "_next_key", lambda keys, **_kw: pytest.fail("ctx.api_key 有值时不得轮转"))
        resolved = asyncio.run(module.OpenAiAgentsBackend()._resolve_gateway(_ctx(api_key=_SECRET)))
        assert resolved.api_key == _SECRET

    def test_backend_falls_back_without_ctx_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _openai_module()
        monkeypatch.setattr(module, "get_gateway_settings", lambda hint: _gateway_settings())
        monkeypatch.setattr(module, "_next_key", lambda keys, **_kw: "rotated")
        resolved = asyncio.run(module.OpenAiAgentsBackend()._resolve_gateway(_ctx(api_key=None)))
        assert resolved.api_key == "rotated"  # pragma: allowlist secret

    def test_key_never_logged(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        module = _openai_module()
        monkeypatch.setattr(module, "get_gateway_settings", lambda hint: _gateway_settings())
        # 这条路径目前**一行日志都不打**，所以断言的是「将来加的日志不许带明文 key」。
        with caplog.at_level(logging.DEBUG):
            asyncio.run(module.OpenAiAgentsBackend()._resolve_gateway(_ctx(api_key=_SECRET)))
        assert _SECRET not in caplog.text


# ── dsh ────────────────────────────────────────────────────────────


def _dsh_provider(**overrides: Any) -> Any:
    """足以映射出 dsh 配置的 provider 桩（形状照 ``LLMProvider``）。"""

    class _P:
        name = "测试平台"
        base_url = "http://gw.example/v1"
        api_keys = "k1\nk2"  # pragma: allowlist secret
        default_model = "kimi-2.6"
        extra_models = ""
        enable_thinking = False

    provider = _P()
    for key, value in overrides.items():
        setattr(provider, key, value)
    return provider


@pytest.fixture(autouse=True)
def _isolated_dsh_home(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """dsh home 落临时目录；并关掉 profile 自动引导（否则会真跑 ``dsh plugin add``）。"""
    from apps.agent.backends.dsh_config import DSH_HOME_ENV

    monkeypatch.setenv(DSH_HOME_ENV, str(tmp_path / "dsh-home"))
    monkeypatch.setenv("FACHUAN_DSH_AUTO_PROFILE", "0")


class TestDshKey:
    """``build_config`` / ``_resolve_config`` 的 key 选择。"""

    def test_build_config_uses_api_key_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.backends import dsh_config

        monkeypatch.setattr(dsh_config, "_next_key", lambda keys, **_kw: pytest.fail("api_key 有值时 dsh 不得再轮转"))
        config = dsh_config.build_config(user_id=7, provider=_dsh_provider(), api_key=_SECRET)
        assert config is not None
        assert config.api_key == _SECRET

    def test_build_config_without_api_key_still_rotates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.backends import dsh_config

        monkeypatch.setattr(dsh_config, "_next_key", lambda keys, **_kw: "rotated")
        config = dsh_config.build_config(user_id=7, provider=_dsh_provider())
        assert config is not None
        assert config.api_key == "rotated"  # pragma: allowlist secret

    def test_backend_forwards_ctx_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``DshBackend._resolve_config`` 必须把 ``ctx.api_key`` 传给 ``build_config``。"""
        from apps.agent.backends import dsh_backend, dsh_config

        captured: dict[str, Any] = {}

        def _build_config(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return dsh_config.DshProviderConfig(
                dsh_home="/tmp/x",
                provider="deepseek-official",
                model="kimi-2.6",
                base_url="u",
                api_key="k",  # pragma: allowlist secret
            )

        monkeypatch.setattr(dsh_config, "build_config", _build_config)
        backend = dsh_backend.DshBackend(pool=cast(Any, SimpleNamespace()))
        asyncio.run(backend._resolve_config(_ctx(api_key=_SECRET)))
        assert captured["api_key"] == _SECRET

    def test_key_never_logged(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        from apps.agent.backends import dsh_config

        with caplog.at_level(logging.DEBUG):
            dsh_config.build_config(user_id=7, provider=_dsh_provider(), api_key=_SECRET)
        # 无律师 token 时 dsh_mcp 会留一条 warning——先确认本用例真的在采日志，
        # 否则 ``not in caplog.text`` 是空断言（永远成立，也永远不守护任何东西）。
        assert caplog.records, "本用例靠真实日志记录判断，路径上必须至少有一条日志"
        assert _SECRET not in caplog.text


# ── pi ─────────────────────────────────────────────────────────────


def _pi_provider(**overrides: Any) -> Any:
    """足以渲染 models.json 的 provider 桩（形状照 ``LLMProvider``）。"""

    class _P:
        name = "测试平台"
        base_url = "http://gw.example/v1"
        api_keys = "k1\nk2"  # pragma: allowlist secret
        default_model = "kimi-2.6"
        extra_models = ""
        vision_model = ""
        enable_thinking = False

        def supports_thinking(self, model: str = "") -> bool:
            return False

    provider = _P()
    for key, value in overrides.items():
        setattr(provider, key, value)
    return provider


def _read_api_key(path: Any) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    key: str = payload["providers"]["fachuan"]["apiKey"]
    return key


class TestPiWorkspaceKey:
    """pi 工作区配置（models.json）里的 key：``model_config`` → ``shared_mcp``。"""

    @staticmethod
    def _no_gateway_mode(monkeypatch: pytest.MonkeyPatch) -> None:
        """网关模式下 pi 不持真实 key（走 ``FACHUAN_PI_GATEWAY_KEY``），要先排掉。"""
        from apps.agent.pi import model_config

        monkeypatch.delenv(model_config.GATEWAY_URL_ENV, raising=False)

    def test_models_json_uses_api_key_override(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.pi import model_config

        self._no_gateway_mode(monkeypatch)
        monkeypatch.setattr(model_config, "_next_key", lambda keys, **_kw: pytest.fail("api_key 有值时 pi 不得再轮转"))
        path = model_config.write_models_json(tmp_path, "kimi-2.6", provider=_pi_provider(), api_key=_SECRET)
        assert path is not None
        assert _read_api_key(path) == _SECRET

    def test_models_json_without_api_key_still_rotates(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.pi import model_config

        self._no_gateway_mode(monkeypatch)
        monkeypatch.setattr(model_config, "_next_key", lambda keys, **_kw: "rotated")
        path = model_config.write_models_json(tmp_path, "kimi-2.6", provider=_pi_provider())
        assert path is not None
        assert _read_api_key(path) == "rotated"

    def test_write_pi_config_forwards_api_key_to_models_json(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``write_pi_config`` 是 pi 工作区配置的唯一写入口，它漏传就整条链断掉。"""
        from apps.agent.pi import model_config, shared_mcp

        self._no_gateway_mode(monkeypatch)
        monkeypatch.setenv("FACHUAN_PI_USER_DIR", str(tmp_path / "user-pi"))
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _pi_provider())
        shared_mcp.write_pi_config(tmp_path / "cfg", api_key=_SECRET)
        assert _read_api_key(tmp_path / "cfg" / "models.json") == _SECRET

    def test_key_never_logged(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from apps.agent.pi import model_config, shared_mcp

        self._no_gateway_mode(monkeypatch)
        monkeypatch.setenv("FACHUAN_PI_USER_DIR", str(tmp_path / "user-pi"))
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _pi_provider())
        with caplog.at_level(logging.DEBUG):
            shared_mcp.write_pi_config(tmp_path / "cfg", api_key=_SECRET)
        # 写 settings.json 会打一条 info——先确认真的采到了日志（非空断言）。
        assert caplog.records, "本用例靠真实日志记录判断，路径上必须至少有一条日志"
        assert _SECRET not in caplog.text


class TestPiPoolKey:
    """``PiProcessPool.acquire`` 把 key 转交给工作区写函数。"""

    @pytest.mark.parametrize(("api_key", "expected"), [(_SECRET, _SECRET), (None, None)])
    def test_pool_forwards_api_key_to_workspace_writer(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, api_key: str | None, expected: str | None
    ) -> None:
        from apps.agent.pi import pool as pool_module

        captured: dict[str, Any] = {}

        def _write_pi_config(
            target_dir: Any, endpoint: Any = None, model_hint: str = "", *, api_key: str | None = None
        ) -> None:
            captured["api_key"] = api_key

        class _StubSession:
            def __init__(self, **kwargs: Any) -> None:
                return None

            async def start(self) -> None:
                return None

            async def close(self, *, abort_running: bool = False) -> None:
                return None

        monkeypatch.setattr(pool_module, "write_pi_config", _write_pi_config)
        monkeypatch.setattr(pool_module, "PiRpcSession", _StubSession)
        # Redis 分布式闸门：本用例只验 key 传递，不碰跨 worker 计数。
        monkeypatch.setattr(pool_module, "_try_redis_slot", lambda size: None)
        monkeypatch.setattr(
            pool_module,
            "layout",
            lambda: (tmp_path / "work", tmp_path / "cfg", tmp_path / "sessions"),
        )
        pi_pool = pool_module.PiProcessPool(pool_module.PoolConfig(size=1))

        async def run() -> None:
            async with pi_pool.acquire(api_key=api_key):
                return None

        asyncio.run(run())
        assert captured["api_key"] == expected


class TestPiBackendKey:
    """``PiBackend.stream`` 把 ``ctx.api_key`` 交给池（链路的入口那一跳）。"""

    @staticmethod
    def _install_stubs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        from apps.agent.services.event_bus import EventBus

        captured: dict[str, Any] = {}

        class _StubSession:
            async def prompt(self, message: str) -> None:
                return None

            async def get_session_stats(self) -> dict[str, Any]:
                return {}

        class _StubAcquire:
            async def __aenter__(self) -> _StubSession:
                return _StubSession()

            async def __aexit__(self, *exc: object) -> bool:
                return False

        class _StubPool:
            waiting = 0
            saturated = False

            def acquire(self, **kwargs: Any) -> _StubAcquire:
                captured.update(kwargs)
                return _StubAcquire()

        async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
            yield {"type": "delta", "content": "答"}
            yield {"type": "done"}

        async def fake_get_pool() -> Any:
            return _StubPool()

        async def fake_model() -> str | None:
            return "kimi-2.6"

        monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool.get_pool", fake_get_pool)
        monkeypatch.setattr("apps.agent.backends.pi_backend.chat_pool._resolve_model", fake_model)
        monkeypatch.setattr("apps.agent.backends.pi_backend.stream_events", fake_stream)
        monkeypatch.setattr("apps.agent.backends.pi_backend.register_live_route", lambda *a, **k: None)
        monkeypatch.setattr("apps.agent.backends.pi_backend.unregister_live_route", lambda *a, **k: None)
        monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)
        return captured

    @pytest.mark.parametrize(("api_key", "expected"), [(_SECRET, _SECRET), (None, None)])
    def test_stream_passes_ctx_api_key_to_pool(
        self, monkeypatch: pytest.MonkeyPatch, api_key: str | None, expected: str | None
    ) -> None:
        from apps.agent.backends.pi_backend import PiBackend

        captured = self._install_stubs(monkeypatch)

        async def collect() -> None:
            async for _ in PiBackend().stream(_ctx(api_key=api_key)):
                pass

        asyncio.run(collect())
        assert captured["api_key"] == expected
