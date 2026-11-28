"""``generated.ts`` 生成器 —— 清单 → 前端的动作名、描述、风险档、分层、撤销与参数 schema。

用法::

    python -m apps.agent.services.ui_action --ts > frontend/src/features/copilot/ui-tools/generated.ts

## 为什么必须生成而不是手写

清单是双端契约。手写前端那一份的失败形态是**静默的**：后端加了动作、前端没有对应
执行器，模型调完页面毫无反应，日志里连错误都没有。生成物 + 逐字节同源测试（08 §10
的 G1）才能在 CI 里拦住它——这是本文件存在的唯一理由。

## 为什么可以生成而不需要模板

照 ``apps/agent/sse_types.py`` 的范式：从 :data:`~.manifest.UI_ACTIONS` 反射，
不手抄任何字面量。差别只在输出目标——那里是 pydantic ``model_fields`` 拼 TS 联合类型，
这里是 dataclass 字段拼 ``UiToolName`` + ``UI_TOOL_SPECS`` + ``UI_TOOL_BY_NAME``。

## 为什么输出的是**全量**字段（而不是只给 name/title/risk/argsSchema）

前端 ``UiToolSpec`` 是冻结的完整形状（08 §2.3 的清单字段）：少了 ``describe`` /
``route`` / ``tier`` / ``handler`` / ``idempotent`` / ``undo``，前端执行层与治理测试
都编译不过，于是只能手抄一份顶住——而手抄那份就是第二个真相，同源测试立刻红。
所以这里一次吐全，前端从头到尾只有生成物。

## 确定性（两个要求）

1. 两次调用逐字节相同：动作按清单声明序，对象键排序输出（``additionalProperties``
   恒在 ``type`` 之前）、缩进固定 2 空格；否则每次重生成都产生无意义 diff，同源测试
   还会随机红。
2. 不依赖 Django / 环境变量：生成器只 import manifest（纯数据模块），
   在没有 settings 的 CI 生成阶段也能跑。
"""

from __future__ import annotations

import sys
from typing import Any

from .manifest import UI_ACTIONS, UiAction, UiActionRisk, UiActionTier, UiActionUndo

#: TS 侧同名联合类型的取值顺序（安全 → 危险，review 时一眼能看出档位边界）。
_RISK_VALUES: tuple[UiActionRisk, ...] = ("safe", "confirm", "guarded")
_TIER_VALUES: tuple[UiActionTier, ...] = ("direct", "deferred")
_UNDO_VALUES: tuple[UiActionUndo, ...] = ("nav", "toggle", "none")

_INDENT = "  "

#: 换行阈值（与前端 prettier 的 ``printWidth`` 同口径）：只为可读性服务。
#: 生成物是逐字节比对的，所以这条阈值一旦改动就是全文件重排——不是坏事，
#: 但要知道它属于「生成器的格式契约」，不属于任何一端的代码风格偏好。
_PRINT_WIDTH = 100

#: TS 单引号字符串里必须转义的字符。中文引号（「」、全角括号）不需要转义，
#: 所以不做 ``ensure_ascii`` 那类把中文变 ``\\uXXXX`` 的处理——生成物要能被人读。
_TS_ESCAPES = {"\\": "\\\\", "'": "\\'", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _ts_string(value: str) -> str:
    """Python 字符串 → TS 单引号字面量（与前端既有代码同一引号口径）。"""
    return "'" + "".join(_TS_ESCAPES.get(char, char) for char in value) + "'"


def _ts_value(value: Any, pad: str) -> str:
    """任意清单值 → TS 字面量（对象递归展开，键排序保证确定性）。"""
    if isinstance(value, dict):
        if not value:
            return "{}"
        # 键排序：schema 的书写顺序是「谁先写谁在前」，不该决定生成物的字节
        items = [
            f"{pad}{_INDENT}{key if key.isidentifier() else _ts_string(key)}: {_ts_value(item, pad + _INDENT)},"
            for key, item in sorted(value.items())
        ]
        return "{\n" + "\n".join(items) + f"\n{pad}}}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_ts_value(item, pad) for item in value) + "]"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return repr(value)
    return _ts_string(str(value))


def _ts_property(name: str, value: Any, pad: str) -> str:
    """一条 ``键: 值,``；长值（describe 是整句中文）折到下一行，跟着 prettier 的样子。"""
    source = _ts_value(value, pad)
    line = f"{pad}{name}: {source},"
    if "\n" in source or len(line) <= _PRINT_WIDTH:
        return line
    return f"{pad}{name}:\n{pad}{_INDENT}{source},"


