"""UI 动作工具面门禁：真名注册 / 分层可见性 / 审批判级 / schema 预算（08 §10 G3、G4）。

## 为什么这四件事必须钉死

1. **分层**：``confirm`` / ``guarded`` 一旦落到 ``deferred``，律师在审批弹窗里看到的工具名
   与模型选的对不上，「这个 AI 有破坏力」这件事也不再可见——分层政策原文是「破坏性
   工具必须留在 direct」，而 ``DIRECT_PATTERNS`` 的 ``delete_*`` 匹配不到 ``ui_*`` 名字。
2. **名字**：FastMCP 的 ``ToolManager`` 按名字存 dict，撞名是**覆盖**、不报错——后注册
   的一方赢，审批对象可以被悄悄换掉（所以注册器撞名直接抛，见下）。
3. **预算**：ui 动作的 schema 是每轮重发的固定前缀，超预算就是每轮都付 token。
4. **判级**：注解写错方向只有一个症状——该审批的被放行（或反之），日志里看不出来。
   所以这里不比字符串，直接把注册出去的 ``ToolAnnotations`` 喂给 ``classify_risk``。

## 为什么用临时 ``MCPServer`` 而不是 ``mcp_server.server``

``mcp_server.server`` 一 import 就注册 441 个工具（不碰网络，但有进程级副作用、且慢）。
判级的输入只是「注册出去的那份 ``ToolAnnotations``」，所以把清单注册进一个空的
``MCPServer`` 拿到的就是与线上一致的 SDK 对象，再按审批层的转换口径查判级。
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from apps.agent.services.approval.annotations import _reset_annotation_cache, prime_annotation_cache
from apps.agent.services.approval.risk import MCP_TOOL_PREFIX, RiskLevel, classify_risk
from apps.agent.services.ui_action.manifest import (
    CONFIRM_ACTION_NAMES,
    DIRECT_ACTION_NAMES,
    UI_ACTIONS,
    UiAction,
    UiActionRisk,
)
from mcp_server.tool_tiers import DIRECT_PATTERNS, DIRECT_TOOLS, build_tool_exposure
from mcp_server.tools.ui.register import _register_actions

_SERVER_PY = Path(__file__).resolve().parents[4] / "mcp_server" / "server.py"

#: 全部 ui 动作 ``args_schema`` 的序列化预算（08 §10 G4：约 1000 token 的固定前缀）。
_SCHEMA_BUDGET_BYTES = 4096
#: 动作数硬上限（同 G4；软上限 20）。
_ACTION_LIMIT = 24


def _is_direct(name: str) -> bool:
    """与 pi 的 ``toolExposure`` 匹配口径一致（精确名优先，模式按 ``*`` 通配）。"""
    if name in DIRECT_TOOLS:
        return True
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in DIRECT_PATTERNS)


def _approval_hints(tool: Any) -> dict[str, Any]:
    """SDK 的 ``ToolAnnotations`` → 审批层读得懂的 dict。

    与 ``apps/agent/services/approval/annotations.py::_annotation_table`` 同一口径
    （三个 snake_case 键 + ``getattr``）。**不能把对象直接喂给 ``classify_risk``**：
    ``risk.py::_classify_by_annotations`` 调的是 ``annotations.get(...)``，对象没有
    ``get`` 会 ``AttributeError``——线上审批链也是先经这层转换再判级，所以这里复刻它。
    """
    annotations = tool.annotations
    return {
        "read_only_hint": getattr(annotations, "read_only_hint", None),
        "destructive_hint": getattr(annotations, "destructive_hint", None),
        "open_world_hint": getattr(annotations, "open_world_hint", None),
    }


def _register_into_probe(actions: Sequence[UiAction]) -> list[Any]:
    """把动作注册进一个空的 ``MCPServer``，返回 SDK 生成的工具对象。"""
    probe = MCPServer("ui-tools-probe")

    def _register(tool: Any, *, annotations: ToolAnnotations | None = None) -> Any:
        return probe.tool(annotations=annotations)(tool)

    _register_actions(actions, _register, reserved_names=set())
    return asyncio.run(probe.list_tools())


def _synthetic(name: str, risk: UiActionRisk) -> UiAction:
    """造一条最小动作：清单里还没有 ``confirm`` / ``guarded`` 真名，但映射必须实测。

    名字刻意不含任何危险前缀——判级只能靠 ``destructiveHint`` 抬起来，
    否则测到的是名字黑名单而不是注解映射。
    """
    return UiAction(
        name=name,
        title="合成动作",
        describe="仅供判级映射测试",
        args_schema={"type": "object", "properties": {}, "additionalProperties": False},
        risk=risk,
        tier="direct",
        handler="synthetic",
    )


@pytest.fixture
def classify_registered() -> Iterator[Callable[[Sequence[UiAction]], dict[str, RiskLevel]]]:
    """注册给定动作 → 按审批口径判级；用完清空注解缓存，不污染同进程其他用例。"""

    def _classify(actions: Sequence[UiAction]) -> dict[str, RiskLevel]:
        tools = _register_into_probe(actions)
        prime_annotation_cache({tool.name: _approval_hints(tool) for tool in tools})
        return {tool.name: classify_risk(f"{MCP_TOOL_PREFIX}{tool.name}", {}) for tool in tools}

    yield _classify
    _reset_annotation_cache()


class TestTierVisibility:
    """分层政策：破坏性动作必须直连，让律师和模型都看得见。"""

    def test_confirm_and_guarded_are_direct(self) -> None:
        hidden = sorted(
            action.name for action in UI_ACTIONS if action.risk in ("confirm", "guarded") and not _is_direct(action.name)
        )
        assert not hidden, f"这些 UI 动作被分层藏起来了（律师将看不到 AI 的破坏力）: {hidden}"

    def test_confirm_names_merged_into_direct_tools(self) -> None:
        """通路本身要在：模式 ``delete_*`` 匹配不到 ``ui_*``，只能显式并。"""
        assert CONFIRM_ACTION_NAMES <= DIRECT_TOOLS

    def test_confirm_names_appear_in_exposure_mapping(self) -> None:
        mapping = build_tool_exposure()
        missing = sorted(name for name in CONFIRM_ACTION_NAMES if mapping.get(name) != "direct")
        assert not missing, f"``build_tool_exposure()`` 里没有这些 confirm 动作: {missing}"

    def test_direct_tier_actions_are_really_direct(self) -> None:
        """清单声明 ``tier="direct"`` 就必须真在 DIRECT_TOOLS 里（评审 P1-3）。

        分层开关默认开，服务端默认 exposure 是 ``deferred``：名单里没有的工具**不声明给
        模型**，律师说“打开待处理”时模型根本不知道有 ``ui_material_prep_set_stage``，
        要先 ``tool_search`` 才行。而清单里那个 ``tier`` 字段如果没人读，它就是个装饰——
        2026-11-27 评审就是这样抓到“三条动作全落 deferred”的。
        """
        declared = {action.name for action in UI_ACTIONS if action.tier == "direct"}
        assert declared == set(DIRECT_ACTION_NAMES), "DIRECT_ACTION_NAMES 必须从清单派生，不得手抄"
        mapping = build_tool_exposure()
        missing = sorted(name for name in declared if mapping.get(name) != "direct")
        assert not missing, f"声明了 direct 但实际按需加载（模型看不见）: {missing}"


class TestConfirmVisibilityGate:
    """G1：``confirm`` / ``guarded`` 在**真实** ``build_tool_exposure()`` 里必须是 ``direct``。

    为什么不并进 :class:`TestTierVisibility`：那里的两条查的是 ``DIRECT_TOOLS`` 与通配
    模式，没有任何 ``confirm`` 动作时循环体**空转**——绿，但什么也没验证。所以这里显式
    要求“至少有一条 confirm 动作参与”，否则清单被误删、或被误降级成 deferred 都无人发觉。
    """

    def test_at_least_one_confirm_action_participates(self) -> None:
        confirm = [action for action in UI_ACTIONS if action.risk == "confirm"]
        assert confirm, "清单里一条 confirm 动作都没有：下面那条门禁会变成空转的假绿"
        deferred = sorted(action.name for action in confirm if action.tier != "direct")
        assert not deferred, f'confirm 动作必须 tier="direct"（藏起来只降低可见性、不降低风险）: {deferred}'

    def test_confirm_and_guarded_are_direct_in_real_exposure(self) -> None:
        risky = [action for action in UI_ACTIONS if action.risk in ("confirm", "guarded")]
        assert any(action.risk == "confirm" for action in risky), "没有 confirm 动作参与，这条门禁是空跑"
        mapping = build_tool_exposure()
        hidden = sorted(action.name for action in risky if mapping.get(action.name) != "direct")
        assert not hidden, (
            f"这些动作在真实 toolExposure 里不是 direct（模型看不见、律师也看不到 AI 的破坏力）: {hidden}"
        )


class TestNames:
    """名字是审批与审计的匹配键，撞名/怪字符都是静默错对象。"""

    def test_names_are_ui_prefixed(self) -> None:
        bad = sorted(action.name for action in UI_ACTIONS if not action.name.startswith("ui_"))
        assert not bad, f"UI 动作名必须以 ui_ 开头（与业务工具区分、也让分层好认）: {bad}"

    def test_names_are_unique(self) -> None:
        names = [action.name for action in UI_ACTIONS]
        assert len(names) == len(set(names)), f"UI 动作名重复，后注册的会覆盖前一个: {names}"

    def test_action_count_within_limit(self) -> None:
        assert len(UI_ACTIONS) <= _ACTION_LIMIT, f"UI 动作数 {len(UI_ACTIONS)} 超过硬上限 {_ACTION_LIMIT}"

    def test_collision_with_builtin_raises(self) -> None:
        """撞名当场抛，不静默覆盖：内置工具是审批与审计口径的基准对象。"""
        action = UI_ACTIONS[0]
        with pytest.raises(RuntimeError, match="撞名"):
            _register_actions([action], lambda tool, *, annotations=None: tool, reserved_names={action.name})

    def test_duplicate_names_in_catalog_raise(self) -> None:
        action = UI_ACTIONS[0]
        with pytest.raises(RuntimeError, match="重复登记"):
            _register_actions([action, action], lambda tool, *, annotations=None: tool, reserved_names=set())


class TestRegisteredSchema:
    """``__signature__`` 反射链路：schema 里必须是真参数，不能退化成无约束对象。"""

    def test_schema_carries_parameters_and_descriptions(self) -> None:
        tools = {tool.name: tool for tool in _register_into_probe(UI_ACTIONS)}
        for action in UI_ACTIONS:
            schema = tools[action.name].input_schema
            properties = schema.get("properties") or {}
            declared: dict[str, Any] = action.args_schema.get("properties") or {}
            assert set(properties) == set(declared), f"{action.name} 的参数表与清单不一致: {sorted(properties)}"
            assert set(schema.get("required") or []) == set(action.args_schema.get("required") or []), (
                f"{action.name} 的必填参数与清单不一致"
            )
            for name, spec in declared.items():
                assert properties[name].get("description") == spec.get("description"), (
                    f"{action.name}.{name} 的描述没进 schema——模型选参数值时看的就是它"
                )
                if spec.get("enum"):
                    assert properties[name].get("enum") == spec["enum"], f"{action.name}.{name} 的枚举没进 schema"


class TestSchemaBudget:
    def test_schema_bytes_within_budget(self) -> None:
        total = sum(
            len(json.dumps(action.args_schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            for action in UI_ACTIONS
        )
        assert total <= _SCHEMA_BUDGET_BYTES, f"UI 动作 schema 合计 {total} 字节，超预算 {_SCHEMA_BUDGET_BYTES}"


class TestRiskAnnotations:
    """判级映射实测：``safe → LOW``、``confirm/guarded → 至少 HIGH（需审批）``。"""

    def test_safe_actions_classify_low(self, classify_registered: Callable[..., dict[str, RiskLevel]]) -> None:
        levels = classify_registered(UI_ACTIONS)
        safe = [action.name for action in UI_ACTIONS if action.risk == "safe"]
        assert safe, "清单里没有 safe 动作，这条断言会变成空跑"
        assert {name: levels[name] for name in safe} == dict.fromkeys(safe, RiskLevel.LOW)

    def test_confirm_and_guarded_classify_at_least_high(
        self, classify_registered: Callable[..., dict[str, RiskLevel]]
    ) -> None:
        levels = classify_registered([_synthetic("ui_project_open", "confirm"), _synthetic("ui_oa_stamp", "guarded")])
        assert set(levels.values()) <= {RiskLevel.HIGH, RiskLevel.CRITICAL}, (
            f"confirm/guarded 动作必须落到「至少高级」（否则既有闸门不会拦截）: {levels}"
        )

    def test_same_name_without_annotation_stays_low(self) -> None:
        """负控：注解缺失时判级退回名字判定（``ui_*`` 不在写前缀里 → LOW）。

        同样是 ``ui_project_open``，只有 ``destructiveHint`` 能把它抬到需要审批。
        注册器哪天不再传 ``annotations``，本条不会红、上面那条会红——差别正是「静默放行」。
        """
        prime_annotation_cache({})
        try:
            assert classify_risk(f"{MCP_TOOL_PREFIX}ui_oa_stamp", {}) == RiskLevel.LOW
        finally:
            _reset_annotation_cache()


class TestServerWiring:
    """``server.py`` 必须真的调用注册器——工具「定义了却没注册」在本仓是常见静默失效。"""

    def test_server_registers_ui_tools_after_builtin_names(self) -> None:
        source = _SERVER_PY.read_text(encoding="utf-8")
        assert "_register_ui_tools(_t" in source, "server.py 没有调用 UI 动作注册器，模型将看不到 ui_* 工具"
        assert source.index("def _builtin_tool_names") < source.index("_register_ui_tools(_t"), (
            "注册必须在 _builtin_tool_names() 之后：撞名检查要以完整内置名单为基准"
        )

    def test_extra_direct_names_mirror_modules(self) -> None:
        """``tool_tiers`` 里手写的两个 UI 工具名必须与各自模块的常量一致。

        为什么手写而不是 import：``tool_tiers`` 在 Django 装配期就被 ``pi/shared_mcp``
        导入，而 ``state_tool`` 会拉起 snapshot 服务（Django 模型）——为一个常量把 import
        图变重不值得。漂移由这条测试守，而不是靠"记得同步"。
        """
        from mcp_server.tools.ui.batch_tool import BATCH_TOOL_NAME
        from mcp_server.tools.ui.state_tool import TOOL_NAME as STATE_TOOL_NAME

        assert BATCH_TOOL_NAME == "ui_action_batch"
        assert STATE_TOOL_NAME == "ui_page_state"
        assert {BATCH_TOOL_NAME, STATE_TOOL_NAME} <= DIRECT_TOOLS
        mapping = build_tool_exposure()
        for name in (BATCH_TOOL_NAME, STATE_TOOL_NAME):
            assert mapping.get(name) == "direct", f"{name} 必须是 direct（否则模型要先 tool_search）"
