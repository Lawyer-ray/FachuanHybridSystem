"""UI 动作批量下发（v2-C）—— 一句话做三件事，只弹一张审批卡。

审批疲劳（``07-ui-action-inventory.md`` R13）：模型经常要连做「打开材料页 → 切到待处理
→ 回到案件」这种三步小事，逐步下发就是逐步审批，律师要点三次「同意」，而真正需要他判断
的只有「这批动作整体要不要做」。批量把它压成一次：``ui_action_batch`` 自己带
``destructiveHint=True``，审批闸门在**调用之前**拦下并弹一张卡，``tool_args`` 里列着全部
步骤，卡上看得见「将执行 3 步」。

**整批校验，不「能跑几条跑几条」**：任一条不合法（动作不在清单、args 过不了 schema、嵌套批量、超 5
步）就一条都不发。部分执行的现场最难收拾——律师看到「前两个跳过了、第三个没动」，而模型手里只有
一个空回执，既不知道从哪一步重来，也不知道页面停在哪。

**只等第一步的回执**：``publish_ui_action`` 单次最多等 2s（``FACHUAN_UI_ACTION_ACK_WAIT``），五步各等
一次就是 10s，而这段等待发生在**模型循环内部**，律师端看到的是「卡住了」。所以第 2 步起传
``wait_seconds=0``：动作照旧按序下发，回执进 pending 表，模型想看后几步就调 ``ui_action_results``。

**batch_id / batch_index 由这里生成**：前端靠它认出「这些帧属于同一次确认」，才能串行执行、并在「停下」
时把同批剩余步骤一起终止（``frontend/src/features/copilot/store/ui-tools.ts``）。审批、判级、回执等待、
事件帧全在 :mod:`apps.agent.services.ui_action`（v2-A）：这里只做「整批校验 + 按序调它」，重抄一遍
publish 等于给 SSE 契约开第二个真相源。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from . import policy, publish_ui_action
from .manifest import UI_ACTIONS, UiAction
from .schema import validate_arguments

logger = logging.getLogger(__name__)

#: 一批最多几步：「一张卡上律师还能逐条读完」的上限，也是前端等待队列的上限。
MAX_BATCH_STEPS = 5
#: 批量工具自己的名字。``steps`` 里出现它 → 拒绝（嵌套批量会把「一张卡」变成「卡中卡」）。
BATCH_TOOL_NAME = "ui_action_batch"
#: 动作名 → 清单项（清单是闭集，唯一来源是 manifest，这里只建一次索引）。
_ACTIONS_BY_NAME: dict[str, UiAction] = {action.name: action for action in UI_ACTIONS}


def _available_actions() -> dict[str, UiAction]:
    """当前可用动作 = 清单 − 部署级 deny 名单（见 :mod:`.policy`）。

    每次校验都重新过滤而不是在 import 时冻结：deny 是部署级开关，冻结在 import 时会让
    「改了环境变量没生效」且看不出原因；而清单只有个位数条目，重建索引的成本可以忽略。
    被禁的动作走下面「不在可用清单里」的**既有**报错——不另造一句新文案，模型学到的
    修法不变（换成可用动作），也不必知道“被禁用”与“不存在”背后的区别。
    """
    return {name: action for name, action in _ACTIONS_BY_NAME.items() if not policy.is_denied(name)}


class BatchInvalid(ValueError):
    """整批被拒；``str(exc)`` 就是可以直接回给模型的那一句话。

    继承 ``ValueError`` 是刻意的：``server._t`` 只把 ``ValueError`` 翻成带文案的 ``ToolError``（→ ``isError``）；
    其它异常会被 SDK 包成 ``Error executing tool ...`` 并**丢掉原因**，而模型需要知道「第几步、错在哪」。
    """


def _args_of(step: Any) -> Any:
    """取一步的参数：``args`` 缺省 / ``None`` 当空对象；非对象原样返回交给 schema 报错。"""
    args = step.get("args") if isinstance(step, dict) else None
    return {} if args is None else args


def validate_batch(steps: Any) -> list[UiAction]:
    """逐条校验整批，返回按序的动作清单；任一条不合规则抛 :class:`BatchInvalid`。

    五类拒绝理由各给一句**能直接回给模型**的话：形状 / 步数 / 未知动作 / 嵌套批量 / 参数。
    """
    if not isinstance(steps, list) or not steps:
        raise BatchInvalid(
            f'steps 必须是非空数组，每项形如 {{"action": "ui_navigate", "args": {{"path": "/"}}}}；这次收到 {type(steps).__name__}。整批没有下发。'
        )
    if len(steps) > MAX_BATCH_STEPS:
        raise BatchInvalid(
            f"一批最多 {MAX_BATCH_STEPS} 步，这次给了 {len(steps)} 步。请拆成两批分别确认；整批没有下发。"
        )
    actions_by_name = _available_actions()
    actions: list[UiAction] = []
    for offset, step in enumerate(steps):
        label = f"第 {offset + 1} 步"
        if not isinstance(step, dict):
            raise BatchInvalid(f'{label}不是对象（应形如 {{"action": ..., "args": {{...}}}}）。整批没有下发。')
        name = step.get("action")
        if not isinstance(name, str) or not name:
            raise BatchInvalid(f"{label}缺少 action（动作名，字符串）。整批没有下发。")
        if name == BATCH_TOOL_NAME:
            raise BatchInvalid(
                f"{label}是 {BATCH_TOOL_NAME}：批量动作不能嵌套。请把内层步骤摊平到这一批里（仍最多 {MAX_BATCH_STEPS} 步）；整批没有下发。"
            )
        action = actions_by_name.get(name)
        if action is None:
            raise BatchInvalid(
                f"{label}的动作 {name} 不在可用清单里。可用动作：{'、'.join(sorted(actions_by_name))}。整批没有下发。"
            )
        error = validate_arguments(action.args_schema, _args_of(step))
        if error is not None:
            raise BatchInvalid(f"{label}（{name}）的参数不合法：{error}。整批没有下发。")
        actions.append(action)
    return actions


async def publish_batch(*, steps: Any, session_id: str | None, note: str = "") -> dict[str, Any]:
    """校验并按序下发整批，返回交给模型的整批结果。

    Returns:
        ``{"status": "dispatched", "batch_id", "steps": [{"action", "call_id", "index"}],
        "observed": 第一步的完整返回值}``；第一步就没送出去（``disabled`` / ``dry_run`` / ``no_channel``）
        时 ``status`` 就是那个状态、``steps`` 为空，后面的步骤一条都不发。每一步的结果都拿得到：
        第一步在 ``observed``，中间步骤在 ``earlier_results``，最后一步稍后用 ``ui_action_results`` 取。
    """
    actions = validate_batch(steps)
    batch_id = uuid.uuid4().hex
    dispatched: list[dict[str, Any]] = []
    earlier: list[str] = []
    first: dict[str, Any] = {}
    for index, action in enumerate(actions):
        step_result = await publish_ui_action(
            action=action,
            arguments=_args_of(steps[index]),
            session_id=session_id,
            batch_id=batch_id,
            batch_index=index,
            wait_seconds=None if index == 0 else 0,  # 只有第一步等回执（见模块 docstring）
        )
        status = str(step_result.get("status") or "")
        first = step_result if index == 0 else first
        if status != "dispatched":
            # 已发出的步骤不追回（页面已经按序执行了），剩下的步骤一条都不再发。
            logger.info(
                "ui_action batch 停在第 %d 步 session=%s batch=%s status=%s", index + 1, session_id, batch_id, status
            )
            return {
                "status": status,
                "batch_id": batch_id,
                "steps": dispatched,
                "observed": first,
                "note": (
                    f"第 {index + 1} 步没有下发成功（{status}），整批后面的步骤一条都没有发。先按 observed 处理；不要原样重复调用整批。"
                ),
            }
        dispatched.append({"action": action.name, "call_id": str(step_result.get("call_id") or ""), "index": index})
        earlier.extend(step_result.get("earlier_results") or [])
    logger.info(
        "ui_action batch dispatch session=%s batch=%s steps=%d note=%r", session_id, batch_id, len(dispatched), note
    )
    result: dict[str, Any] = {
        "status": "dispatched",
        "batch_id": batch_id,
        "steps": dispatched,
        "observed": first,
        "note": (
            f"整批 {len(dispatched)} 步已按序下发，只有第一步等了回执（见 observed）。后面几步的结果稍后用 ui_action_results 取；"
            "拿到回执前不要断言页面已经变成什么样。"
        ),
    }
    if earlier:
        result["earlier_results"] = [item for item in earlier if item]
    return result
