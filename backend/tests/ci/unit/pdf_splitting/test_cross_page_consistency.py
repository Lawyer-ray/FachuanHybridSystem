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
    Inconsistency,
    _is_header_word,
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
            range(1, 40), "经办人：张三丰\n170306 3117063303100701000157 财付通支付 D31.00 7594.97 6223221027175157"
        )
        pages_text.update(
            dict.fromkeys(range(40, 80), "经办人：张三丰\n170306 3117063303100700300179 支付宝支付 D226.00 7034.97")
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
