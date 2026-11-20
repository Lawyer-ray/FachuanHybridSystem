"""``services/chat/citation_check.py`` 的引用核验（纯函数 + 注入查询接口）。

本文件钉四个方面：

1. **核不到的才进清单**，且文案照抄答案里的写法（律师要能在正文里搜到那句）；
2. **中文/阿拉伯条号互通**：「第一千零七十九条」与「第1079条」是同一条，反查
   原文里的「第三十二条」也要认；
3. **条款号在原文存在性只在原文自己写了条号时才核**：真实数据源返回的是条文
   正文（不含「第 X 条」），硬要求条号出现在原文会让每一条真实引用都变噪音；
4. **不查库**：数据源全部经 :class:`FakeLookup` 注入，用例不建库、不联网。

为什么这些用例不在 ``test_equivalence.py`` 或 ``test_fusion.py`` 里：三个模块
各管一件事，文件名必须能直接告诉下一个人"改这个模块该跑哪个文件"。
"""

from __future__ import annotations

import pytest

from apps.agent.services.chat.citation_check import (
    MAX_UNVERIFIED,
    extract_case_refs,
    extract_statute_refs,
    verify_references,
)

#: 真实数据源返回的 ``article_text`` 形状：条文正文，通常**不含**「第 X 条」。
ARTICLE_1079_BODY = "夫妻一方要求离婚的，可以由有关组织进行调解或者直接向人民法院提起离婚诉讼。"


class FakeLookup:
    """注入用的核验数据源：字典就是"库"，同时记录被问了什么。"""

    def __init__(self, statutes: dict[tuple[str, int], str] | None = None, cases: set[str] | None = None) -> None:
        self.statutes = statutes or {}
        self.cases = cases or set()
        self.statute_calls: list[tuple[str, int]] = []
        self.case_calls: list[str] = []

    def statute_text(self, law_name: str, article_no: int) -> str | None:
        self.statute_calls.append((law_name, article_no))
        return self.statutes.get((law_name, article_no))

    def case_exists(self, case_no: str) -> bool:
        self.case_calls.append(case_no)
        return case_no in self.cases


def test_verified_statute_and_case_produce_no_message() -> None:
    """核到的不进 unverified 清单（清单只放"要人再看一眼"的）。"""
    lookup = FakeLookup(
        statutes={("民法典", 1079): f"第一千零七十九条 {ARTICLE_1079_BODY}"},
        cases={"（2020）京01民终1号"},  # allowlist secret（合成案号，仅用于测试解析规则）
    )
    text = "依据《民法典》第一千零七十九条，夫妻一方要求离婚的可以直接起诉；参见（2020）京01民终1号。"  # allowlist secret（合成案号，仅用于测试解析规则）

    assert verify_references(text, lookup=lookup) == []
    # 中文条号折算成 1079 才问得到数据源（折错就是核错一条法条）。
    assert lookup.statute_calls == [("民法典", 1079)]
    assert lookup.case_calls == ["（2020）京01民终1号"]  # allowlist secret（合成案号，仅用于测试解析规则）


def test_missing_statute_is_reported_with_the_wording_from_the_answer() -> None:
    """查不到的法条：文案照抄答案里的写法，不改写成别的条号形态。"""
    messages = verify_references("依据《民法典》第一千零七十九条……", lookup=FakeLookup())

    assert messages == ["引《民法典》第一千零七十九条，本轮无核验命中"]


def test_missing_case_number_is_reported() -> None:
    """查不到的案号同样进清单（案号真实性是另一条独立的造假路径）。"""
    messages = verify_references("参见（2020）京01民终1234号判决。", lookup=FakeLookup())  # allowlist secret（合成案号，仅用于测试解析规则）

    assert messages == ["引案号（2020）京01民终1234号，本轮无核验命中"]  # allowlist secret（合成案号，仅用于测试解析规则）


