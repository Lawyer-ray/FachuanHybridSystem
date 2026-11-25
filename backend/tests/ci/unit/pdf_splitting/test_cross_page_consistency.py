"""跨页文本一致性校对的单元测试。

真实背景：一份 164 页卷宗里同一枚经办人章被识别 150+ 次，出现多种写法——正确写法
76 次、带空格写法 47 次、错字写法 5 次、严重错字 1 次。同一份卷宗的流水表表头里
`交易卡号` 出现 179 次，其中 15 次被认成 `交易方号`。

判据的全部风险在「什么算同一个词的两种写法」。对正文任意位置做 3..6 字全滑窗会
因为**滑窗 × 一字差**变成噪声发生器：`支付宝支付` 与 `财付通支付` 都是真词，
它们的窗口必然在一字差处相交（实测 157 页真实卷宗上这样跑出 1340 条命中，人工核过
有效的只有几十条）。所以片段只从字段值和表头行这两处原子位置抽取，本测试把这条
约束钉死。

测试数据全为虚构值：`张三丰` / `张四丰` / `李四丰` / `王五丰` 是「张三」类虚构名的三字变体，
`交易卡号` / `经办人` 是银行业务流程术语。片段最短 3 字，所以虚构人名一律取三字。
"""

from __future__ import annotations

from apps.pdf_splitting.services.split.cross_page_consistency import (
    KIND_AMOUNT,
    KIND_CASE_NUMBER,
    KIND_ENTITY_CLUSTER,
    KIND_FREQUENCY,
    KIND_ID_MALFORMED,
    Inconsistency,
    _is_header_word,
    _is_valid_id_card,
    _iter_candidates,
    find_inconsistencies,
)

#: 「交易卡号」179 次 / 「交易方号」15 次——照真实卷宗里的术语错字分布写。
#: 用 3/2 这种量级分不出 high 与 medium 的边界。
_TERM_CANONICAL_COUNT = 179
_TERM_VARIANT_COUNT = 15

#: 一行流水表表头：空格分隔的行内散排，与真实 OCR 输出同形（卷宗里一个 `|` 都没有）。
_HEADER_TEMPLATE = "交易日期 对方账号 摘要 发生额 当前余额 {card}"


def _pages(repeats: dict[str, int], *, pages: int) -> dict[int, str]:
    """把每段文字均匀铺到 ``pages`` 页上，每页一行一段。

    ``repeats``: ``{片段: 总次数}``。总次数除不尽页数时余数落在前面的页。
    同一页里两段文字必须分行放——行内相邻会让两个术语首尾相接，切出纸面上不存在
    的片段（实测 `交易卡号`+`交易方号` 拼出 `交易卡` 和 `易卡号`）。
    """
    page_texts: dict[int, str] = {}
    for page_number in range(1, pages + 1):
        lines: list[str] = []
        for fragment, total in repeats.items():
            quota = total // pages + (1 if page_number <= total % pages else 0)
            lines.extend([fragment] * quota)
        page_texts[page_number] = "\n".join(lines)
    return page_texts


def _field_pages(value: str, count: int, *, offset: int = 0) -> dict[int, str]:
    """``经办人：<value>`` 重复 ``count`` 次，每页一次；页号从 ``offset + 1`` 起。

    两种写法各自铺在不同的页上——同页会互相覆盖，两个片段的频次就永远凑不齐。
    """
    return {offset + page_number: f"经办人：{value}" for page_number in range(1, count + 1)}


def _header_pages(card: str, count: int, *, offset: int = 0) -> dict[int, str]:
    """流水表表头里的「交易卡号」格子被识别成 ``card``，重复 ``count`` 页。"""
    return {offset + page_number: _HEADER_TEMPLATE.format(card=card) for page_number in range(1, count + 1)}


