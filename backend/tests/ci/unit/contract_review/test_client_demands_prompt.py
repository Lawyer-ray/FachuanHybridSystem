"""客户特别交代 → 审查 prompt 的接线测试。

**为什么值得单独测**：客户交代是律师唯一能直接纠正 AI 方向的手段
（「这单一定要压工期」「预算不能再加」）。如果它只是在界面上被记住、
却没进 prompt，模型根本不知道——律师写了等于白写，而且看不出哪里错了。
同一坑踩过一次：前端只弹了个 toast，字段压根没传。
"""

from __future__ import annotations

from apps.contract_review.services.review.contract_reviewer import _build_revision_prompt

TEXT = "[段落0] 甲方应于合同签订后十日内支付全部款项。"


def _prompt(**kw: object) -> str:
    return _build_revision_prompt(TEXT, "party_a", "联胜酒店", "某装饰公司", **kw)  # type: ignore[arg-type]


class TestClientDemandsInPrompt:
    def test_chips_appear_in_prompt(self) -> None:
        p = _prompt(client_demands=["这单一定要压工期", "预算不能再加"])
        assert "这单一定要压工期" in p
        assert "预算不能再加" in p
        # 必须明确告诉模型这是最高优先级，否则会被当成背景信息忽略
        assert "客户特别交代" in p
        assert "必须给出修改建议" in p

    def test_free_text_note_appears_in_prompt(self) -> None:
        p = _prompt(client_note="付款节点太早，客户资金压力大")
        assert "付款节点太早，客户资金压力大" in p

    def test_blank_demands_add_no_section(self) -> None:
        """没写交代时不能凭空多出一段「客户特别交代（空）」，那会污染 prompt。"""
        p = _prompt()
        assert "客户特别交代" not in p
        p2 = _prompt(client_note="   ", client_demands=["", "  "])
        assert "客户特别交代" not in p2

    def test_party_stance_still_rendered(self) -> None:
        """加了交代段不能挤掉立场信息——方向首先由立场决定。"""
        p = _prompt(client_demands=["压工期"])
        assert "甲方" in p
        assert "联胜酒店" in p
        assert p.index("联胜酒店") < p.index("客户特别交代")
