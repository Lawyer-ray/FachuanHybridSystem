"""UI 动作单源清单 —— 「AI 操作页面」这件事的唯一真相。

## 为什么必须是纯数据

同一份清单要喂给四个消费者：MCP 真名工具注册（后端）、前端类型与参数守卫
（``frontend/src/features/copilot/ui-tools/generated.ts``，由 :mod:`.__main__` 反射生成）、
工具分层表（``mcp_server/tool_tiers.py``）与审计白名单。任何一处手抄都会漂移，
而这类漂移的表现是**静默不动**：后端多了动作、前端没有对应执行器，模型调完页面
毫无反应，日志里连错误都没有。

所以这里只放元数据：**不 import Django、不 import mcp、不碰任何业务模块**，
``python -m apps.agent.services.ui_action --ts`` 才能在无 settings 的环境里跑。

## 为什么没有「怎么执行」

参数 → URL、怎么开面板、跨 feature 发哪条 window 事件，全是前端的知识（只有前端
知道路由表与组件边界）。清单里写执行细节的唯一结果是两端各演化一套口径。

## 本次范围（P0+P1）

只登记 3 条 ``safe`` 动作。``confirm`` / ``guarded`` 的枚举位已经就位
（:data:`UiActionRisk` 三值 + :data:`CONFIRM_ACTION_NAMES` 接口），写类动作留到
P2/P3——先把「能下发、不假装看见」这条管道跑通。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

#: 三档风险（不是两档）：``safe`` 无外部副作用；``confirm`` 单次写库/上传/触发 LLM，
#: 走后端审批；``guarded`` 对外系统/不可逆/涉及凭证，审批 + 前端本地二次确认。
UiActionRisk = Literal["safe", "confirm", "guarded"]
#: 工具面分层：``direct`` 直接声明给模型，``deferred`` 由 ``tool_search`` 加载后仍以真名调用。
UiActionTier = Literal["direct", "deferred"]
#: 撤销能力：``nav`` 浏览器前进/后退，``toggle`` 复位到动作前的值，``none`` 不可撤。
UiActionUndo = Literal["nav", "toggle", "none"]
#: 副作用标签（审计、预算与「破坏性工具必须可见」的政策判定共用一套词）。
UiActionSideEffect = Literal["write_db", "upload", "llm", "external", "credential", "delete"]


@dataclass(frozen=True)
class UiAction:
    """一条 UI 动作的元数据（字段见 08 §2.3）。"""

    #: MCP 工具短名（``ui_`` 前缀）；前端 ``UiToolName`` 与审批卡上的真名都用它
    name: str
    #: 审批卡 / banner 上的中文名
    title: str
    #: 给模型：何时该用、何时**不**该用（含反例，≤200 字）
    describe: str
    #: 参数 JSON Schema；``additionalProperties`` 恒为 False（模型生成多余参数要被拒）
    args_schema: dict[str, Any]
    #: 风险档 → 决定审批与前端二次确认（见 :data:`UiActionRisk`）
    risk: UiActionRisk
    #: 分层政策：``confirm`` / ``guarded`` **一律 direct**——律师要能一眼看见
    #: 「这个 AI 有破坏力」，把它们藏起来只降低可见性、不降低风险
    tier: UiActionTier
    #: 前端执行器 id（``ui-tools/registry.ts`` 的键）
    handler: str
    #: 期望路由前缀；前端据此判断动作是否落在当前页面（``None`` = 任意页面）
    route: str | None = None
    #: 执行前是否要带页面快照（T3 读回，本次全部 False）
    needs_snapshot: bool = False
    #: 撤销能力（只覆盖 UI 状态，业务写库不在此列）
    undo: UiActionUndo = "none"
    #: 副作用标签（空 = 无外部副作用，这是 ``safe`` 的定义）
    side_effects: tuple[UiActionSideEffect, ...] = ()
    #: 长任务：只发起，进度走既有轮询（本次全部 False）
    long_running: bool = False
    #: 同参数重复执行是否安全（决定前端能否重试：非幂等的写动作绝不自动重试）
    idempotent: bool = False


#: ``ui_navigate`` 的参数。路径白名单**不在后端**：本仓库的路由表只存在于前端
#: （``@/app/paths`` 的实例构造函数），后端再抄一份必然在改名时静默拒绝合法路径。
#: 所以后端只校验「是字符串且必填」，具体的站内路径校验由前端 ``ui-tools/routes.ts``
#: 做（双端校验的第二道，防旧前端执行新后端下发的路径）。
_NAVIGATE_ARGS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "站内路径，形如 /material-prep?stage=todo；不带域名与协议。",
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}

#: ``ui_copilot_open`` 的**可选**业务上下文，对齐动作盘点里 ``ui.copilot.open`` 的
#: 契约（``docs/analysis/ai-ui-action-2026-11-27/raw/07-ui-action-inventory.md:57``：
#: ``{"origin":"case"|"contract","refId":number,"title":string}``）。
#:
#: 三个都**可省**（``required`` 留空）：不带参数 = 普通打开（律师只是想开面板问句话），
#: 三项齐全 = 进入「业务内会话」，面板头部挂上对应案件/合同。前端的
#: ``CopilotLaunchContext``（``launch.ts:23-30``）要求三者齐全才认，缺一个自行降级为
#: 普通打开——把纯打开写成非法调用，等于让最常见的用法报错。
#:
#: 每个属性都必须带 ``description``：MCP 的 inputSchema 由参数注解反射生成，
#: 描述缺失时模型选参数值只能靠猜（``test_ui_tool_tiers`` 的 schema 门禁会红）。
_COPILOT_OPEN_ARGS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "origin": {
            "type": "string",
            "enum": ["case", "contract"],
            "description": "业务入口：case=案件内，contract=合同/委托内。",
        },
        "refId": {
            "type": "integer",
            "description": "对应业务 id（案件 id 或合同 id）。",
        },
        "title": {
            "type": "string",
            "description": "展示名（面板头部 chip 用，如客户/委托名）。",
        },
    },
    "required": [],
    "additionalProperties": False,
}

#: ``ui_material_prep_set_stage`` 的参数。枚举值来自前端的 ``PrepStage``
#: （``features/material-prep/stages.ts``：收件箱 + 材料包三态），后端不另立一套词。
_SET_STAGE_ARGS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stage": {
            "type": "string",
            "enum": ["inbox", "todo", "done", "filed"],
            "description": "inbox=收件箱，todo=待处理，done=已归案，filed=不接归档。",
        },
    },
    "required": ["stage"],
    "additionalProperties": False,
}


#: 唯一清单。**只放元数据**，声明序 = 文档序（生成物也按这个序，重生成才有稳定的 diff）。
UI_ACTIONS: tuple[UiAction, ...] = (
    UiAction(
        name="ui_navigate",
        title="跳转页面",
        describe=(
            "在应用内跳转到某个页面（只改 URL，不提交任何业务操作）。"
            "path 必须是站内路径，如 /material-prep?stage=todo。"
            "它不是浏览器：不能填表、不能调接口，也看不到跳转后页面的内容。"
        ),
        args_schema=_NAVIGATE_ARGS,
        risk="safe",
        tier="direct",
        handler="navigate",
        route=None,
        undo="nav",
        idempotent=True,
    ),
    UiAction(
        name="ui_copilot_open",
        title="打开 AI 助手面板",
        describe=(
            "把 AI 助手面板打开并置前（律师能在里面看到对话）。"
            "不带参数就是普通打开；origin/refId/title 三项齐全才算「业务内会话」，"
            "面板头部会挂上对应的案件/合同。"
            "它不发送消息、不切换会话，也不打开别的弹窗——用户要提问请直接回答，不要调它代替回答。"
        ),
        args_schema=_COPILOT_OPEN_ARGS,
        risk="safe",
        tier="direct",
        handler="openCopilot",
        route=None,
        undo="toggle",
        idempotent=True,
    ),
    UiAction(
        name="ui_material_prep_set_stage",
        title="切换材料预处理阶段",
        describe=(
            "把材料预处理页切到某个阶段（收件箱 / 待处理 / 已归案 / 不接归档）。"
            "只切视图筛选，不改材料包本身的状态；"
            "要真的把材料包归案或上传，请用对应的业务工具，不要用这个动作代替。"
        ),
        args_schema=_SET_STAGE_ARGS,
        risk="safe",
        tier="direct",
        handler="setMaterialPrepStage",
        route="/material-prep",
        undo="toggle",
        idempotent=True,
    ),
)


#: 需要人工审批的动作名（``confirm`` 档）。本次清单里没有 confirm 动作，故为空集。
#: 接口先立着：``mcp_server/tool_tiers.py`` 要把它们并进 ``DIRECT_TOOLS``——
#: 分层政策是「破坏性工具必须留在 direct」，而 ``DIRECT_PATTERNS`` 里的 ``delete_*``
#: 匹配不到 ``ui_delete_pack`` 这类名字，必须显式并入。
CONFIRM_ACTION_NAMES: frozenset[str] = frozenset(a.name for a in UI_ACTIONS if a.risk == "confirm")


#: 声明为 ``tier="direct"`` 的动作名。
#:
#: 为什么需要它：分层开关默认开（``mcp_server/tool_tiers.py:60``），服务端默认 exposure 是
#: ``deferred``（见 ``apps/agent/pi/shared_mcp.py`` 写 mcp.json 那一段）——**没列进
#: DIRECT_TOOLS 的工具不会声明给模型**，模型要先 ``tool_search`` 才知道有 ``ui_navigate``。
#: 而 ``ui_navigate`` / ``ui_copilot_open`` / ``set_stage`` 是“律师开口就要动页面”的高频动作，
#: 必须常驻可见（08 §2.2）。
#:
#: 一律从清单派生，而不是让 ``tool_tiers`` 手抄一遍名字：`tier` 写两处就是「装样子的
#: 单源」——2026-11-27 评审 P1-3 就是这么抓到清单说 direct、实际是 deferred 的。
DIRECT_ACTION_NAMES: frozenset[str] = frozenset(a.name for a in UI_ACTIONS if a.tier == "direct")