def _combine(*page_sets: dict[int, str]) -> dict[int, str]:
    """把多组页拼成一本卷宗。

    各组铺在不同的页上（``offset`` 各自错开），所以直接取并集；同一页出现两次视为
    测试写错——静默覆盖会让两个片段的频次凑不齐，断言就假绿。
    """
    combined: dict[int, str] = {}
    for page_set in page_sets:
        overlap = combined.keys() & page_set.keys()
        if overlap:
            raise AssertionError(f"测试数据页号重叠：{sorted(overlap)[:5]}")
        combined.update(page_set)
    return combined


def _pairs(pages_text: dict[int, str], **kwargs: object) -> set[tuple[str, str]]:
    return {(hit.canonical, hit.variant) for hit in find_inconsistencies(pages_text, **kwargs)}


class TestDetectsTermLevelTypo:
    def test_catches_table_header_variant(self) -> None:
        """`交易卡号`(179) vs `交易方号`(15)：表头里的术语级形近错字必须抓到。"""
        pages_text = _combine(
            _header_pages("交易卡号", _TERM_CANONICAL_COUNT),
            _header_pages("交易方号", _TERM_VARIANT_COUNT, offset=_TERM_CANONICAL_COUNT),
        )
        assert ("交易卡号", "交易方号") in _pairs(pages_text)

    def test_header_variant_is_high_confidence(self) -> None:
        """179 vs 15 = 差 12 倍、variant 占比 7.7% → high。"""
        pages_text = _combine(
            _header_pages("交易卡号", _TERM_CANONICAL_COUNT),
            _header_pages("交易方号", _TERM_VARIANT_COUNT, offset=_TERM_CANONICAL_COUNT),
        )
        hit = next(hit for hit in find_inconsistencies(pages_text) if hit.variant == "交易方号")
        assert hit.canonical_count == _TERM_CANONICAL_COUNT
        assert hit.variant_count == _TERM_VARIANT_COUNT
        assert hit.confidence == "high"

    def test_reports_variant_pages(self) -> None:
        """页号是判据的落脚点——律师要靠它翻回原页核对。"""
        pages_text = _combine(_field_pages("张三丰", 20), _field_pages("张四丰", 3, offset=20))
        hit = next(hit for hit in find_inconsistencies(pages_text) if hit.variant == "张四丰")
        assert hit.pages == [21, 22, 23]

    def test_catches_seal_text_typo(self) -> None:
        """印章文字差 1 字：`张某某罗某某`(76) vs `张某某罗某乙`(5)。"""
        pages_text = _combine(_field_pages("张某某罗某某", 76), _field_pages("张某某罗某乙", 5, offset=76))
        assert ("张某某罗某某", "张某某罗某乙") in _pairs(pages_text)

    def test_missing_char_header_word_is_recognised_as_header(self) -> None:
        """`易日期` 是 `交易日期` 漏了一个字：长度差 1 也要能进表头候选项。

        它最终不与 `交易日期` 配对——长度不同不比较（`张三` vs `张三丰` 是两个人）。
        但必须先进候选，否则这条表头根本不会出现在结果里。
        """
        assert _is_header_word("易日期")
        assert _iter_candidates("交易日期 对方账号 摘要 发生额 当前余额 易日期", max_len=6) == [
            "交易日期",
            "对方账号",
            "发生额",
            "当前余额",
            "易日期",
        ]


class TestOnlyAtomicUnitsAreCompared:
    def test_true_words_in_body_text_are_not_candidates(self) -> None:
        """`支付宝支付` / `财付通支付` 是两个真词，滑窗曾让它们互相配对。"""
        pages_text = dict.fromkeys(
            range(1, 40), "经办人：张三丰\n170306 1000000000000000000001 财付通支付 D31.00 7594.97 6200000000000001"
        )
        pages_text.update(
            dict.fromkeys(range(40, 80), "经办人：张三丰\n170306 1000000000000000000002 支付宝支付 D226.00 7034.97")
        )
        variants = {hit.variant for hit in find_inconsistencies(pages_text)}
        assert "支付宝支付" not in variants
        assert "财付通支付" not in variants
        assert pages_text  # 数据确实铺到了多页，不是空跑

    def test_body_sentence_fragments_are_not_candidates(self) -> None:
        """`的利率`、`款合同` 是句子碎片，不是字段值也不是表头。"""
        pages_text = {
            n: "本合同项下贷款合同的利率按基准利率种类执行" if n % 2 else "本合同项下款合同的利率按基准利率种类执行"
            for n in range(1, 60)
        }
        assert find_inconsistencies(pages_text) == []

    def test_field_values_of_different_people_are_compared(self) -> None:
        """字段值是原子单元：`张甲乙` 与 `张甲丙` 该被拿出来比，再由频次决定报不报。"""
        pages_text = _combine(_field_pages("张甲乙", 79), _field_pages("张甲丙", 3, offset=79))
        assert ("张甲乙", "张甲丙") in _pairs(pages_text)


