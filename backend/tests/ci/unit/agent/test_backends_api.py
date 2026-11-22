"""``GET /agent/backends``：前端切换器的后端清单与可用性自检。

三个验收点：

1. **结构**：每个已注册后端一条，带用户可见名、能力声明、可用性与原因；
2. **可用性是真判据**：dsh 缺 SDK / 缺可用 LLMProvider 时 ``available=False``
   且给出原因，而不是让用户「选完再报错」——``agent_kind`` 是会话级属性，
   建完会话不能改，撞墙的代价是换个后端重开；
3. **未注册的 dsh 仍出现**（置灰）：直接不列会让人以为「本系统没有这个后端」，
   而真相是「这里缺东西」，后者可排查。

全部离线：注册表用假后端注入，LLMProvider 用桩替换，不起任何子进程。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.api import session_api
from apps.agent.backends import BackendCapabilities, register
from apps.agent.backends import registry as registry_module
from apps.agent.schemas import BackendOptionOut


def _caps(**overrides: Any) -> BackendCapabilities:
    base: dict[str, Any] = {
        "streaming": True,
        "tool_calls": True,
        "approval": True,
        "compaction": True,
        "steer": True,
    }
    base.update(overrides)
    return BackendCapabilities(**base)


class _FakeBackend:
    """最小注册项：本端点只读 ``kind`` 与 ``capabilities``，不跑 stream。"""

    def __init__(self, kind: str, caps: BackendCapabilities | None = None) -> None:
        self.kind = kind
        self.capabilities = caps or _caps()

    def stream(self, ctx: Any) -> Any:  # pragma: no cover - 本端点不调用
        raise NotImplementedError


class _FakeProvider:
    def __init__(self, default_model: str = "test-model", extra_models: str = "") -> None:
        self.default_model = default_model
        self.extra_models = extra_models


@pytest.fixture(autouse=True)
def _isolated_registry() -> Any:
    """注册表是进程内全局状态：每条用例前后清空（否则串用例出假绿）。"""
    registry_module.clear()
    yield
    registry_module.clear()


@pytest.fixture(autouse=True)
def _dsh_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认「SDK 已装 + 有可用 provider」；各用例按需覆盖单项。

    打桩点选 ``_dsh_probe``（探测结果）而不是 ``importlib.util.find_spec``：
    后者本机能真装到 SDK，桩成功也测不出差异。探测内部的两条判据由
    ``TestDshProbe`` 直接测真实函数（该类用 ``monkeypatch.undo()`` 先撤掉本夹具）。
    """
    monkeypatch.setattr(session_api, "_dsh_probe", lambda: (True, ""))


def _options() -> dict[str, BackendOptionOut]:
    """按 kind 索引的选项表。

    ``_collect_backend_options`` 会先 ``ensure_registered()``（幂等），真实的 pi
    因此也会出现在结果里——调用方一律按 kind 取值，不假设总数。
    """
    return {option.kind: option for option in session_api._collect_backend_options()}


class TestResponseShape:
    def test_lists_every_registered_backend(self) -> None:
        register(_FakeBackend("pi"))
        register(_FakeBackend("dsh"))
        # ``ensure_registered()``（幂等）会把真实内置后端一并补进注册表，所以这里
        # 断言「注入的两个都在」而不是全集——后者每接一个后端就要改一次，且失败信息
        # 只说明「多了个 kind」，与本用例要验的「按 kind 逐条列出」无关。
        kinds = sorted(_options())
        assert {"dsh", "pi"} <= set(kinds)

    def test_each_option_carries_label_capabilities_and_schema_fields(self) -> None:
        register(_FakeBackend("pi", _caps(steer=False)))
        pi = _options()["pi"]
        assert isinstance(pi, BackendOptionOut)
        assert pi.label == "Pi"
        assert pi.description, "切换器要显示一句副标题，空串等于没解释"
        assert pi.available is True
        assert pi.reason == ""
        # 能力逐项展开（前端据此隐藏插话框）：不是嵌套对象
        assert pi.capabilities["steer"] is False
        assert pi.capabilities["streaming"] is True
        assert pi.capabilities["concurrent_in_session"] is False

    def test_unknown_kind_falls_back_to_kind_as_label(self) -> None:
        """新后端注册后至少不会出现空名字——不需要同时改本表。"""
        register(_FakeBackend("third"))
        option = _options()["third"]
        assert option.label == "third"
        assert option.available is True

    def test_non_dsh_backends_are_available_without_probing_llm_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """可用性判据只作用于 dsh：pi 有自己的可执行文件检测，不在本端点里拦。"""

        def _boom() -> str:
            raise AssertionError("非 dsh 后端不应触发 LLMProvider 探测")

        monkeypatch.setattr(session_api, "_no_llm_provider_reason", _boom)
        register(_FakeBackend("pi"))
        assert _options()["pi"].available is True


