"""续页合并的单元测试。

真实背景：一份 164 页银行卷宗里，LLM 把同一份《个人房产抵押贷款合同》
切成 p116-125 / p126-140 两段——p125 结尾是「3.9 还款账户…」，
p126 开头是「5.4 借款人应…办理抵押登记」，条款序号连续推进，中间没有新标题。

不合并的后果是归案后出现两个同名材料，且后续「按材料生成起诉状」会拿半份合同。

反面约束同样重要：**不能误合并**。同一卷宗里 p51-63 与 p64-69 都是
`bank_statement`（银行流水），但那是两个不同当事人的流水，必须分开。
所以「同类型 + 页相邻 + 长度相近」都不足以作为合并依据，必须有续页证据。
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.pdf_splitting.services.split import segment_merge


@dataclass
class _Seg:
    page_start: int
    page_end: int
    segment_type: str
    filename: str
    order: int = 0


class TestDocumentHeadingDetection:
    def test_detects_new_document_heading(self) -> None:
        assert segment_merge._looks_like_doc_heading("个人房产抵押贷款合同\n(适用于无开发商担保)")

    def test_detects_short_proof_heading(self) -> None:
        assert segment_merge._looks_like_doc_heading("收入证明\n兹证明丙某…")

    def test_clause_text_is_not_heading(self) -> None:
        assert not segment_merge._looks_like_doc_heading("5.4 借款人应在本合同签订后立即向有关登记机关办理抵押登记手续")

    def test_long_line_is_not_heading(self) -> None:
        """标题一般短；长句即便含「合同」也不当标题，避免漏合并。"""
        long_line = "本合同项下的担保范围包括但不限于主债权本金、利息、罚息、复利、违约金、损害赔偿金" * 2
        assert not segment_merge._looks_like_doc_heading(long_line)


class TestClauseNumber:
    def test_decimal_clause(self) -> None:
        assert segment_merge._clause_number("5.4 借款人应…") == 5.4

    def test_chinese_article(self) -> None:
        assert segment_merge._clause_number("第六条 保险") == 6.0

    def test_tail_clause(self) -> None:
        assert segment_merge._tail_clause_number("…3.8 变更还款账户…3.9 还款账户被冻") == 3.9

    def test_no_clause(self) -> None:
        assert segment_merge._clause_number("居民户口簿") is None


class TestShouldMerge:
    def test_real_contract_continuation(self) -> None:
        """真实案例：p125 结尾 3.9 → p126 开头 5.4，条款推进、无标题。"""
        prev = "3.8 借款人要求变更还款账户时，应由账户所有人提前提出申请。3.9 还款账户被有权机关冻结"
        nxt = "5.4 借款人应在本合同签订后立即向有关登记机关办理抵押登记手续"
        assert segment_merge.should_merge(prev, nxt, prev_pages=10, next_pages=15)

    def test_two_different_bank_statements_not_merged(self) -> None:
        """两份不同当事人的流水：即便同类型相邻，也不能合并。"""
        prev = "某银行借记卡交易明细 甲某 20230101 1000.00"
        nxt = "某银行借记卡交易明细 乙某 20230101 2000.00"
        assert not segment_merge.should_merge(prev, nxt, prev_pages=13, next_pages=6)

    def test_new_heading_blocks_merge(self) -> None:
        prev = "3.9 还款账户被冻结"
        nxt = "个人房产抵押贷款合同\n(适用于无开发商担保)"
        assert not segment_merge.should_merge(prev, nxt, prev_pages=5, next_pages=5)

    def test_clause_not_advancing_blocks_merge(self) -> None:
        """序号没推进说明可能是并列的另一份，不是续页。"""
        prev = "8.2 借款人有权提前还款"
        nxt = "3.1 本合同项下贷款用途为…"
        assert not segment_merge.should_merge(prev, nxt, prev_pages=5, next_pages=5)

    def test_oversized_merge_blocked(self) -> None:
        """合并后超过上限就不再合，防止把整本卷宗粘成一段。"""
        prev = "3.9 账户"
        nxt = "5.4 抵押登记"
        assert not segment_merge.should_merge(prev, nxt, prev_pages=segment_merge.MAX_MERGED_PAGES - 1, next_pages=5)


class TestMergeContinuationSegments:
    def test_merges_real_slip(self) -> None:
        segs = [
            _Seg(116, 125, "loan_contract", "个人房产抵押贷款合同.pdf", 0),
            _Seg(126, 140, "loan_contract", "个人房产抵押贷款合同.pdf", 1),
        ]
        pages = {125: "3.9 还款账户被有权机关冻结", 126: "5.4 借款人应办理抵押登记手续"}
        merged = segment_merge.merge_continuation_segments(segs, pages)

        assert len(merged) == 1
        assert (merged[0].page_start, merged[0].page_end) == (116, 140)

    def test_keeps_separate_statements(self) -> None:
        segs = [
            _Seg(51, 63, "bank_statement", "流水_甲.pdf", 0),
            _Seg(64, 69, "bank_statement", "流水_乙.pdf", 1),
        ]
        pages = {63: "某银行卡 甲某", 64: "某银行卡 乙某"}
        merged = segment_merge.merge_continuation_segments(segs, pages)

        assert len(merged) == 2

    def test_different_type_never_merges(self) -> None:
        segs = [
            _Seg(1, 5, "loan_contract", "合同.pdf", 0),
            _Seg(6, 9, "bank_statement", "流水.pdf", 1),
        ]
        pages = {5: "3.9 账户", 6: "5.4 抵押"}
        assert len(segment_merge.merge_continuation_segments(segs, pages)) == 2

    def test_non_adjacent_never_merges(self) -> None:
        """中间隔着别的材料时不能合并（页不相邻）。"""
        segs = [
            _Seg(1, 5, "loan_contract", "合同.pdf", 0),
            _Seg(8, 12, "loan_contract", "合同续.pdf", 1),
        ]
        pages = {5: "3.9 账户", 8: "5.4 抵押"}
        assert len(segment_merge.merge_continuation_segments(segs, pages)) == 2

    def test_orders_renumbered_after_merge(self) -> None:
        segs = [
            _Seg(1, 5, "loan_contract", "a.pdf", 0),
            _Seg(6, 10, "loan_contract", "a.pdf", 1),
            _Seg(11, 12, "party_identity", "b.pdf", 2),
        ]
        pages = {5: "3.9 账户", 6: "5.4 抵押", 11: "身份证"}
        merged = segment_merge.merge_continuation_segments(segs, pages)

        assert [item.order for item in merged] == list(range(len(merged)))

    def test_empty_and_single_unchanged(self) -> None:
        assert segment_merge.merge_continuation_segments([], {}) == []
        one = [_Seg(1, 3, "x", "a.pdf")]
        assert segment_merge.merge_continuation_segments(one, {}) == one
