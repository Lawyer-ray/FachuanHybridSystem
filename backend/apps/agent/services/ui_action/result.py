"""``publish_ui_action`` 的返回值装配与文案（v2-A）。

下发主流程在 :mod:`apps.agent.services.ui_action`；本模块只做一件事：把 ``ack`` 拿到的回执与
``verify`` 的核实结论拼成模型看得见的工具返回值，并把它写成模型不会读错的那一句话。
字段为什么这么分组见 :func:`_dispatched_result` 的 docstring。

**为什么模块顶层没有 Django 符号**：与 :mod:`.audit` 同一条纪律（完整论证见它的模块
docstring）——``python -m apps.agent.services.ui_action --ts`` 要在没有 Django settings 的
进程里 import 整个包；本模块顶层只 import stdlib 与包内模块，一个 Django 符号都不引。
"""

from __future__ import annotations

import logging
from typing import Any

from . import ack, audit, verify
from .manifest import UiAction

logger = logging.getLogger(__name__)


def _dispatched_result(
    *,
    call_id: str,
    delivered: bool,
    observed: dict[str, Any] | None,
    wait_seconds: float,
) -> dict[str, Any]:
    """``status=dispatched`` 的两种形态（拿到回执 / 没拿到）。

    分成一个函数而不是在 :func:`publish_ui_action` 里堆 if：这两组字段是**冻结契约**
    （前端与模型两侧照抄），分开写才能一眼看出「``observed=true`` 时多了哪些键、
    ``observed=false`` 时一个都不该有」。
    """
    if observed is None:
        return {
            "status": "dispatched",
            "call_id": call_id,
            "delivered": delivered,
            "observed": False,
            "pending": True,
            "note": _unobserved_note(delivered=delivered, wait_seconds=wait_seconds),
        }
    outcome = str(observed.get("outcome") or "unknown")
    result: dict[str, Any] = {
        "status": "dispatched",
        "call_id": call_id,
        "delivered": delivered,
        "observed": True,
        "outcome": outcome,
    }
    # ``code`` 只对 error 有意义：别的 outcome 带着 code，模型会把「中止」误读成路由故障。
    if outcome == "error":
        code = str(observed.get("code") or "").strip()
        if code:
            result["code"] = code
    location = str(observed.get("location") or "").strip()
    if location:
        result["location"] = location
    # note 放最后：契约里它就是最后一项，读返回值的人从字段一路读到这句话。
    result["note"] = _observed_note(outcome, observed)
    return result


async def _attach_verification(
    result: dict[str, Any],
    *,
    call_id: str,
    action: UiAction,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """拿到 ``ok`` 回执且动作声明了核实器时，把服务端核实结果拼进返回值并落库。

    **文案就是规格**：这是模型唯一能看到的信号。所以 ``note`` 必须把「已由服务端核实」
    与「页面报成功但服务端核实不通过，不要对律师说已完成」分开说——只说「成功」
    等于把前端的一句话当成事实转述给律师。

    核实器没声明（``action.verify`` 为空）或核实器返回 ``None`` 时**一个字段都不加**：
    既有返回值契约（前端与模型两侧照抄的冻结契约）逐字不变。
    """
    verification = await verify.run_verifier(action, arguments)
    if verification is None:
        return result
    verified = verification.get("verified")
    if not isinstance(verified, bool):
        verified = None
    verify_note = str(verification.get("note") or "")
    result["verified"] = verified
    result["verify_note"] = verify_note
    result["note"] = _verified_note(str(result.get("note") or ""), verified, verify_note)
    # 台账与返回值同源：两边各算一次核实就等于「模型看到的」与「事后查到的」可能不同。
    await audit.apply_verification(call_id, verified=verified, note=verify_note)
    logger.info(
        "ui_action verify action=%s call_id=%s verified=%s note=%s", action.name, call_id, verified, verify_note
    )
    return result


def _verified_note(observed_note: str, verified: bool | None, verify_note: str) -> str:
    """服务端核实结论 → 给模型的那句话（三种结论三种措词，不能合并）。

    ``verified=None`` 不能按 ``False`` 写：那时服务端**没看到**库，而不是看到了「没变」。
    两种情形的共同底线是不许断言已完成，所以两段话都以「不要说已完成」收口。
    """
    detail = f"（{verify_note}）" if verify_note else ""
    if verified is True:
        return f"{observed_note}已由服务端核实{detail}，可以基于事实陈述。"
    if verified is False:
        return (
            f"页面报成功，但服务端核实不通过{detail}。"
            "不要对律师说已完成——只能说页面回执显示成功，而服务端没看到对应的变化。"
        )
    return f"{observed_note}但服务端无法核实是否真的生效{detail}。不要说已完成，只能说页面回执显示成功。"


def _unobserved_note(*, delivered: bool, wait_seconds: float) -> str:
    """没拿到回执时的 note —— 三种情形文案必须不同，否则模型会替页面编结果。

    ``delivered`` 判据沿用 v1 的评审结论（P2-4）：没人收听时若仍说「已下发到当前页面」，
    模型就会向律师断言页面变了，而事实上可能根本没人看到。
    """
    if not delivered:
        return (
            "动作已发出，但当前没有页面在收听（律师可能没打开助手或已断开）；回执可能永远不会有。"
            "不要断言页面已经变化，可以提醒他打开后重试。"
        )
    if wait_seconds <= 0:
        return (
            f"动作已下发，但服务端当前不等待回执（{ack.ACK_WAIT_ENV}=0）。"
            "结果稍后可用 ui_action_results 取；拿到回执前不要断言页面已经变成什么样。"
        )
    return (
        f"动作已下发，但 {wait_seconds:g} 秒内没有收到页面回执（页面可能在切换中或律师没在看）。"
        "结果稍后可用 ui_action_results 取；拿到回执前不要断言页面已经变成什么样。"
    )


def _observed_note(outcome: str, observed: dict[str, Any]) -> str:
    """拿到回执时的 note —— 按 outcome 分叉，三种结局对模型的下一步含义完全不同。"""
    detail = str(observed.get("detail") or "").strip()
    location = str(observed.get("location") or "").strip()
    tail = f"（页面说明：{detail}）" if detail else ""
    if outcome == "ok":
        where = f"页面当前地址 {location}。" if location else ""
        return f"页面已执行该动作并回传结果：成功。{where}{tail}这一点现在可以基于事实陈述。"
    if outcome == "error":
        code = str(observed.get("code") or "unknown").strip()
        return f"页面执行该动作失败（{code}）。{tail}不要把这次动作说成已完成；可以据此换一条路或告诉律师没成功。"
    return f"页面中止了该动作（律师可能离开页面或手动取消）。{tail}不要断言页面已经变成什么样。"


def _describe_pending(item: dict[str, Any]) -> str:
    """一条积压结果 → 一句话。模型读人话比读嵌套 JSON 更不容易读错。"""
    action_name = str(item.get("action") or "未知动作")
    outcome = str(item.get("outcome") or "unknown")
    detail = str(item.get("detail") or "").strip()
    tail = f"（{detail}）" if detail else ""
    if outcome == "ok":
        location = str(item.get("location") or "").strip()
        return f"{action_name} 成功" + (f"，页面当前地址 {location}" if location else "")
    if outcome == "error":
        return f"{action_name} 失败（{item.get('code') or 'unknown'}）{tail}"
    if outcome == "aborted":
        return f"{action_name} 被页面中止{tail}"
    return f"{action_name} 结果未知（页面始终没有回执）"
