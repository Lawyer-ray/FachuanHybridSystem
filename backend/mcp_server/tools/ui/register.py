"""UI 动作 → MCP 真名工具（按清单动态注册）。

## 为什么一个工具名都不手写

名字 / 描述 / 参数 schema / 风险档的唯一来源是 ``apps/agent/services/ui_action/manifest.py``。
手写一份的漂移是**静默**的：清单加了动作、这里没跟上，模型调的工具根本不存在
（``test_tool_registration`` 只对账 server.py 里写死的 ``_t(fn)``，对这种手写不动它）；
反过来这里多写一条、前端没有执行器，则表现为「模型调完页面毫无反应、日志里连错误都没有」。
所以 :func:`_register_ui_tools` 只做一件事：把 ``UI_ACTIONS`` 逐条注册。

## 为什么签名是「真参数」而不是 ``**kwargs``

MCP 的 inputSchema 由函数签名生成（本仓从不手写 schema）。``**kwargs`` 会退化成无约束
对象，模型更容易生成非法参数，而「未知参数被静默忽略」正是
``tests/ci/unit/mcp_server/test_server_registration.py::TestSignatureHygiene`` 明令禁绝的
模式。本仓同时禁止 ``eval`` / ``exec``（拼源码 = 又开一处可执行面），所以这里用
:class:`inspect.Signature` 直接装配参数表挂到 ``__signature__``：不生成源码，SDK 通过
``inspect.signature`` 反射到的就是真参数（``server._t`` 的 ``functools.wraps`` 会把
``__signature__`` 一并带到它的包装函数上）。

## 为什么必须 ``async def``

共享 MCP 是**单进程**服务全所会话（``mcp_server/tool_tiers.py`` 的分层前提）。同步函数体
会在事件循环线程里跑，一个动作下发就钉住所有人的工具调用——与 ``tools/core/ask_user.py``
刻意写成 ``async`` 是同一条理由。函数体本身也只做一件事：把动作推给前端，**不等回执**。

## annotations → 审批判级

- ``safe`` → ``readOnlyHint=True``：判级退回名字判定（``ui_*`` 不在写前缀里 → LOW → 直通）；
- ``confirm`` / ``guarded`` → ``destructiveHint=True``：``risk.py::_classify_by_annotations``
  取「至少 HIGH」→ 既有闸门在工具体执行**之前**拦下并弹审批卡。

两个口径之间的桥是 ``apps/agent/services/approval/annotations.py::_annotation_table``：它把
SDK 的 ``ToolAnnotations`` **对象**转成 ``{"read_only_hint": …}`` 三键 dict，``risk.py`` 才读
得到（它调 ``annotations.get(...)``，直接喂对象会 ``AttributeError``）。所以这里只传对象、
**不要**再转一层 dict——MCP 注册只接受 ``ToolAnnotations``，转换各有各的边界。
判级的实测断言见 ``tests/ci/unit/mcp_server/test_ui_tool_tiers.py``。
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Iterable, Sequence
from typing import Annotated, Any, Literal

from mcp.types import ToolAnnotations
from pydantic import Field

from apps.agent.services.ui_action import publish_ui_action
from apps.agent.services.ui_action.manifest import UI_ACTIONS, UiAction
from mcp_server.identity import current_session_id

logger = logging.getLogger(__name__)

#: JSON Schema ``type`` → Python 注解。清单是手写的、只允许这几种类型；遇到没登记的
#: 类型退化成 ``Any``（schema 少一条类型约束，但工具照样可调，不会因新写法注册失败）。
_SCHEMA_TYPES: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict[str, Any],
    "array": list[Any],
}


def _annotations_for(risk: str) -> ToolAnnotations:
    """风险档 → MCP 注解（判级映射的唯一出口，理由见模块 docstring）。"""
    if risk == "safe":
        return ToolAnnotations(read_only_hint=True)
    return ToolAnnotations(destructive_hint=True)


def _parameter(name: str, spec: dict[str, Any], *, required: bool) -> inspect.Parameter:
    """一条 JSON Schema 属性 → 一个函数参数。

    描述与 ``enum`` 必须落进注解：pi 原样透传 inputSchema，模型选参数值时看的就是它
    （``test_schema_param_descriptions`` 的门禁口径）。``describe`` 里写再详细也替代不了
    「``stage`` 只能是这四个值」这种结构化约束。
    """
    annotation = _SCHEMA_TYPES.get(str(spec.get("type", "")), Any)
    enum_values = spec.get("enum")
    if enum_values:
        # ``Literal[("a", "b")]`` 是 ``Literal["a", "b"]`` 的运行期写法（typing 会摊平元组）。
        annotation = Literal[tuple(enum_values)]
    # 可选参数**不**与 ``None`` 求并：并集会把它变成
    # ``anyOf: [{type/enum}, {type: null}]``，模型看到的是「要么这个枚举、要么 null」，
    # 而它实际只需要「要么给合法值、要么别给」。JSON Schema 里的可选性由 ``required``
    # 表达（清单里没列名就是可选），这里的默认值只决定调用签名怎么填——MCP 把没传的
    # 一项补成 ``None`` 后由 ``_tool_for`` 过滤掉，不会流进参数校验。
    return inspect.Parameter(
        name,
        inspect.Parameter.KEYWORD_ONLY,
        annotation=Annotated[annotation, Field(description=str(spec.get("description", "")))],
        default=inspect.Parameter.empty if required else spec.get("default"),
    )


def _signature_for(action: UiAction) -> inspect.Signature:
    """按 ``args_schema`` 装配参数表（``additionalProperties=False`` → 只声明 properties）。"""
    properties: dict[str, Any] = action.args_schema.get("properties") or {}
    required = set(action.args_schema.get("required") or [])
    return inspect.Signature(
        parameters=[_parameter(name, spec, required=name in required) for name, spec in properties.items()],
    )


def _tool_for(action: UiAction) -> Callable[..., Any]:
    """造一条工具的「壳」：真签名 + 真 docstring，函数体只有一次下发。

    工具体里**不判级、不等待、不落库**：判级由审批闸门在调用前完成，执行结果不回传
    （理由见 ``apps/agent/services/ui_action/__init__.py`` 的模块 docstring）。
    """

    async def _call(**kwargs: Any) -> dict[str, Any]:
        # 丢掉值为 ``None`` 的键：MCP 的 ArgModel 会把**没传的**可选参数补成 None 后
        # 全量 dump 进 kwargs（``func_metadata`` 的 ``model_dump_one_level``），而 None
        # 在 ``args_schema`` 里是「类型不对」而不是「没传」——不过滤就会让
        # 「不带参数的普通打开」永远被判成 invalid_args，工具看似存在却从不生效。
        arguments = {key: value for key, value in kwargs.items() if value is not None}
        return await publish_ui_action(
            action=action,
            arguments=arguments,
            session_id=current_session_id() or None,
        )

    # 走 Any 视图再赋值：``__signature__`` 是解释器认的约定属性，Callable 类型上没声明；
    # 用 ``setattr`` 会被 ruff 的 B010 拦（常量属性名）。
    tool: Any = _call
    tool.__signature__ = _signature_for(action)
    # 工具真名 = ``__name__``：审批按 ``mcp__fachuan__<name>`` 全名匹配，别名会让审批
    # 弹窗里的名字与模型选的对不上。
    tool.__name__ = action.name
    tool.__qualname__ = action.name
    tool.__doc__ = action.describe
    return _call


def _register_actions(
    actions: Sequence[UiAction],
    register_tool: Callable[..., Any],
    *,
    reserved_names: Iterable[str],
) -> list[str]:
    """按给定动作逐条注册，返回注册名列表。

    ``actions`` 是参数而不是直接用 ``UI_ACTIONS``：``confirm`` / ``guarded`` 档在拿到真名
    动作之前也必须能实测判级（见 ``test_ui_tool_tiers`` 的合成动作）——判级只取决于
    注册出去的那份 ``ToolAnnotations``，与动作是否已在清单里无关。
    """
    reserved = set(reserved_names)
    registered: list[str] = []
    for action in actions:
        if action.name in reserved:
            # 静默覆盖会把一个内置工具（审批与审计口径的基准对象）换成一条下发动作。
            raise RuntimeError(f"UI 动作与既有工具撞名，拒绝注册: {action.name}")
        if action.name in registered:
            raise RuntimeError(f"UI 动作在清单里重复登记: {action.name}")
        register_tool(_tool_for(action), annotations=_annotations_for(action.risk))
        registered.append(action.name)
    if registered:
        logger.info("ui 工具已注册 %d 个: %s", len(registered), ", ".join(registered))
    return registered


def _register_ui_tools(
    register_tool: Callable[..., Any],
    *,
    reserved_names: Iterable[str] = (),
) -> list[str]:
    """把整份清单注册进 MCP；返回注册名列表（调用方并入工具名台账）。

    Args:
        register_tool: 主仓的统一注册口（``server._t``），以
            ``register_tool(func, annotations=...)`` 调用——与 ``plugin_tools`` 同一约定：
            传函数而不是让本模块 import ``server``，否则「导入本模块」就等于跑一遍
            441 个工具的注册。
        reserved_names: 已注册的内置工具名。撞名直接抛（不静默跳过）：UI 动作与内置
            工具撞名说明清单选错了名字，跳过会让「清单里有、模型调不到」变成静默事实。

    函数名带 ``_`` 前缀不是「私有」的意思：``mcp_server/tools/`` 下的非下划线顶层函数
    会被 ``test_tool_registration`` 当作「实现完整但从未注册的工具」。注册器不是工具，
    按该门禁 docstring 的约定用 ``_`` 命名，而不是往白名单里加一条逃生门。
    """
    return _register_actions(UI_ACTIONS, register_tool, reserved_names=reserved_names)
