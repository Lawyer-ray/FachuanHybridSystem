"""部署级风险策略（``ui_action/policy.py``）：floor 只能加严、deny 只能减面。

为什么这些断言值得写：这两个环境变量是**事故现场**的唯一开关（改环境变量 + 重启，不发版），
而它们坏掉的方式全是「看着正常」：

- floor 非法值直接抛 → 整个进程起不来，比不加严更糟；
- floor 抬了档但注册器仍按清单档算注解 → 审批卡永远不弹，运维以为「今天很严」；
- deny 命中却仍然注册 → 模型照样调得到，「关掉了」是一句假话；
- deny 写错名字却没有任何声音 → 运维以为关掉了某动作，实际什么都没发生；
- deny 把批量清单忘了 → 单步调不到、批量还能下发，等于留了个后门；
- ``CONFIRM_ACTION_NAMES`` 不跟生效档走 → 分层清单（``tool_tiers``）把被抬档的动作藏起来。

本文件不建库：策略是纯数据/纯函数，注册用假 ``register_tool`` 收集名字（不起 MCP 服务）。
唯一的模块级副作用是 ``importlib.reload(manifest)``（``CONFIRM_ACTION_NAMES`` 是 import 期
派生的常量，不 reload 就测不到「按生效档派生」），用例用 ``try/finally`` 在复原环境后重算
一遍，不把抬高后的集合留给后面的用例。
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import Any, NamedTuple

import pytest
from mcp.types import ToolAnnotations

from apps.agent.services.ui_action import manifest as manifest_module
from apps.agent.services.ui_action import policy
from apps.agent.services.ui_action.batch import BatchInvalid, validate_batch
from apps.agent.services.ui_action.manifest import UI_ACTIONS, UiAction
from mcp_server.tools.ui.register import _register_actions, _register_ui_tools

#: 清单里的三条 ``safe`` 动作取一条做纯读样本。
NAVIGATE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_navigate")
#: 清单里唯一的 ``confirm`` 动作（写材料包归属）。
JUDGE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_material_prep_judge")


class _Registered(NamedTuple):
    """假注册口收到的一条：工具真名 + 注册时那份注解。"""

    name: str
    annotations: ToolAnnotations | None


def _collector() -> tuple[Callable[..., Any], list[_Registered]]:
    """造一个假的 ``register_tool``（与 ``server._t`` 同形：``(tool, *, annotations)``）。"""
    collected: list[_Registered] = []

    def _register(tool: Any, *, annotations: ToolAnnotations | None = None) -> Any:
        collected.append(_Registered(str(tool.__name__), annotations))
        return tool

    return _register, collected


@pytest.fixture(autouse=True)
def _clean_policy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例都从「默认策略」起跑：本机 shell 导出的 floor/deny 不许让用例变色。"""
    monkeypatch.delenv(policy.FLOOR_ENV, raising=False)
    monkeypatch.delenv(policy.DENY_ENV, raising=False)


# ---------------------------------------------------------------------------
# ① 默认：floor=safe、deny 空，清单档位原样生效
# ---------------------------------------------------------------------------


def test_default_policy_keeps_catalog_risks() -> None:
    """不设任何环境变量时，生效档 = 清单档；没有任何动作被禁。"""
    assert policy.risk_floor() == "safe"
    assert policy.denied_action_names() == frozenset()
    assert policy.effective_risk(NAVIGATE) == "safe"
    assert policy.effective_risk(JUDGE) == "confirm"
    assert not policy.escalated(NAVIGATE)
    assert not policy.escalated(JUDGE), "floor=safe 不许给任何动作降档或抬档"


# ---------------------------------------------------------------------------
# ② floor 抬档：生效档升高、确认集合跟着变、注解真的变 destructive
# ---------------------------------------------------------------------------