class TestHighFrequencyWins:
    def test_high_frequency_side_is_canonical(self) -> None:
        """canonical 取高频那一侧——不是按出现顺序，也不是按字典序。"""
        pages_text = _combine(_field_pages("张三丰", 30), _field_pages("张四丰", 3, offset=30))
        hit = next(hit for hit in find_inconsistencies(pages_text) if hit.variant == "张四丰")
        assert hit.canonical == "张三丰"
        assert hit.canonical_count == 30
        assert hit.variant_count == 3

    def test_confidence_high_needs_ratio_and_share(self) -> None:
        """ratio >= 3 且 variant 占比 <= 20% 才 high；179/15 满足。"""
        pages_text = _combine(
            _header_pages("交易卡号", _TERM_CANONICAL_COUNT),
            _header_pages("交易方号", _TERM_VARIANT_COUNT, offset=_TERM_CANONICAL_COUNT),
        )
        hit = next(hit for hit in find_inconsistencies(pages_text) if hit.variant == "交易方号")
        assert hit.canonical_count / hit.variant_count >= 3
        assert hit.variant_count / (hit.canonical_count + hit.variant_count) <= 0.2
        assert hit.confidence == "high"

    def test_term_below_ratio_is_not_reported(self) -> None:
        """27 vs 10 只有 2.7 倍，不到业务术语的 3 倍门槛——不报。"""
        pages_text = _combine(_header_pages("交易卡号", 27), _header_pages("交易方号", 10, offset=27))
        assert pages_text
        assert find_inconsistencies(pages_text) == []

    def test_term_at_ratio_is_reported(self) -> None:
        """9 vs 3 正好 3 倍——达到业务术语门槛，报。"""
        pages_text = _combine(_header_pages("交易卡号", 9), _header_pages("交易方号", 3, offset=9))
        hit = next(hit for hit in find_inconsistencies(pages_text) if hit.variant == "交易方号")
        assert hit.canonical_count == 9
        assert hit.variant_count == 3
        assert hit.confidence == "high"


class TestPersonNameThreshold:
    """人名门槛比业务术语严（4 倍）：同姓差一字的两个人太常见，误报代价很高。"""

    def test_person_name_with_wide_gap_is_reported(self) -> None:
        """`张三丰`(16) vs `张四丰`(3) = 5.3 倍——签字栏被认错的那一类，报。

        真实形态：`丙某甲`(3) 只出现在签字栏，`丙某某`(16) 在正文里满篇都是。
        """
        pages_text = _combine(_field_pages("张三丰", 16), _field_pages("张四丰", 3, offset=16))
        hit = next(hit for hit in find_inconsistencies(pages_text) if hit.variant == "张四丰")
        assert hit.canonical == "张三丰"
        assert hit.canonical_count / hit.variant_count > 4

    def test_person_name_below_person_threshold_is_not_reported(self) -> None:
        """`张三丰`(21) vs `张四丰`(15) = 1.4 倍——两个自然人，不报。"""
        pages_text = _combine(_field_pages("张三丰", 21), _field_pages("张四丰", 15, offset=21))
        assert find_inconsistencies(pages_text) == []

    def test_person_threshold_is_stricter_than_term_threshold(self) -> None:
        """同样是 5 倍：业务术语报，人名不报（人名要 4 倍、这里用 3.5 倍验两档不同）。

        `张三丰`(14) / `张四丰`(4) = 3.5 倍：越过术语门槛(3)但没到人名门槛(4)。
        """
        pages_text = _combine(_field_pages("张三丰", 14), _field_pages("张四丰", 4, offset=14))
        assert find_inconsistencies(pages_text) == []


