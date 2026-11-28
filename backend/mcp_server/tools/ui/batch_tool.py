"""``ui_action_batch`` —— 一句话做三件事，只弹一张审批卡（v2-C）。

## 为什么不在清单（manifest）里

清单里的每一条都必须有前端执行器、风险档、撤销能力（见 ``manifest.py`` 的模块 docstring），
而批量**自己不碰页面**：它是一层编排，真正动页面的是内层那几条清单动作。

## 为什么注解恒为 ``destructiveHint=True``

审批闸门判级看的是「被调用的那个工具」，而这里被调用的只有 ``ui_action_batch`` 一个名字，
按步判级做不到。批量里只要有一个写动作，整批就该被拦下弹一张卡，所以整批按最严的档走。
代价是纯读的一批也弹卡——宁可多一次确认，也不让「混在安全动作里的那个写动作」溜过去。

## 为什么注册函数单独一个模块、只导出名字

接线在 ``tools/ui/register.py``（主会话统一改，避免并发写同一个文件）：
``_register_ui_batch_tool(_t)`` 返回注册名，调用方并入工具名台账与分层清单。
``BATCH_TOOL_NAME`` 也从本模块转出——名字只有一处，``tool_tiers`` 那边 import 它而不是手抄
字符串，否则改名时「清单里有、模型调不到」会静默发生（这类漂移不报错、也不红）。

## 为什么写成「壳 + 设 ``__name__``」

``tests/ci/unit/mcp_server/test_tool_registration.py`` 把 ``mcp_server/tools/`` 下所有顶层
非下划线函数当成「该在 server.py 里注册的工具」，而本工具是动态注册的；写成顶层函数会被
那道门禁判成「定义了却没注册」。做法与 ``register.py`` 的 ``ui_action_results`` 一致。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from apps.agent.services.ui_action.batch import BATCH_TOOL_NAME, publish_batch
from mcp_server.identity import current_session_id

logger = logging.getLogger(__name__)

__all__ = ["BATCH_TOOL_NAME", "_register_ui_batch_tool"]


def _ui_action_batch_tool() -> Callable[..., Any]:
    """造 ``ui_action_batch`` 的壳：真签名 + 真 docstring，函数体只有一次整批下发。"""

    async def _call(
        steps: Annotated[
            list[dict[str, Any]],
            Field(
                description=(
                    "按执行顺序排列的步骤，1~5 步。每项形如 "
                    '{"action": "ui_navigate", "args": {"path": "/material-prep?stage=todo"}}；'
                    "action 只能是可用的 ui_* 动作名，args 按该动作的参数说明填。"
                )
            ),
        ],
        note: Annotated[
            str,
            Field(description="给律师看的一句话说明（显示在审批卡上，如「把材料页切到待处理再回案件」）。"),
        ] = "",
    ) -> dict[str, Any]:
        """把 2~5 个明确的页面操作合成一批：律师只审批一次，页面按顺序执行。

        **什么时候该用**：一句话里包含多个明确的页面操作，而且希望律师一次确认——典型如
        「打开材料预处理、切到待处理、再回案件页」。纯跳转/开面板/切筛选的小动作尤其适合：
        一次确认比五次快，律师的注意力比点击次数值钱。

        **什么时候不该用**：

        - 只有一步——直接调对应的单步动作，批量只会让审批卡变复杂；
        - 步骤之间有依赖、要先看前一步的结果才知道下一步做什么（先 ``ui_navigate`` 到材料页，
          再决定切哪个 stage）——分开调用，配合 ``ui_page_state`` 读回页面状态再决定；
        - 需要先查业务数据才知道该点哪——先用业务工具查清楚，再下发。

        **规则**：一批最多 5 步；每步 ``{"action": 动作名, "args": {...}}``；不能嵌套
        ``ui_action_batch``。任一步不合法，**整批一条都不会下发**（不会「能跑几条跑几条」），
        报错里会指明第几步错在哪，按那句话改完再调一次。

        **执行与结果**：律师批准后页面按顺序执行，**某一步失败就中止**，后面的步骤一律不执行。
        只有第一步等回执（整批等会拖成「卡住了」）：第一步的结果在 ``observed``，中间步骤的回执
        在 ``earlier_results``，最后一步稍后用 ``ui_action_results`` 取。拿到回执前不要断言
        页面已经变成什么样。
        """
        return await publish_batch(steps=steps, session_id=current_session_id() or None, note=note)

    tool: Any = _call
    # 工具真名 = ``__name__``：审批按 ``mcp__fachuan__<name>`` 全名匹配（同 ``register.py``）。
    tool.__name__ = BATCH_TOOL_NAME
    tool.__qualname__ = BATCH_TOOL_NAME
    return _call


def _register_ui_batch_tool(register_tool: Callable[..., Any]) -> str:
    """注册 ``ui_action_batch`` 并返回注册名（调用方并入工具名台账与分层清单）。

    ``destructiveHint=True`` 是**整批**的语义，理由见模块 docstring。
    """
    register_tool(_ui_action_batch_tool(), annotations=ToolAnnotations(destructive_hint=True))
    logger.info("ui 批量动作工具已注册: %s", BATCH_TOOL_NAME)
    return BATCH_TOOL_NAME
