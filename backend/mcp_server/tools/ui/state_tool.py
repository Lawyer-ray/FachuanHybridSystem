"""``ui_page_state``：让模型先看清页面再说话（v2-B）。

## 为什么手写、不在 UI 动作清单里

清单里的每一条都必须有前端执行器、风险档与撤销能力；而「读页面状态」前端不参与执行（它只是
**答**一次读取），塞进清单会让 ``--ts`` 生成器造一条永远匹配不到执行器的动作，正好是
``register.py`` 开头那种静默失效。它与 ``ui_action_results`` 同属「手写但仍是 ``ui_*`` 一族」的工具。

## 为什么取舍写进 docstring、为什么写成「壳」

模型最容易犯的错是「能从后端查到的事实也去问页面」（案件、合同、材料都在库里，页面只是可能过期
的视图）。工具描述是它每轮唯一稳定的提示词位，所以取舍必须写在那里。壳 + 设 ``__name__`` 则是
因为 ``test_tool_registration`` 与审批都按工具真名对账，别名会让审批弹窗与模型选的名字对不上。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from apps.agent.services.ui_action import snapshot
from mcp_server.identity import current_session_id

logger = logging.getLogger(__name__)

#: 工具真名（审批按 ``mcp__fachuan__<name>`` 全名匹配，改名等于换一个审批对象）。
TOOL_NAME = "ui_page_state"

#: 各「没问到」结局给模型的一句话（问人 / 等一等 / 换工具）：混成同一句模型就分不清下一步。
_HINTS: dict[str, str] = {
    "no_channel": "当前没有可接收请求的页面（律师未打开会话）。改成直接问律师，不要假设页面内容。",
    "timeout": "律师可能没开页面（或在切换中），这次没问到。改成直接问他，不要假设页面内容。",
    "no_page_state": "页面在，但它没有声明结构化状态。改成问律师，或改用能查到数据的工具。",
}


def _ui_page_state_tool() -> Callable[..., Any]:
    """造 ``ui_page_state`` 的壳（真名 + 真 docstring），与 ``register.py`` 的 ``_tool_for`` 同形。"""

    async def _call(
        page: Annotated[
            str | None, Field(description="要读哪一页（如 material-prep）；省略 = 最近注册且已挂载的页面")
        ] = None,
    ) -> dict[str, Any]:
        """读取律师**当前页面上**的结构化状态（页面主动声明的那部分字段）。

        **什么时候该用**（两条同时成立）：律师说的是指代词（「这个页面」「我刚填的」
        「当前选中的那条」），而你不知道他指的是哪条记录 / 哪个 stage / 表单填到哪；
        且这些事实**只存在于浏览器里**（选中项、未提交的草稿、当前 tab）。

        **什么时候不该用**：

        - 能从后端查到的数据（案件 / 合同 / 材料 / 检索结果）——直接查库或调对应工具，
          页面只是它的一个视图，问页面等于绕远路，而且可能已经过期；
        - 律师问的是业务问题本身（怎么起诉、条款怎么写）——页面状态帮不上忙；
        - 同一轮刚看过快照——重复问只会白等最多 3 秒。

        **返回**：``{"status", "route", "state", "available_actions", "hint"?}``。

        - ``ok``：``state`` 是页面声明的那部分字段，可以据此回答或决定下一步动作；
          ``available_actions`` 是这页**此刻真能调**的动作名（如 ``ui_material_prep_judge``）
          ——有它就直接调那个工具，不用先瞎试一遍再改口；
        - ``no_page_state``：页面在，但它没声明结构化状态；``available_actions`` 仍可能是真的
          （页面只是没声明字段，并不是没有动作）；
        - ``timeout`` / ``no_channel``：**没问到**——这不等于页面是空的。这两种返回**没有**
          ``available_actions`` 键，所以「键不存在」只说明没问到，不能读成「这页没有可用动作」。
          改成直接问律师，绝不要把「没问到」当成「页面上没有」。

        Args:
            page: 要读哪一页（如 ``"material-prep"``）；省略 = 取最近注册且已挂载的页面。
        """
        result = await snapshot.request_snapshot(page, current_session_id() or None)
        hint = _HINTS.get(str(result.get("status")))
        if hint:
            result["hint"] = hint
        return result

    tool: Any = _call
    tool.__name__ = TOOL_NAME
    tool.__qualname__ = TOOL_NAME
    return _call


def register_ui_state_tool(register_tool: Callable[..., Any]) -> str:
    """注册 ``ui_page_state`` 并返回注册名（调用方并入工具名台账）；只读注解 → 判级退回名字判定。"""
    register_tool(_ui_page_state_tool(), annotations=ToolAnnotations(read_only_hint=True))
    logger.info("ui 页面状态工具已注册: %s", TOOL_NAME)
    return TOOL_NAME