class TestNoFalsePositiveOnRealDifferentNames:
    def test_close_frequency_names_are_not_reported(self) -> None:
        """`张三丰`(21) vs `张四丰`(15) 是两个自然人，频次接近就不报。"""
        pages_text = _combine(_field_pages("张三丰", 21), _field_pages("张四丰", 15, offset=21))
        variants = {hit.variant for hit in find_inconsistencies(pages_text)}
        assert "张四丰" not in variants
        assert "张三丰" not in variants

    def test_two_people_with_different_surnames_are_not_reported(self) -> None:
        """`李四丰`(21) vs `王五丰`(15)：首字不同且频次接近，是两个不同的人。"""
        pages_text = _combine(_field_pages("李四丰", 21), _field_pages("王五丰", 15, offset=21))
        assert find_inconsistencies(pages_text) == []

    def test_close_frequency_pair_under_min_count_is_ignored(self) -> None:
        """低到门槛以下的两段文字连同它们的差异都不参与比较。"""
        pages_text = _combine(_field_pages("张三丰", 2), _field_pages("张四丰", 1, offset=2))
        assert find_inconsistencies(pages_text, min_count=3) == []


class TestNoCrossLengthComparison:
    def test_shorter_and_longer_names_are_not_compared(self) -> None:
        """`张三丰` vs `张三丰李` 是两个人，不是漏字——长度不同不比较。"""
        pages_text = _combine(_field_pages("张三丰", 30), _field_pages("张三丰李", 5, offset=30))
        assert find_inconsistencies(pages_text) == []

    def test_length_difference_not_treated_as_missing_char(self) -> None:
        """`交易卡号`(179) 与 `交易卡`(4) 长度不同，不走「差 1 字」判据。"""
        pages_text = _combine(_header_pages("交易卡号", 179), _header_pages("交易卡", 4, offset=179))
        assert find_inconsistencies(pages_text) == []


class TestWhitespaceNormalization:
    def test_space_only_difference_is_not_a_variant(self) -> None:
        """`张某某罗某某` 与 `张某某 罗某某` 是排版差异，OCR 没认错字。"""
        pages_text = {n: ("经办人：张某某罗某某" if n % 2 else "经办人：张某某 罗某某") for n in range(1, 31)}
        assert find_inconsistencies(pages_text) == []

    def test_spaced_and_unspaced_counts_are_merged(self) -> None:
        """带空格写法归一后要并进 canonical 频次，不能自己变成一个变体。"""
        pages_text = {n: ("经办人：张某某罗某某" if n % 2 else "经办人：张某某 罗某某") for n in range(1, 31)}
        pages_text.update(dict.fromkeys(range(31, 34), "经办人：张某某罗某乙"))
        hit = next(hit for hit in find_inconsistencies(pages_text) if hit.variant == "张某某罗某乙")
        assert hit.canonical == "张某某罗某某"
        assert hit.canonical_count == 30


