"""agent 后端可用性查询契约（前端切换器用）。

只描述「有哪些后端可选、各能不能用」——运行期行为仍归 ``backends`` 包。
"""

from __future__ import annotations

from typing import Any

from ninja import Schema


class BackendOptionOut(Schema):
    """一个可选 agent 后端（``GET /agent/backends`` 的列表项）。

    ``available`` 与 ``reason`` 是这个契约存在的理由：dsh 的 SDK / 运行时 /
    模型凭据任意一项缺失时，用户只能在**选了之后**报错——那时已经建了会话
    （``agent_kind`` 是会话级属性，建完不能改），只能换个后端重开。所以后端
    自检结果要能提前问出来，让选项置灰而不是让用户撞墙。

    能力字段是 :class:`apps.agent.backends.base.BackendCapabilities` 的逐项
    展开（而不是嵌套对象）：前端据此隐藏插话框、逐字动画等，嵌套一层只会让
    UI 里多写一层解引用。
    """

    #: 注册表里的 kind（同时也是 ``SessionIn.agent_kind`` 的合法取值）
    kind: str
    #: 给用户看的名字（"Pi" / "DeepSeek Harness"）
    label: str
    #: 一句话说明（切换器里的副标题；未注册的 kind 说明它是什么）
    description: str
    #: 现在能不能新建这个后端的会话。``False`` 时必须读 ``reason``。
    available: bool
    #: 不可用的原因（面向用户的中文短句；``available=True`` 时为空串）。
    reason: str
    #: 能力声明，见 ``BackendCapabilities`` 各字段注释。
    capabilities: dict[str, Any]
    #: 该后端可选的模型清单（来自启用的 ``LLMProvider``：``default_model`` +
    #: ``extra_models``）。空列表 = 不支持逐栏指定模型，前端不显示下拉。
    #: 三个后端最终都落到同一个 LiteLLM 网关，所以共用同一份清单是合理的；
    #: 若将来某后端有独占模型，在它自己的返回值里收窄，不要在这里加分支类型。
    models: list[str] = []
    #: 未指定模型时该后端会用的那个（UI 预填用）。
    #: ``None`` = 没有可用平台/默认模型，此时 ``models`` 也应为空。
    default_model: str | None = None
