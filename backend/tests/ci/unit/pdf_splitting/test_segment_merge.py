"""续页合并的单元测试。

真实背景：一份 164 页银行卷宗里，LLM 把同一份《个人房产抵押贷款合同》
切成 p116-125 / p126-140 两段——p125 结尾是「3.9 还款账户…」，
p126 开头是「5.4 借款人应…办理抵押登记」，条款序号连续推进，中间没有新标题。

不合并的后果是归案后出现两个同名材料，且后续「按材料生成起诉状」会拿半份合同。

反面约束同样重要：**不能误合并**。同一卷宗里 p51-63 与 p64-69 都是
`bank_statement`（银行流水），但那是两个不同当事人的流水，必须分开。
所以「同类型 + 页相邻 + 长度相近」都不足以作为合并依据，必须有续页证据。

判据双向修（P2-2）后新增的两组约束：
- 误并方向：解析不出序号、或两侧编号体系不同 → 一律不合并；
- 漏并方向：末页的金额/面积/日期/证号不是条款号，不能拿它们判「序号不推进」。
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
    confidence: float = 0.9
    review_flag: str = "normal"


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

    def test_重复件抬头仍是新材料开头(self) -> None:
        """实测 p105/p107 是同一份买卖合同的**两份重复件**（都从标题+当事人抬头
        重新开始），不是续页。抬头判据必须继续把它们分开。"""
        assert segment_merge._looks_like_doc_heading("房地产买卖合同\n本合同双方当事人：\n甲方(卖方): …")


class TestClauseRef:
    def test_decimal_clause(self) -> None:
        assert segment_merge._clause_ref("5.4 借款人应…") == (segment_merge.KIND_DECIMAL, 5.4)

    def test_chinese_article(self) -> None:
        assert segment_merge._clause_ref("第六条 保险") == (segment_merge.KIND_ARTICLE, 6.0)

    def test_arabic_article(self) -> None:
        assert segment_merge._clause_ref("第12条 保险") == (segment_merge.KIND_ARTICLE, 12.0)

    def test_中文顿号序号(self) -> None:
        assert segment_merge._clause_ref("一、甲方决定中途不卖") == (segment_merge.KIND_LIST, 1.0)
        assert segment_merge._clause_ref("十一、双方约定的其他事项：") == (segment_merge.KIND_LIST, 11.0)

    def test_阿拉伯顿号与括号序号(self) -> None:
        assert segment_merge._clause_ref("1、证据一") == (segment_merge.KIND_LIST, 1.0)
        assert segment_merge._clause_ref("（一）证据一") == (segment_merge.KIND_LIST, 1.0)
        assert segment_merge._clause_ref("(3) 证据三") == (segment_merge.KIND_LIST, 3.0)

    def test_no_clause(self) -> None:
        assert segment_merge._clause_ref("居民户口簿") is None
        assert segment_merge._clause_ref("") is None

    def test_首行不是序号就不算续页(self) -> None:
        """实测 p126 首行是半句话「金、损害赔偿金…」，没有序号——序号判据救不了它，
        这类续页交给边界二审（见 test_segment_boundary_review.py）。"""
        assert segment_merge._clause_ref("金、损害赔偿金和实现债权及抵押权的费用。") is None


class TestTailClauseRef:
    def test_tail_clause(self) -> None:
        text = "3.8 变更还款账户\n3.9 还款账户被冻"
        assert segment_merge._tail_clause_ref(text) == (segment_merge.KIND_DECIMAL, 3.9)

    def test_末页金额不被当条款号(self) -> None:
        """实测末页最后一个十进制数几乎总是表格里的金额（125493.76 / 15000.41）。"""
        text = "3.9 还款账户被有权机关冻结\n本页合计 125493.76\n卡可用余额 51,099.70"
        assert segment_merge._tail_clause_ref(text) == (segment_merge.KIND_DECIMAL, 3.9)

    def test_末页日期不被当条款号(self) -> None:
        assert segment_merge._tail_clause_ref("2.1 贷款用途\n签订日期 2024.01") == (segment_merge.KIND_DECIMAL, 2.1)

    def test_行首面积与金额也不当条款号(self) -> None:
        assert segment_merge._tail_clause_ref("用地分摊面积\n8.81m2 基底面积") is None
        assert segment_merge._tail_clause_ref("1.00 元") is None
        assert segment_merge._tail_clause_ref("1310000.00") is None

    def test_证号拼接不被当条款号(self) -> None:
        """实测 p110 把证号读成 1116075562.1116076，旧逻辑当成条款号 1.1e9。"""
        assert segment_merge._tail_clause_ref("62.1116075564号的《房地产权证》") is None

    def test_行首中文序号也能取到(self) -> None:
        text = "五、甲方决定中途不卖或逾期交付房地产时\n六、其他约定"
        assert segment_merge._tail_clause_ref(text) == (segment_merge.KIND_LIST, 6.0)

    def test_没有行首序号就是None(self) -> None:
        assert segment_merge._tail_clause_ref("某银行借记卡交易明细 甲某 20230101 1000.00") is None


class TestShouldMerge:
    def test_real_contract_continuation(self) -> None:
        """真实案例：p125 结尾 3.9 → p126 开头 5.4，条款推进、无标题。"""
        prev = "3.8 借款人要求变更还款账户时，应由账户所有人提前提出申请。3.9 还款账户被有权机关冻结"
        nxt = "5.4 借款人应在本合同签订后立即向有关登记机关办理抵押登记手续"
        assert segment_merge.should_merge(prev, nxt, prev_pages=10, next_pages=15)

    def test_末页带金额的真续页仍要合并(self) -> None:
        """漏并方向的回归：旧逻辑取到 125493.76 当条款号 → 判「不推进」→ 并不回。"""
        prev = "3.9 还款账户被有权机关冻结\n本页合计 125493.76"
        nxt = "5.4 借款人应在本合同签订后办理抵押登记手续"
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

    def test_中文序号回退不合并(self) -> None:
        """误并方向的回归：两份同类型清单，后一份从「一、」重新开始。
        旧逻辑解析不出中文序号 → 校验被跳过 → 两份被粘成一份。"""
        prev = "二、证据二\n三、证据三"
        nxt = "一、证据一\n二、证据二"
        assert not segment_merge.should_merge(prev, nxt, prev_pages=3, next_pages=3)

    def test_中文序号推进才合并(self) -> None:
        prev = "五、甲方决定中途不卖"
        nxt = "十一、双方约定的其他事项："
        assert segment_merge.should_merge(prev, nxt, prev_pages=2, next_pages=4)

    def test_前段解析不出序号就不合并(self) -> None:
        """误并方向：后段以「一、」开头但前段末页没有任何行首序号 →
        旧逻辑跳过校验直接合并，现在一律不合并。"""
        prev = "证据清单及明细\n序号 证据名称 证明内容\n1 借条 证明借款事实"
        nxt = "一、证据一\n二、证据二"
        assert not segment_merge.should_merge(prev, nxt, prev_pages=2, next_pages=2)

    def test_后段解析不出序号就不合并(self) -> None:
        prev = "3.9 还款账户被冻结"
        nxt = "兹证明甲某系我单位职工"
        assert not segment_merge.should_merge(prev, nxt, prev_pages=5, next_pages=1)

    def test_跨编号体系不合并(self) -> None:
        """条款 5.3 与列表「六、」不可比：跨体系比大小会误并两份不同材料。"""
        prev = "5.3 抵押担保的范围为本合同项下贷款本金及利息"
        nxt = "六、其他约定事项"
        assert not segment_merge.should_merge(prev, nxt, prev_pages=5, next_pages=5)

    def test_跨批长合同可以合并(self) -> None:
        """25 页/批，长合同被批界切成 25+25；旧的 40 页上限让它永不合并。"""
        prev = "3.9 还款账户被冻结"
        nxt = "5.4 借款人应办理抵押登记"
        assert segment_merge.should_merge(prev, nxt, prev_pages=25, next_pages=25)

    def test_oversized_merge_blocked(self) -> None:
        """合并后超过上限就不再合，防止把整本卷宗粘成一段。"""
        prev = "3.9 账户"
        nxt = "5.4 抵押登记"
        assert not segment_merge.should_merge(prev, nxt, prev_pages=segment_merge.MAX_MERGED_PAGES - 1, next_pages=5)

    def test_上限取值锁住(self) -> None:
        """80 ≈ 3 个分段批（25 页/批）+ 余量；改动要有依据，不能悄悄放开。"""
        assert segment_merge.MAX_MERGED_PAGES == 80


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

    def test_合并继承更差的复核标记与更低置信度(self) -> None:
        """B6 保守校准：半份高置信 + 半份低置信，合并后不能以 NORMAL 呈现，
        否则律师按低置信筛复核时正好漏掉这一段。"""
        segs = [
            _Seg(1, 5, "loan_contract", "a.pdf", 0, confidence=0.95, review_flag="normal"),
            _Seg(6, 10, "loan_contract", "a.pdf", 1, confidence=0.4, review_flag="low_confidence"),
        ]
        pages = {5: "3.9 账户", 6: "5.4 抵押"}
        merged = segment_merge.merge_continuation_segments(segs, pages)

        assert len(merged) == 1
        assert merged[0].confidence == 0.4
        assert merged[0].review_flag == "low_confidence"

    def test_empty_and_single_unchanged(self) -> None:
        assert segment_merge.merge_continuation_segments([], {}) == []
        one = [_Seg(1, 3, "x", "a.pdf")]
        assert segment_merge.merge_continuation_segments(one, {}) == one