class TestGuardsAndOrdering:
    def test_empty_input(self) -> None:
        assert find_inconsistencies({}) == []

    def test_invalid_arguments_return_empty(self) -> None:
        pages_text = {1: "经办人：张三丰"}
        assert find_inconsistencies(pages_text, min_count=1) == []
        assert find_inconsistencies(pages_text, min_count=3, max_len=2) == []

    def test_max_len_bounds_fragment_length(self) -> None:
        """7 字的字段值超出门槛：max_len=6 下不参与，放宽到 7 才比。"""
        pages_text = _combine(_field_pages("张三丰李四王五", 30), _field_pages("张三丰李四王六", 3, offset=30))
        assert find_inconsistencies(pages_text, max_len=6) == []
        pairs = {(hit.canonical, hit.variant) for hit in find_inconsistencies(pages_text, max_len=7)}
        assert ("张三丰李四王五", "张三丰李四王六") in pairs

    def test_sorted_by_variant_count_descending(self) -> None:
        pages_text = _combine(
            _header_pages("交易卡号", 179),
            _header_pages("交易方号", 15, offset=179),
            _field_pages("张三丰", 30, offset=194),
            _field_pages("张四丰", 6, offset=224),
        )
        variant_counts = [hit.variant_count for hit in find_inconsistencies(pages_text)]
        assert variant_counts == sorted(variant_counts, reverse=True)

    def test_result_is_frozen(self) -> None:
        hit = Inconsistency(
            canonical="交易卡号",
            variant="交易方号",
            canonical_count=179,
            variant_count=15,
            pages=[4],
            confidence="high",
        )
        try:
            hit.canonical = "交易方号"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("Inconsistency 应为 frozen dataclass")


def _role_pages(role: str, value: str, page_numbers: list[int]) -> dict[int, str]:
    """``<role>：<value>`` 铺到指定页上（每页一次）。"""
    return dict.fromkeys(page_numbers, f"{role}：{value}")


#: 虚构借款人姓名族：同「姓+名首字」前缀、只差末字的 5 种写法。
#: 真实卷宗里借款人正是这个形态——每种写法各出现 1-2 页，频次比只有 2.0。
_BORROWER_WRITINGS = ["测试甲", "测试乙", "测试丙", "测试丁", "测试戊"]

#: 虚构证件号（110101 = 示例行政区划，号码明显是假号）。
_FAKE_ID = "110101199001011234"
#: 同一号码被 OCR 认坏两位：第 2 位数字认成字母、第 17 位数字认错。
_FAKE_ID_BROKEN = "1x0101199001011244"
#: 与 _FAKE_ID 只差末两位的另一个**合法**号码（用于验「候选不唯一就不报」）。
_FAKE_ID_NEIGHBOUR = "110101199001011244"


