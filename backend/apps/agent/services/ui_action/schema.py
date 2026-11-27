"""``ui_action`` 参数的**最小** JSON Schema 校验（双端校验的第一道）。

## 为什么不用 jsonschema 库

``jsonschema`` 在本仓库只是 ``mcp`` 的传递依赖（``backend/uv.lock`` 有、
``backend/pyproject.toml`` 没声明），直接 import 等于把「参数校验」的存亡挂在上游
某个包的依赖变更上。而本阶段清单里只用到四个关键字，所以手写 50 行：
**多支持一个关键字就多一个漂移点**——清单里出现不支持的写法时本模块会静默放行，
那比不校验更危险（看起来校验过了）。真要扩关键字，先扩这里。

## 失败返回文案而不是抛异常

模型看到的只有工具返回值。抛异常 → MCP 层包成一句「工具执行失败」，模型只能拿
同样的参数重试；返回「哪个字段错了」→ 模型下一步能改。
"""

from __future__ import annotations

from typing import Any

#: 只校验 ``type`` / ``enum`` / ``required`` / ``additionalProperties``。
#: ``bool`` 是 ``int`` 的子类，布尔值必须排除在 integer/number 之外，
#: 否则 ``{"stage": true}`` 会被当成合法整数放过去。
_TYPE_CHECKS: dict[str, Any] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
}


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    """校验一次工具调用参数；返回**第一条**错误文案，``None`` = 通过。"""
    if not isinstance(arguments, dict):
        return f"参数必须是 JSON 对象，收到 {type(arguments).__name__}"
    properties: dict[str, Any] = schema.get("properties") or {}
    if schema.get("additionalProperties") is False:
        unknown = [key for key in arguments if key not in properties]
        if unknown:
            allowed = "、".join(sorted(properties)) or "（无）"
            return f"不认识的参数：{'、'.join(unknown)}；允许的参数：{allowed}"
    for name in schema.get("required") or []:
        if name not in arguments:
            return f"缺少必填参数 {name}"
    for name, value in arguments.items():
        spec = properties.get(name)
        expected = (spec or {}).get("type")
        if expected in _TYPE_CHECKS and not _TYPE_CHECKS[expected](value):
            return f"参数 {name} 应为 {expected}，收到 {value!r}"
        allowed_values = (spec or {}).get("enum")
        if allowed_values is not None and value not in allowed_values:
            return f"参数 {name} 只能是 {'、'.join(map(str, allowed_values))}，收到 {value!r}"
    return None
