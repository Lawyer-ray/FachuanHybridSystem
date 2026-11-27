"""UI 动作的服务端效果核实 —— 「页面说成功」不等于「库里真的变了」。

## 为什么需要它

``outcome`` 的唯一来源是前端回执，也就是**页面自己说**它做完了。而在治理口径上，
客户端提交的结果只是线索，不是事实（对照 OpenAI Apps SDK「UI 调工具 → 服务器验证并
更新 → 服务器返回权威快照」、MCP「tools annotations are untrusted」、AG-UI「servers must
still reject client-supplied results for server-owned tools」）。法律场景里说错一次
「已归案」就是事故，所以「动作声称成功后，服务端自己去看一眼库」这一步必须存在。

## 核实只回答一个问题

「这个动作声称成功之后，库里真的长这样吗」。它**不**修数据、**不**回滚、**不**重试：
核实是读侧的事，写侧有各自的业务事务。三态结论与它们的含义见 ``AgentUiAction.verified``：

- ``True``：库里的样子与声称的目标一致；
- ``False``：页面报成功，但库里没变（模型必须改口径，不许对律师说已完成）；
- ``None``：**无法核实**（材料包不存在、没有草稿状态、核实器没登记、核实过程报错）。
  这是一个合法答案，不许退化成 ``False``——「我没看」和「我看了没变」是两件事。

## 注册方式

动作在清单里用 ``verify="<核实器名>"`` 声明（``manifest.UiAction.verify``），
本模块用 :func:`verifier` 注册同名函数。清单里只放**名字**、不放函数，理由与清单
「只放元数据」的同一条：``python -m apps.agent.services.ui_action --ts`` 要在没有
Django settings 的进程里 import 整个包，而核实器必然要碰模型。

## 核实绝不许抛异常

核实失败不能变成「这个动作失败了」——动作已经做完了，核实只是一份附加证据。
所以 :func:`run_verifier` 只 catch ``DatabaseError`` / ``ValueError`` / ``KeyError``
（仓库禁止扩大 ``except Exception``），warn 之后返回 ``verified=None``。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .manifest import UiAction

logger = logging.getLogger(__name__)

#: 核实结果的三态字段名（返回体与 ``AgentUiAction.verified`` 同一套词）。
VerificationFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

#: 核实器注册表：动作名 → 核实函数。核实函数只回答一件事——「这个动作声称成功后，
#: 库里真的长这样吗」。见模块 docstring 的三态口径。
VERIFIERS: dict[str, VerificationFn] = {}


def verifier(name: str) -> Callable[[VerificationFn], VerificationFn]:
    """把函数登记成 ``name`` 的核实器（重复登记直接覆盖）。

    覆盖而不是拒绝重复：测试要能用假的核实器换掉真那个（那正是「核实结论会不会被
    正确处理」唯一可测的办法），而进程启动期没有任何调用点会注册两次。
    """

    def register(func: VerificationFn) -> VerificationFn:
        VERIFIERS[name] = func
        return func

    return register


async def run_verifier(action: UiAction, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """跑一次核实，返回 ``{"verified": bool|None, "note": str, "observed": {...}}``。

    动作没声明 ``verify`` 时返回 ``None``：调用方（``publish_ui_action``）据此**一个字段
    都不加**，既有返回值契约逐字不变。

    核实器没登记时返回 ``verified=None`` 而不是 ``None``：那说明清单声明了核实能力却没
    接上实现，是配置错误——但对外仍是「无法核实」，不能因此把动作判成假成功。
    """
    if not action.verify:
        return None
    func = VERIFIERS.get(action.verify)
    if func is None:
        logger.warning("动作声明了核实器但没登记: action=%s verify=%s", action.name, action.verify)
        return {"verified": None, "note": f"无法核实：核实器 {action.verify} 未登记", "observed": {}}
    # 延迟 import：本模块要能在无 Django settings 的进程里被 import（见模块 docstring）。
    from django.db import DatabaseError

    try:
        return await func(arguments)
    except (DatabaseError, KeyError, ValueError):
        logger.warning(
            "UI 动作服务端核实失败（按无法核实处理，不影响下发结果）: action=%s verify=%s",
            action.name,
            action.verify,
            exc_info=True,
        )
        return {"verified": None, "note": "无法核实：核实过程出错", "observed": {}}


@verifier("material_prep_status")
async def material_prep_status(arguments: dict[str, Any]) -> dict[str, Any]:
    """核实 ``ui_material_prep_judge`` 是否真的把材料包判到了 ``target``。

    状态真相在 ``InboxMessage.draft_state["status"]``（与前端材料预处理同一份数据，
    见 ``apps/message_hub/models/inbox_message.py``）；参数名 ``packId`` / ``target``
    与清单里的 ``_JUDGE_ARGS`` 同名，不在这里另起一套词。

    ``draft_state`` 不是 dict（老消息 / 被别的链路写坏）或材料包根本不在了 → 无法核实。
    后者尤其不能判成 ``False``：包被删掉时「页面说它归案了」到底成没成，本核实器
    没有能力回答。
    """
    # 延迟 import：本模块要能在无 Django settings 的进程里被 import（见模块 docstring）。
    from apps.message_hub.models.inbox_message import InboxMessage

    raw_pack_id = arguments.get("packId")
    target = str(arguments.get("target") or "")
    if not isinstance(raw_pack_id, int):
        # 参数在清单的 schema 里是整数，但核实器是读侧的最后一环：拿到脏参数就回
        # 「无法核实」，而不是把 ``filter(pk=...)`` 的 ValueError 扔给上游。
        return {
            "verified": None,
            "note": f"无法核实：材料包标识 {raw_pack_id!r} 不是整数",
            "observed": {"packId": raw_pack_id},
        }
    pack_id = raw_pack_id
    pack = await InboxMessage.objects.filter(pk=pack_id).afirst()
    draft_state = pack.draft_state if pack is not None else None
    if not isinstance(draft_state, dict):
        return {
            "verified": None,
            "note": f"无法核实：材料包 {pack_id} 不存在或没有草稿状态",
            "observed": {"packId": pack_id},
        }
    actual = str(draft_state.get("status") or "")
    observed = {"packId": pack_id, "status": actual}
    if actual == target:
        return {"verified": True, "note": f"服务端核实通过：材料包 {pack_id} 当前状态 {actual}", "observed": observed}
    return {
        "verified": False,
        "note": f"页面报成功但服务端核实不通过：库里仍是 {actual or '空'}。不得对律师说已完成",
        "observed": observed,
    }