class TestEntityClusterCatchesPartyName:
    """当事人姓名：每种写法都很少时，频次悬殊法结构性失效，靠前缀聚类补。"""

    def test_frequency_method_alone_misses_low_count_writings(self) -> None:
        """5 种写法各 1-3 页、频次比 2.0 → 频次法一条都不报（这就是实测盲区）。"""
        pages_text = _combine(
            *[_role_pages("户名", writing, [index + 1]) for index, writing in enumerate(_BORROWER_WRITINGS)]
        )
        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_FREQUENCY] == []

    def test_cluster_reports_every_other_writing_as_candidate(self) -> None:
        """同一角色下 5 种写法 → 参照写法 + 其余 4 种各一条候选提示。"""
        pages_text = _combine(
            *[_role_pages("户名", writing, [index + 1]) for index, writing in enumerate(_BORROWER_WRITINGS)]
        )

        hits = [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_ENTITY_CLUSTER]

        assert len(hits) == 4
        assert {hit.canonical for hit in hits} == {hits[0].canonical}  # 单一参照写法
        assert {hits[0].canonical} | {hit.variant for hit in hits} == set(_BORROWER_WRITINGS)

    def test_cluster_hints_are_medium_so_frontend_wont_auto_apply(self) -> None:
        """必须是 medium：前端 engine-suggest 只信 high，medium 天然「只提示不改正文」。

        簇里各写法频次接近，根本没有「哪个是正确写法」的证据。给 high 会让前端
        建议把其中一个人名改成另一个——可能把两个真人合并成一个。
        """
        pages_text = _combine(
            *[_role_pages("户名", writing, [index + 1]) for index, writing in enumerate(_BORROWER_WRITINGS)]
        )

        hits = [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_ENTITY_CLUSTER]

        assert hits
        assert all(hit.confidence == "medium" for hit in hits)

    def test_cluster_reports_variant_pages(self) -> None:
        """页号仍必须给全——律师要靠它翻回原页核对是哪一种写法。"""
        pages_text = _combine(
            _role_pages("户名", "测试甲", [1, 2, 3]),
            _role_pages("户名", "测试乙", [4, 5]),
            _role_pages("户名", "测试丙", [6]),
        )

        hit = next(hit for hit in find_inconsistencies(pages_text) if hit.variant == "测试丙")

        assert hit.pages == [6]
        assert hit.canonical == "测试甲"
        assert hit.canonical_count == 3
        assert hit.variant_count == 1

    def test_two_writings_are_not_clustered(self) -> None:
        """只有 2 种写法 → 不聚类：那正是「两个同姓差一字的自然人」的形态。

        与 ``TestPersonNameThreshold`` 同一份数据：频次法不报（1.4 倍），
        聚类也不能报，否则这道守卫就被绕过去了。
        """
        pages_text = _combine(_field_pages("张三丰", 21), _field_pages("张四丰", 15, offset=21))

        assert find_inconsistencies(pages_text) == []

    def test_three_writings_on_one_page_are_not_clustered(self) -> None:
        """3 种写法但全在同一页 → 不报：同页同角色并列更像共有人/保证人名单。"""
        pages_text = {1: "户名：测试甲 测试乙 测试丙"}

        assert find_inconsistencies(pages_text) == []

    def test_writings_under_different_roles_are_not_clustered(self) -> None:
        """跨角色不聚类：借款人/保证人/抵押人各自是同姓不同的人，这是常态。"""
        pages_text = _combine(
            _role_pages("借款人", "测试甲", [1, 2]),
            _role_pages("保证人", "测试乙", [3, 4]),
            _role_pages("抵押人", "测试丙", [5, 6]),
        )

        assert find_inconsistencies(pages_text) == []

    def test_different_prefix_is_not_clustered(self) -> None:
        """同角色但姓不同 → 不是一个人名簇。"""
        pages_text = _combine(
            _role_pages("户名", "测试甲", [1]),
            _role_pages("户名", "合成乙", [2]),
            _role_pages("户名", "虚构丙", [3]),
        )

        assert find_inconsistencies(pages_text) == []

    def test_different_length_is_not_clustered(self) -> None:
        """3 字与 4 字分桶：`测试甲` 与 `测试甲乙` 不是同一个人的漏字写法。"""
        pages_text = _combine(
            _role_pages("户名", "测试甲", [1]),
            _role_pages("户名", "测试乙", [2]),
            _role_pages("户名", "测试甲乙", [3]),
        )

        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_ENTITY_CLUSTER] == []

    def test_body_text_names_are_not_clustered(self) -> None:
        """正文里的人名不进聚类：不对正文滑窗是本模块的立身之本（1340 条噪声教训）。"""
        pages_text = {
            1: "测试甲向本行申请借款",
            2: "测试乙向本行申请借款",
            3: "测试丙向本行申请借款",
        }

        assert find_inconsistencies(pages_text) == []

    def test_business_terms_are_not_clustered_as_names(self) -> None:
        """表头术语不是人名形态，不进姓名聚类（仍走原有频次判据）。"""
        pages_text = _combine(_header_pages("交易卡号", 179), _header_pages("交易方号", 15, offset=179))

        hits = find_inconsistencies(pages_text)

        assert hits
        assert all(hit.kind == KIND_FREQUENCY for hit in hits)

    def test_cluster_does_not_duplicate_frequency_hit(self) -> None:
        """频次法已报过的同一对写法，聚类不再刷一条。"""
        pages_text = _combine(
            _role_pages("经办人", "测试甲", list(range(1, 31))),
            _role_pages("经办人", "测试乙", [31, 32, 33]),
            _role_pages("经办人", "测试丙", [34]),
        )

        hits = find_inconsistencies(pages_text)
        pairs = [(hit.canonical, hit.variant) for hit in hits]

        assert len(pairs) == len(set(pairs))
        assert ("测试甲", "测试乙") in pairs
        assert sum(1 for hit in hits if hit.kind == KIND_FREQUENCY) == 1