def test_floor_escalates_safe_action_and_confirm_names(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``floor=confirm`` 时 ``ui_navigate`` 的生效档变 confirm，且进 ``CONFIRM_ACTION_NAMES``。"""
    try:
        with monkeypatch.context() as scoped, caplog.at_level(logging.WARNING):
            scoped.setenv(policy.FLOOR_ENV, "confirm")

            assert policy.risk_floor() == "confirm"
            assert policy.effective_risk(NAVIGATE) == "confirm"
            assert policy.escalated(NAVIGATE) is True
            # 清单档已是 confirm 的动作不受影响（只升不降、也不重复告警）
            assert policy.effective_risk(JUDGE) == "confirm"
            assert policy.escalated(JUDGE) is False

            reloaded = importlib.reload(manifest_module)
            assert "ui_navigate" in reloaded.CONFIRM_ACTION_NAMES, (
                "CONFIRM_ACTION_NAMES 必须按生效档派生，否则 tool_tiers 会把被抬档的动作藏起来"
            )
            assert JUDGE.name in reloaded.CONFIRM_ACTION_NAMES

            # floor 是判级的输入：注册出去的注解必须是 destructive（否则审批卡不会弹）
            register, collected = _collector()
            _register_actions([NAVIGATE], register, reserved_names=set())
            assert [item.name for item in collected] == ["ui_navigate"]
            annotations = collected[0].annotations
            assert annotations is not None
            assert annotations.destructive_hint is True
            assert annotations.read_only_hint is not True
            assert any("抬高" in record.getMessage() for record in caplog.records), "抬档必须留一条可解释的日志"
    finally:
        # context 退出时环境已复原；重算一遍，别把抬高后的集合留给同进程的其它用例。
        restored = importlib.reload(manifest_module)
    assert set(restored.CONFIRM_ACTION_NAMES) == {JUDGE.name}, "策略复原后确认集合必须回到清单档"

    # guarded 档：同一套 max 逻辑，safe 动作直接抬到最高档
    monkeypatch.setenv(policy.FLOOR_ENV, "guarded")
    assert policy.effective_risk(NAVIGATE) == "guarded"


# ---------------------------------------------------------------------------
# ③ 非法 floor：兜底 safe 并告警（不能让写错一个字符把进程搞挂）
# ---------------------------------------------------------------------------


def test_invalid_floor_falls_back_to_safe_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(policy.FLOOR_ENV, "HIGH")

    with caplog.at_level(logging.WARNING, logger=policy.__name__):
        assert policy.risk_floor() == "safe"
        assert policy.effective_risk(NAVIGATE) == "safe"

    messages = [record.getMessage() for record in caplog.records]
    assert any(policy.FLOOR_ENV in message and "high" in message.lower() for message in messages), (
        f"非法 floor 必须告警（否则运维以为加严了）: {messages}"
    )


# ---------------------------------------------------------------------------
# ④ deny：不注册成工具、批量清单里也没有
# ---------------------------------------------------------------------------


def test_denied_action_is_not_registered_and_not_batchable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(policy.DENY_ENV, " ui_material_prep_judge ")

    assert policy.is_denied("ui_material_prep_judge") is True
    assert policy.is_denied("ui_navigate") is False
    assert policy.unknown_denied_names({action.name for action in UI_ACTIONS}) == ()

    register, collected = _collector()
    registered = _register_ui_tools(register, reserved_names=())
    assert "ui_material_prep_judge" not in registered
    assert "ui_material_prep_judge" not in [item.name for item in collected]
    # 其余动作与两个手写工具照常可用（deny 只砍名单里那一条）
    assert {"ui_navigate", "ui_copilot_open", "ui_material_prep_set_stage"} <= set(registered)
    assert {"ui_action_results", "ui_page_state", "ui_action_batch"} <= set(registered)

    with pytest.raises(BatchInvalid) as excinfo:
        validate_batch([{"action": "ui_material_prep_judge", "args": {"packId": 1, "target": "done"}}])
    message = str(excinfo.value)
    assert "不在可用清单里" in message, "被禁动作走既有报错，不另造新文案"
    available = message.split("可用动作：", 1)[1]
    assert "ui_material_prep_judge" not in available, "被禁动作不能出现在「可用动作」列表里"


# ---------------------------------------------------------------------------
# ⑤ deny 名单拼错：只告警不抛，且不误伤任何真实动作
# ---------------------------------------------------------------------------


def test_unknown_deny_name_only_warns(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    typo = "ui_material_prep_jugde"
    monkeypatch.setenv(policy.DENY_ENV, typo)

    with caplog.at_level(logging.WARNING, logger="mcp_server.tools.ui.register"):
        register, collected = _collector()
        registered = _register_ui_tools(register, reserved_names=())

    # 不抛、也不跳过任何真实动作
    assert {item.name for item in collected} == set(registered)
    assert {action.name for action in UI_ACTIONS} <= set(registered)
    assert policy.is_denied("ui_navigate") is False

    assert policy.unknown_denied_names({action.name for action in UI_ACTIONS}) == (typo,)
    messages = [record.getMessage() for record in caplog.records]
    assert any(typo in message and policy.DENY_ENV in message for message in messages), (
        f"拼错的 deny 名字必须告警（否则运维以为关掉了）: {messages}"
    )