def _ts_spec(action: UiAction) -> str:
    """一条动作 → ``UiToolSpec`` 对象字面量（字段顺序 = 前端接口声明序）。"""
    pad = _INDENT * 2
    body = [
        _ts_property("name", action.name, pad),
        _ts_property("title", action.title, pad),
        _ts_property("describe", action.describe, pad),
        _ts_property("argsSchema", action.args_schema, pad),
        _ts_property("route", action.route, pad),
        _ts_property("risk", action.risk, pad),
        _ts_property("tier", action.tier, pad),
        _ts_property("handler", action.handler, pad),
        _ts_property("idempotent", action.idempotent, pad),
        _ts_property("undo", action.undo, pad),
    ]
    return f"{_INDENT}{{\n" + "\n".join(body) + f"\n{_INDENT}}},"


def generate_ts() -> str:
    """生成 TypeScript 清单文件内容（从 :data:`~.manifest.UI_ACTIONS` 反射）。"""
    names = "\n".join(f"{_INDENT}| {_ts_string(action.name)}" for action in UI_ACTIONS)
    risks = " | ".join(_ts_string(value) for value in _RISK_VALUES)
    tiers = " | ".join(_ts_string(value) for value in _TIER_VALUES)
    undos = " | ".join(_ts_string(value) for value in _UNDO_VALUES)
    specs = "\n".join(_ts_spec(action) for action in UI_ACTIONS)
    return (
        "/**\n"
        " * UI 动作清单（自动生成，禁手改 —— python -m apps.agent.services.ui_action --ts）\n"
        " *\n"
        " * 后端单一来源：apps/agent/services/ui_action/manifest.py。\n"
        " * 改清单请改那里再重跑上面那条命令，**不要**手改本文件\n"
        " * （CI 的 test_ui_action_manifest_same_source.py 逐字节比对会红）。\n"
        " *\n"
        " * 生成器是反射而不是手写模板：动作名 / 描述 / 风险档 / 参数 schema 只有 manifest\n"
        " * 一个来源。手抄两份的漂移是静默的（后端有动作、前端没执行器 → 模型调完页面\n"
        " * 毫无反应、无报错）。\n"
        " */\n\n"
        "export type UiToolName =\n"
        f"{names}\n\n"
        "/**\n"
        " * 三档风险：`safe` 无外部副作用直接执行；`confirm` 走后端审批；\n"
        " * `guarded` 审批之后再要前端本地二次确认。\n"
        " */\n"
        f"export type UiToolRisk = {risks}\n\n"
        "/** 工具面分层：`deferred` 由 tool_search 加载后仍以真名调用（审批不受影响） */\n"
        f"export type UiToolTier = {tiers}\n\n"
        "/** 撤销能力：只覆盖 UI 状态（nav/toggle），业务写库一律 none */\n"
        f"export type UiToolUndo = {undos}\n\n"
        "export interface UiToolSpec {\n"
        "  name: UiToolName\n"
        "  /** 审批卡 / banner 上的中文名（别在组件里另起一套文案） */\n"
        "  title: string\n"
        "  /** 给模型看的「何时该用 / 何时不该用」，含反例 */\n"
        "  describe: string\n"
        "  /** 参数 JSON Schema（additionalProperties 恒为 false，前端据此做第二道守卫） */\n"
        "  argsSchema: Record<string, unknown>\n"
        "  /** 期望路由前缀；`null` = 任意页面 */\n"
        "  route: string | null\n"
        "  risk: UiToolRisk\n"
        "  tier: UiToolTier\n"
        "  /** 前端执行器 id（可读标签；执行分派按 name 走闭集，不靠它） */\n"
        "  handler: string\n"
        "  idempotent: boolean\n"
        "  undo: UiToolUndo\n"
        "}\n\n"
        "export const UI_TOOL_SPECS: readonly UiToolSpec[] = [\n"
        f"{specs}\n"
        "]\n\n"
        "/**\n"
        " * 名字 → 规格。执行器分派先查这张表再查 `UI_EXECUTORS`：\n"
        " * 两边都是闭集，`resolveExecutor` 因此能把「清单里没有的名字」判成 unknown_action，\n"
        " * 而不是拿 `undefined` 硬调（那是运行期 TypeError，日志里看不出是版本漂移）。\n"
        " */\n"
        "export const UI_TOOL_BY_NAME: Record<UiToolName, UiToolSpec> = Object.fromEntries(\n"
        "  UI_TOOL_SPECS.map((spec) => [spec.name, spec]),\n"
        ") as Record<UiToolName, UiToolSpec>\n"
    )


if __name__ == "__main__":
    if "--ts" in sys.argv:
        sys.stdout.write(generate_ts())
    else:
        sys.stdout.write("用法：python -m apps.agent.services.ui_action --ts\n")