class TestIdCardMalformed:
    """证件号：靠结构合法性这个硬证据，不靠频次。"""

    def test_structurally_broken_id_is_reported(self) -> None:
        """合法号 vs 被认坏两位的号（同一字段）→ 一条 id_malformed 提示。"""
        pages_text = _combine(
            _role_pages("公民身份号码", _FAKE_ID, [1, 2]),
            _role_pages("公民身份号码", _FAKE_ID_BROKEN, [3]),
        )

        hits = [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_ID_MALFORMED]

        assert len(hits) == 1
        assert hits[0].canonical == _FAKE_ID
        assert hits[0].variant == _FAKE_ID_BROKEN
        assert hits[0].pages == [3]
        assert hits[0].confidence == "medium"

    def test_two_valid_ids_differing_by_one_digit_are_not_reported(self) -> None:
        """两侧都合法 → 不报：可能是相邻发号的两个自然人，没有硬证据就不猜。"""
        pages_text = _combine(
            _role_pages("证件号码", _FAKE_ID, [1, 2]),
            _role_pages("证件号码", _FAKE_ID_NEIGHBOUR, [3, 4]),
        )

        assert find_inconsistencies(pages_text) == []

    def test_ambiguous_broken_id_is_not_reported(self) -> None:
        """损坏号与两个合法号都接近 → 候选不唯一，不指认。"""
        pages_text = _combine(
            _role_pages("公民身份号码", _FAKE_ID, [1]),
            _role_pages("公民身份号码", _FAKE_ID_NEIGHBOUR, [2]),
            _role_pages("公民身份号码", _FAKE_ID_BROKEN, [3]),
        )

        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_ID_MALFORMED] == []

    def test_broken_id_far_from_every_valid_id_is_not_reported(self) -> None:
        """损坏号与合法号差 3 位以上 → 超出容差，不报。"""
        pages_text = _combine(
            _role_pages("证件号码", _FAKE_ID, [1]),
            _role_pages("证件号码", "9x9999999999999999", [2]),
        )

        assert find_inconsistencies(pages_text) == []

    def test_separator_may_be_missing(self) -> None:
        """OCR 常把冒号丢掉或换成空格：两种形态都要能取到证件号。"""
        pages_text = {1: f"证件号码 {_FAKE_ID}", 2: f"证件号码:{_FAKE_ID_BROKEN}"}

        hits = [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_ID_MALFORMED]

        assert len(hits) == 1
        assert hits[0].variant == _FAKE_ID_BROKEN

    def test_longer_account_number_is_not_truncated_into_id(self) -> None:
        """22 位账号串不许被截前 18 位当证件号——那会造出假的「损坏号」。"""
        pages_text = {1: "证件号码：6200000000000000000123", 2: f"证件号码：{_FAKE_ID}"}

        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_ID_MALFORMED] == []

    def test_id_roles_are_not_merged(self) -> None:
        """不同证件号字段各自分桶：跨字段配对没有「同一处」的依据。"""
        pages_text = _combine(
            _role_pages("证件号码", _FAKE_ID, [1]),
            _role_pages("公民身份号码", _FAKE_ID_BROKEN, [2]),
        )

        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_ID_MALFORMED] == []

    def test_validity_oracle(self) -> None:
        """18 位证只有末位可以是 X；15 位旧证全数字；其它长度一律不合法。"""
        assert _is_valid_id_card(_FAKE_ID)
        assert _is_valid_id_card("11010119900101123X")
        assert _is_valid_id_card("110101900101123")
        assert not _is_valid_id_card(_FAKE_ID_BROKEN)
        assert not _is_valid_id_card("11010119900101123Y")
        assert not _is_valid_id_card("12345")