def test_article_number_mismatch_in_returned_text_is_reported() -> None:
    """数据源把 A 条的原文贴成 B 条：原文里出现了别的条号 → 必须报。"""
    lookup = FakeLookup(statutes={("民法典", 1079): "第一千零八十条 完成离婚登记，或者离婚判决书生效。"})

    messages = verify_references("依据《民法典》第一千零七十九条……", lookup=lookup)

    assert messages == ["引《民法典》第一千零七十九条，核验返回的原文里查无此条号"]


def test_returned_text_without_any_article_number_is_treated_as_verified() -> None:
    """原文只有条文正文、没有任何条号 → 无从证伪，按核到处理（宁缺勿错）。"""
    lookup = FakeLookup(statutes={("民法典", 1079): ARTICLE_1079_BODY})

    assert verify_references("依据《民法典》第一千零七十九条……", lookup=lookup) == []


def test_arabic_and_chinese_article_numbers_are_the_same_article() -> None:
    """答案写阿拉伯数字、原文写中文条号：同一条，不误报。"""
    lookup = FakeLookup(statutes={("公司法", 32): "第三十二条 股东有权查阅、复制公司章程。"})

    assert verify_references("《公司法》第32条规定股东可以查阅公司章程。", lookup=lookup) == []
    assert lookup.statute_calls == [("公司法", 32)]


def test_paragraph_suffix_does_not_break_parsing() -> None:
    """「第 1079 条第二款」按条核（款不在本模块能力内，但引用不能因此漏核）。"""
    lookup = FakeLookup(statutes={("民法典", 1079): ARTICLE_1079_BODY})

    assert verify_references("《民法典》第1079条第二款规定……", lookup=lookup) == []
    assert lookup.statute_calls == [("民法典", 1079)]


def test_duplicate_references_are_reported_once() -> None:
    """同一处引用写两遍（含两种条号写法）只核一次、只报一次。"""
    messages = verify_references(
        "《民法典》第1079条……；如前所述，《民法典》第一千零七十九条已经明确。",
        lookup=FakeLookup(),
    )

    assert len(messages) == 1
    assert messages[0].startswith("引《民法典》第1079条")


def test_limit_collapses_the_tail_into_one_summary_line() -> None:
    """超出上限时只截清单、不静默丢：最后一行写清还有多少条没列。"""
    text = "、".join(f"《测试法》第{article}条" for article in range(1, MAX_UNVERIFIED + 6))

    messages = verify_references(text, lookup=FakeLookup())

    assert len(messages) == MAX_UNVERIFIED + 1
    assert messages[-1] == f"另有 5 处引用未核验（本清单最多列 {MAX_UNVERIFIED} 条）"
    # 负数会把清单切成"除最后一条全留下"，不是截断：直接报错而不是给出怪结果。
    with pytest.raises(ValueError):
        verify_references("《测试法》第1条", lookup=FakeLookup(), limit=-1)


def test_extract_statute_refs_keeps_first_wording_per_article() -> None:
    """抽取：按 ``(法律名, 条号)`` 去重、保留首次出现的写法。"""
    refs = extract_statute_refs("《民法典》第一千零七十九条、《公司法》第32条、又见《民法典》第1079条")

    assert [(ref.law_name, ref.article_no) for ref in refs] == [("民法典", 1079), ("公司法", 32)]
    assert refs[0].raw == "《民法典》第一千零七十九条"


def test_extract_case_refs_normalizes_paren_width() -> None:
    """案号：全角/半角括号与空白归一，同一案号只抽一次。"""
    refs = extract_case_refs("(2020)京01民终1号 与 （2020）京01民终1号 是同一案")  # allowlist secret（合成案号，仅用于测试解析规则）

    assert len(refs) == 1
    assert refs[0].case_no == "（2020）京01民终1号"  # allowlist secret（合成案号，仅用于测试解析规则）


def test_empty_text_returns_no_messages() -> None:
    """空正文（解析失败/极短回答）不产清单，也不报错。"""
    lookup = FakeLookup()

    assert verify_references("", lookup=lookup) == []
    assert lookup.statute_calls == []
    assert lookup.case_calls == []
