"""工具返回整形——list 信封化。

## 为什么

SDK(`func_metadata.py::_convert_to_content`)对 list 返回值会**逐项拆成
独立 TextContent**:

- 50 条记录 → 50 个无分隔的独立 JSON 文本块(pi 以 ``\\n`` 拼接,模型读到的
  不是 JSON 数组);
- **空列表 → 零内容块**——pi 的 ``textOf`` 产出空串,模型收到「成功的空气」,
  无法区分「没有结果」与「工具坏了」。

统一包成 ``{"total": N, "items": [...]}`` 单块 JSON:模型一眼看到条数,
空结果也有明确的 ``{"total": 0, "items": []}``。

## 用法

工具函数返回处 ``return list_result(rows)``,返回注解写
``-> dict[str, Any]``。契约测试(test_output_contract)按源码里的
``list_result(`` 标记识别信封工具,把后端响应包进信封再校验。
"""

from __future__ import annotations

from typing import Any


def list_result(items: list[Any], limit: int | None = None) -> dict[str, Any]:
    """把列表包成 {total, items} 信封,规避 SDK 的多块扁平化与空列表零内容。

    ``limit`` 提供时做客户端截断(pi 对工具输出 20KB 起腰斩,默认调用应留在
    截断线内):返回 ``{total, returned, truncated, items}``,``total`` 是完整
    条数——模型能看到「还有更多」而不是误以为看到了全量。
    """
    if limit is not None and len(items) > limit:
        return {
            "total": len(items),
            "returned": limit,
            "truncated": True,
            "items": items[:limit],
        }
    return {"total": len(items), "items": items}