class TestCaseNumberVariant:
    """案号：同法院 + 同年 + 同案件类型下，短号码是长号码**删掉一位**的产物。

    真实样本（某 37 页卷宗）：完整案号在 p13/p34 一致、p18 掉了一位成三位数。
    这是「数字错位」，前面三类判据（差一个汉字 + 频次悬殊）都看不见。
    """

    def test_dropped_digit_is_reported(self) -> None:
        pages_text = {
            13: "见（2099）测试民终6121号判决书。",  # privacy-allow 虚构案号
            18: "见(2099)测试民终621号判决书。",  # privacy-allow 虚构案号
            34: "（2099）测试民终6121号判决再次确认。",  # privacy-allow 虚构案号
        }

        hits = [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_CASE_NUMBER]

        assert len(hits) == 1
        assert hits[0].canonical_count == 2  # 多数派是 6121
        assert "6121" in hits[0].canonical
        assert "621" in hits[0].variant
        assert hits[0].pages == [18]
        assert hits[0].confidence == "medium"

    def test_two_real_neighbouring_cases_are_not_reported(self) -> None:
        """6121 与 6122 是同年同类的两个真实案件——形态是「替换一位」而不是「删一位」。"""
        pages_text = {
            1: "（2099）测试民终6121号 判决如下。",  # privacy-allow 虚构案号
            2: "（2099）测试民终6122号 裁定如下。",  # privacy-allow 虚构案号
            3: "（2099）测试民终6121号 再次提及。",  # privacy-allow 虚构案号
        }

        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_CASE_NUMBER] == []

    def test_different_court_or_kind_is_not_bucketed_together(self) -> None:
        pages_text = {
            1: "（2099）测试民终6121号。",  # privacy-allow 虚构案号
            2: "（2099）测试民初621号。",  # privacy-allow 虚构案号（案件类型不同）
            3: "（2099）另院民终621号。",  # privacy-allow 虚构案号（法院不同）
        }

        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_CASE_NUMBER] == []


class TestAmountVariant:
    """金额：同一角色标签下，数值只差几位，且多数派出现 ≥2 次。

    真实样本（617 卷宗）：应补税额 `6529346.56元` 在 p23/p27/p28 一致、p32 成 `6592946.56元`。
    """

    def test_amount_typo_under_same_label_is_reported(self) -> None:
        pages_text = {
            27: "应补缴税款 6529346.56元和滞纳金。",
            28: "应补缴税款 6529346.56元已核定。",
            32: "应补缴税款 6592946.56元。",
        }

        hits = [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_AMOUNT]

        assert len(hits) == 1
        assert "6529346.56" in hits[0].canonical
        assert "6592946.56" in hits[0].variant
        assert hits[0].canonical_count == 2
        assert hits[0].pages == [32]
        assert hits[0].confidence == "medium"

    def test_without_a_majority_nothing_is_reported(self) -> None:
        """两个各出现一次的真不同金额（实测某 164 页卷宗 `11700` vs `11530`）→ 不报。"""
        pages_text = {31: "收入 11700元。", 48: "收入 11530元。"}

        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_AMOUNT] == []

    def test_same_numbers_under_different_labels_are_not_compared(self) -> None:
        pages_text = {
            1: "合同价 100000元。",
            2: "违约金 10020元。",
            3: "合同价 100000元。",
        }

        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_AMOUNT] == []

    def test_amount_without_unit_is_ignored(self) -> None:
        """没有 `元` 的数字（页码 / 账号 / 流水号）不参与比对。"""
        pages_text = {1: "凭证号 6529346 与 6529346。", 2: "凭证号 6592946。"}

        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_AMOUNT] == []

    def test_clearly_different_amounts_under_same_label_are_not_reported(self) -> None:
        """差 3 位以上的两个金额是两笔不同的钱，不是同一个数写错。"""
        pages_text = {
            1: "本金 1000000元。",
            2: "本金 1000000元。",
            3: "本金 7777777元。",
        }

        assert [hit for hit in find_inconsistencies(pages_text) if hit.kind == KIND_AMOUNT] == []