class TestDshAvailability:
    def test_probe_result_is_propagated_into_option(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """探测说不可用 → 选项置灰，原因原样透传给前端。"""
        monkeypatch.setattr(session_api, "_dsh_probe", lambda: (False, "未配置可用的 LLM 平台"))
        register(_FakeBackend("dsh"))
        dsh = _options()["dsh"]
        assert dsh.available is False
        assert dsh.reason == "未配置可用的 LLM 平台"

    def test_available_when_probe_is_clean(self) -> None:
        register(_FakeBackend("dsh"))
        dsh = _options()["dsh"]
        assert dsh.available is True
        assert dsh.reason == ""
        assert dsh.label == "DeepSeek Harness"


class TestDshProbe:
    """``_dsh_probe``：可用性的两条判据（SDK 在不在 / 有没有可用 LLMProvider）。

    这里要测的是**真实** ``_dsh_probe``，而模块级 autouse 夹具正好把它换成了
    ``lambda: (True, "")``。每个用例先 ``monkeypatch.undo()`` 澈掉那条桩（连同
    它已记录的撤销），再打自己的桩——否则实测探测不到任何东西、四条用例全部
    假绿（踩过：断言 `available is False` 反而报 True）。
    """

    def test_missing_sdk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.undo()
        monkeypatch.setattr(session_api.importlib.util, "find_spec", lambda name: None)
        available, reason = session_api._dsh_probe()
        assert available is False
        assert "SDK" in reason

    def test_sdk_present_but_no_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.undo()
        monkeypatch.setattr(session_api.importlib.util, "find_spec", lambda name: object())
        monkeypatch.setattr(session_api, "_no_llm_provider_reason", lambda: "未配置可用的 LLM 平台")
        assert session_api._dsh_probe() == (False, "未配置可用的 LLM 平台")

    def test_sdk_present_and_provider_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.undo()
        monkeypatch.setattr(session_api.importlib.util, "find_spec", lambda name: object())
        monkeypatch.setattr(session_api, "_no_llm_provider_reason", lambda: "")
        assert session_api._dsh_probe() == (True, "")

    def test_unregistered_dsh_still_listed_and_greyed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """没注册 ≠ 没有这个后端：置灰 + 原因，用户知道该去装什么。"""
        # 真实 DshBackend 是否注册取决于同进程其他用例（注册表是全局的）：
        # 抹掉它，否则本机装了 SDK 时这里会跑到「已注册」分支上。
        real_kinds = registry_module.available_kinds
        monkeypatch.setattr(registry_module, "available_kinds", lambda: [k for k in real_kinds() if k != "dsh"])
        monkeypatch.setattr(session_api, "available_backend_kinds", registry_module.available_kinds)
        register(_FakeBackend("pi"))
        dsh = _options()["dsh"]
        assert dsh.available is False
        assert "DshBackend" in dsh.reason
        # 未注册时拿不到能力声明：空 dict 而不是编造一份全 True
        assert dsh.capabilities == {}


class TestLlmProviderReason:
    """``_no_llm_provider_reason``：可用性判据的单一来源（勾 ``_load_provider``）。"""

    @staticmethod
    def _patch_provider(monkeypatch: pytest.MonkeyPatch, provider: Any, models: list[str]) -> None:
        import apps.agent.pi.model_config as model_config

        monkeypatch.setattr(model_config, "_load_provider", lambda *a, **kw: provider)
        monkeypatch.setattr(model_config, "_provider_models", lambda p: models)

    def test_no_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_provider(monkeypatch, None, [])
        assert "LLMProvider" in session_api._no_llm_provider_reason()

    def test_provider_without_models(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_provider(monkeypatch, _FakeProvider(), [])
        assert "默认模型" in session_api._no_llm_provider_reason()

    def test_ready_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_provider(monkeypatch, _FakeProvider(), ["test-model"])
        assert session_api._no_llm_provider_reason() == ""


class TestRoute:
    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_endpoint_returns_list(self) -> None:
        """端点本体（含 ``sync_to_async`` 摆渡）能跑通并返回 schema 列表。

        探测已被夹具打桩成「可用」，所以不需要真实 LLMProvider 配置。
        """
        register(_FakeBackend("pi"))
        options = await session_api.list_backends(request=None)
        # 未注册的 dsh 也以置灰条目出现（见 _collect_backend_options）；其余条目来自
        # ``ensure_registered()`` 补上的真实内置后端，所以只断言这两条存在。
        kinds = {o.kind for o in options}
        assert {"dsh", "pi"} <= kinds
        assert all(isinstance(o, BackendOptionOut) for o in options)

    def test_route_registered_on_agent_prefix(self) -> None:
        """路径拼法：router 挂在 ``/agent`` 下，所以前端取的是 ``agent/backends``。"""
        path_view = session_api.router.path_operations["/backends"]
        assert [op.methods for op in path_view.operations] == [["GET"]]
        assert [op.path for op in path_view.operations] == ["/backends"]


class TestModelsPerKind:
    """模型清单按运行时收窄：claude-agent 只给 Anthropic 协议模型（前端据此过滤下拉）。"""

    _PLATFORM = ["glm53", "kimi-2.6(Anthropic)", "kimi-2.6"]

    def _patch_models(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(session_api, "_available_models", lambda: list(self._PLATFORM))

    def test_claude_agent_only_gets_anthropic_models(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_models(monkeypatch)
        register(_FakeBackend("claude-agent"))
        option = _options()["claude-agent"]
        assert option.models == ["kimi-2.6(Anthropic)"]
        # 预填的默认模型也必须是能用的那个，不是平台清单第一项
        assert option.default_model == "kimi-2.6(Anthropic)"

    def test_claude_agent_without_anthropic_models_gets_empty_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(session_api, "_available_models", lambda: ["glm53", "kimi-2.6"])
        register(_FakeBackend("claude-agent"))
        option = _options()["claude-agent"]
        assert option.models == []
        assert option.default_model is None

    def test_other_backends_keep_the_full_platform_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_models(monkeypatch)
        register(_FakeBackend("pi"))
        assert _options()["pi"].models == self._PLATFORM

    def test_filter_shares_the_backend_marker(self) -> None:
        """判据取自 claude_agent_backend 的常量，不是这里另写一份字面量。"""
        from apps.agent.backends.claude_agent_backend import ANTHROPIC_MODEL_MARKER

        assert session_api._models_for_kind("claude-agent", [f"x-{ANTHROPIC_MODEL_MARKER.upper()}", "y"]) == [
            f"x-{ANTHROPIC_MODEL_MARKER.upper()}"
        ]
