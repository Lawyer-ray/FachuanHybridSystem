"""``tool_shaping.list_result`` 语义单元测试——53 个工具共用的信封约定。

三件事必须钉死(2026-10-25 信封化引入):
1. 空/非空列表都产出**单块** JSON(SDK 会把裸 list 逐项拆块、空列表变零内容);
2. limit 截断时 ``truncated=True`` 且 ``total`` 是**下界**(调用方按 limit+1
   探测,拿到 limit+1 条才置截断);
3. 未截断时 total 精确、无多余键。
"""

from __future__ import annotations

import json

from mcp_server.tool_shaping import list_result


class TestListResultEnvelope:
    def test_plain_list_envelope(self):
        out = list_result([{"id": 1}, {"id": 2}])
        assert out == {"total": 2, "items": [{"id": 1}, {"id": 2}]}
        assert "truncated" not in out, "未截断不应有 truncated 键"

    def test_empty_list_is_explicit_not_silent(self):
        # 空列表曾是零内容块(模型收到「成功的空气」)——信封后必须显式
        out = list_result([])
        assert out == {"total": 0, "items": []}

    def test_truncation_reports_lower_bound_total(self):
        # limit+1 探测:拿到 11 条、limit=10 → truncated + total=11(下界)
        rows = [{"id": i} for i in range(11)]
        out = list_result(rows, limit=10)
        assert out["truncated"] is True
        assert out["total"] == 11
        assert out["returned"] == 10
        assert len(out["items"]) == 10

    def test_limit_at_exact_count_not_truncated(self):
        out = list_result([{"id": 1}], limit=5)
        assert out == {"total": 1, "items": [{"id": 1}]}

    def test_limit_zero_guards(self):
        # limit=0 边界:不切出负数/空 items 也要结构合法
        out = list_result([{"id": 1}, {"id": 2}], limit=0)
        assert out["truncated"] is True
        assert out["items"] == []

    def test_serializes_as_single_json_object(self):
        # 信封必须是单块可解析 JSON(回归 SDK 扁平化)
        text = json.dumps(list_result([{"a": 1}]), ensure_ascii=False)
        assert json.loads(text)["items"] == [{"a": 1}]
