"""BARLC 域外法查明插件的单元测试（无网络、无数据库）。

## 为什么这些测试值得写

插件在涉及域外法核验的链路里是**唯一的证据来源**：律师看到的「支持 / 矛盾 /
不存在该引用」全部由它决定。它的失败模式不是抛异常，而是**安静地给出一个错的
结论**，所以每一条断言都对着一个"曾经会骗人"的具体行为：

| 测试 | 盯的历史行为 |
|:--|:--|
| `test_normalize_name_keeps_vietnamese_diacritics` | 归一化把越南语变音抹成空格 → `Luật Dân sự` 与 `Luật Dân số` 相等 → 锁定错法 |
| `test_section_key_*` | `Section 4` → `Section4` 永不命中；`5.1` → `51` 命中第 51 条；泰文数字先被删光 |
| `test_split_sections_drops_decoy` | 条文内引用的换行造出「编号对、正文错」的诱饵条，且 `find_section` 取第一个命中 |
| `test_best_match_*` | 近似名直接当成命中（同一部越南法/跨国同名法） |
| `test_resolve_law_raises_when_upstream_fails` | 上游全挂 → 返回 None → 下游判「不存在该引用」（假死） |
| `test_check_unconfirmed_when_no_sections` | 切不出条款 → 判「不存在该条（共 0 条）」（假死） |
| `test_tally_*` | 失败票进分母 / 平票硬给结论 |
| `test_parse_judge_output_*` | 自造选项被折算成最接近的选项；要件聚合交给模型总结 |

CI 不拉 `backend/plugins` 子模块（见 `.github/workflows/backend-ci.yml` 的 mypy 注释），
所以整份文件在子模块缺失时 `skip`，而不是 `error`。
"""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.unit

_HAS_PLUGIN = importlib.util.find_spec("plugins.barlc_asean_law") is not None
if not _HAS_PLUGIN:  # pragma: no cover - CI 无子模块时走这里
    pytest.skip("backend/plugins 子模块未检出，跳过 BARLC 插件测试", allow_module_level=True)

from plugins.barlc_asean_law.adapter import BarlcAdapter
from plugins.barlc_asean_law.credential import BarlcCredential
from plugins.barlc_asean_law.jury import (
    MIN_VALID_VOTES,
    ElementVerdict,
    JudgeVote,
    ParsedVote,
    _aggregate_elements,
    parse_judge_output,
    reset_jury_cache,
    run_jury,
    tally,
)
from plugins.barlc_asean_law.models import BarlcUpstreamError, LawDetail, LawHit, LawSection
from plugins.barlc_asean_law.verify import (
    VERDICT_CONTRADICTED,
    VERDICT_NOT_FOUND,
    VERDICT_NOT_MENTIONED,
    VERDICT_SUPPORTED,
    CitationRequest,
    JudicialVerifier,
    normalize_name,
)

CRED = BarlcCredential(credential_id=1, account="a@example.com", password="x", site_name="barlc")


# ---------------------------------------------------------------- 假件


def _hit(sys_id: str, title_cn: str, title_en: str, country: str) -> LawHit:
    return LawHit(sys_id=sys_id, title_cn=title_cn, title_en=title_en, title_local="", country_code=country)


def _detail(sys_id: str = "1", *, files: int = 1, english: bool = True) -> LawDetail:
    from plugins.barlc_asean_law.models import LawFile

    return LawDetail(
        sys_id=sys_id,
        title_cn="1999年商业和工业房地产租赁法",
        title_en="Rental of Immovable Property for Commerce and Industry Act 1991",
        title_local="",
        publish_date=None,
        effective_date=None,
        revise_date=None,
        keywords_cn="",
        keywords_en="",
        country_code="LAWCOUNTRYTG",
        law_category="",
        has_english_pdf=english,
        file_count=files,
        files=[LawFile(record_id=1, file_id=1, filename="a.pdf", size=1) for _ in range(files)],
    )


class _FakeAdapter:
    """可控的假适配器：只实现 `JudicialVerifier` 用到的那四个方法。"""

    def __init__(self, *, hits=None, sections=None, search_error=None, detail_error=None, section_error=None):
        self._hits = hits or []
        self._sections = sections if sections is not None else []
        self._search_error = search_error
        self._detail_error = detail_error
        self._section_error = section_error

    def search(self, credential, *, keyword, country_code=None, field="Title", page=1, page_size=20):
        if self._search_error is not None:
            raise self._search_error
        return len(self._hits), list(self._hits)

    def get_detail(self, credential, *, sys_id):
        if self._detail_error is not None:
            raise self._detail_error
        return _detail(sys_id)

    def fetch_sections(self, credential, *, detail, lang="en", allow_lang_fallback=True):
        if self._section_error is not None:
            raise self._section_error
        return list(self._sections)

    @staticmethod
    def find_section(sections, number):
        return BarlcAdapter.find_section(sections, number)

    @staticmethod
    def known_country_codes():
        return {"LAWCOUNTRYTG", "LAWCOUNTRYMLXY"}


# ---------------------------------------------------------------- 名称归一化


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # 只差变音的越南语名称必须区分开（旧实现两者都变成 "lu t d n s"）。
        ("Luật Dân sự", "Luật Dân số"),
        ("Luật Dân sự", "Bộ luật Dân sự"),
    ],
)
def test_normalize_name_keeps_vietnamese_diacritics(left: str, right: str) -> None:
    assert normalize_name(left) != normalize_name(right)


def test_normalize_name_folds_diacritics_but_keeps_text() -> None:
    assert normalize_name("Luật Dân sự") == "luat dan su"
    assert normalize_name("Điều 4") == "dieu 4"


def test_normalize_name_keeps_thai_combining_marks() -> None:
    # 泰文的元音/声调本身就是组合符；折变音时不能把它们一起删掉。
    assert normalize_name("ที่ดิน") == "ที่ดิน"


# ---------------------------------------------------------------- 条号归一化


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4", "4"),
        ("第4条", "4"),
        ("第四条", "4"),
        ("第七十九条", "79"),
        ("Section 4", "4"),
        ("Art. 4", "4"),
        ("มาตรา ๔", "4"),
        ("4 bis", "4bis"),
        ("4bis", "4bis"),
        ("Section 4 bis", "4bis"),
        ("12/1", "12/1"),
        ("5.1", "5"),  # 子款归到所属条，不能变成 51
        ("51", "51"),
        ("", ""),
    ],
)
def test_section_key(raw: str, expected: str) -> None:
    assert BarlcAdapter.section_key(raw) == expected


def test_find_section_accepts_documented_forms() -> None:
    sections = [LawSection(number="4", text="Section 4. Rental must be in writing.")]
    for probe in ("4", "第4条", "第四条", "Section 4", "Art. 4"):
        assert BarlcAdapter.find_section(sections, probe) is sections[0], probe


# ---------------------------------------------------------------- 条款切分


def test_split_sections_supports_article_style() -> None:
    text = "Article 1. Short title.\nArticle 2. Definitions.\n"
    numbers = [section.number for section in BarlcAdapter.split_sections(text, lang="en")]
    assert numbers == ["1", "2"]


def test_split_sections_drops_decoy_section() -> None:
    """条文内引用落在行首时不得造出「编号对、正文错」的诱饵条。"""
    text = (
        "Section 3. Application. This Act shall not apply to the property described in\n"
        "Section 5 of the Land Code.\n"
        "Section 4. Rental must be in writing.\n"
        "Section 5. Term of rental.\n"
    )
    sections = BarlcAdapter.split_sections(text, lang="en")
    assert [section.number for section in sections] == ["3", "4", "5"]
    found = BarlcAdapter.find_section(sections, "5")
    assert found is not None
    assert found.text.startswith("Section 5. Term of rental.")


def test_split_sections_normalizes_thai_digits_and_suffix() -> None:
    text = "มาตรา ๑ บทนิยาม\nมาตรา ๒ ทวิ การเช่า\n"
    numbers = [section.number for section in BarlcAdapter.split_sections(text, lang="local")]
    assert numbers == ["1", "2bis"]


def test_split_sections_returns_empty_for_unknown_style() -> None:
    assert BarlcAdapter.split_sections("前言\n第一条 这是中文体例\n", lang="en") == []


# ---------------------------------------------------------------- 名称匹配


def test_best_match_does_not_lock_onto_near_miss_law() -> None:
    """民法典 vs 人口法：只差变音的两个名字不能互相命中。"""
    match = JudicialVerifier._best_match(
        "Luật Dân sự",
        [_hit("POP", "", "Luật Dân số", "LAWCOUNTRYYN")],
        country_code=None,
    )
    assert match.sys_id == ""
    assert match.kind == "ambiguous"


def test_best_match_requires_country_when_title_collides() -> None:
    hits = [
        _hit("1", "民法典", "Civil Code", "LAWCOUNTRYLW"),
        _hit("2", "民法典", "Civil Code", "LAWCOUNTRYYN"),
    ]
    ambiguous = JudicialVerifier._best_match("Civil Code", hits, country_code=None)
    assert ambiguous.kind == "ambiguous"
    assert ambiguous.sys_id == ""

    scoped = JudicialVerifier._best_match("Civil Code", hits, country_code="LAWCOUNTRYYN")
    assert scoped.sys_id == "2"
    assert scoped.kind == "exact"


def test_best_match_containment_still_works() -> None:
    match = JudicialVerifier._best_match(
        "商业和工业房地产租赁法",
        [_hit("7", "1999年商业和工业房地产租赁法", "", "LAWCOUNTRYTG")],
        country_code="LAWCOUNTRYTG",
    )
    assert match.sys_id == "7"
    assert match.confident


# ---------------------------------------------------------------- 规则层语义


def test_resolve_law_raises_when_upstream_fails() -> None:
    """上游全挂是「问不着」，不是「查无此法」。"""
    verifier = JudicialVerifier(_FakeAdapter(search_error=BarlcUpstreamError("boom")))
    with pytest.raises(BarlcUpstreamError):
        verifier.resolve_law(CRED, law_name="Rental of Immovable Property Act")


def test_check_returns_not_found_when_law_absent() -> None:
    verifier = JudicialVerifier(_FakeAdapter(hits=[]))
    check = verifier.check(CRED, CitationRequest(law_name="Fake Thailand Lease Act 2099", section_number="1"))
    assert check.result == VERDICT_NOT_FOUND
    assert check.needs_human is False


def test_check_unconfirmed_when_no_sections_parsed() -> None:
    """切不出条款 ≠ 没有这一条：必须是「无结论 + 需人工」。"""
    verifier = JudicialVerifier(
        _FakeAdapter(
            hits=[_hit("321381", "1999年商业和工业房地产租赁法", "Rental Act", "LAWCOUNTRYTG")],
            sections=[],
        )
    )
    check = verifier.check(CRED, CitationRequest(law_name="Rental Act", section_number="4"))
    assert check.result == ""
    assert check.is_unconfirmed
    assert check.needs_human


def test_check_unconfirmed_when_section_missing_but_match_was_fuzzy() -> None:
    verifier = JudicialVerifier(
        _FakeAdapter(
            hits=[_hit("321381", "1999年商业和工业房地产租赁法", "Rental Act", "LAWCOUNTRYTG")],
            sections=[LawSection(number="9", text="Section 9. Other.")],
        )
    )
    # 「泰国商业租赁法」只是近似，命中后不能断言"没有第 4 条"
    check = verifier.check(CRED, CitationRequest(law_name="泰国商业租赁法", section_number="4"))
    assert check.result == ""
    assert check.needs_human


def test_check_not_found_when_section_truly_missing() -> None:
    verifier = JudicialVerifier(
        _FakeAdapter(
            hits=[_hit("321381", "1999年商业和工业房地产租赁法", "Rental Act", "LAWCOUNTRYTG")],
            sections=[LawSection(number="9", text="Section 9. Other.")],
        )
    )
    check = verifier.check(CRED, CitationRequest(law_name="Rental Act", section_number="4"))
    assert check.result == VERDICT_NOT_FOUND
    assert "共 1 条" in check.reason


def test_check_jury_disabled_keeps_pending_verdict() -> None:
    verifier = JudicialVerifier(
        _FakeAdapter(
            hits=[_hit("321381", "1999年商业和工业房地产租赁法", "Rental Act", "LAWCOUNTRYTG")],
            sections=[LawSection(number="4", text="Section 4. Rental must be in writing.")],
        )
    )
    check = verifier.check(
        CRED,
        CitationRequest(law_name="Rental Act", section_number="4", claim="租赁必须书面"),
        jury=False,
    )
    assert check.result == ""
    assert "多判定器审查已关闭" in check.reason


# ---------------------------------------------------------------- 判定输出解析


def _judge_json(*elements: tuple[str, str]) -> str:
    import json

    return json.dumps(
        {
            "elements": [
                {"statement": statement, "verdict": verdict, "reason": "依据"} for statement, verdict in elements
            ],
            "quote": "",
        },
        ensure_ascii=False,
    )


def test_parse_judge_output_supported() -> None:
    parsed = parse_judge_output(
        _judge_json(("必须书面", VERDICT_SUPPORTED)),
        section_text="Section 4. Rental must be in writing.",
    )
    assert parsed.verdict == VERDICT_SUPPORTED
    assert parsed.partial is False


def test_parse_judge_output_partial_support_is_not_supported() -> None:
    """一个要件有依据、一个没有 → 不能算「支持整条主张」。"""
    parsed = parse_judge_output(
        _judge_json(("必须书面", VERDICT_SUPPORTED), ("必须登记", VERDICT_NOT_MENTIONED)),
        section_text="Section 4. Rental must be in writing.",
    )
    assert parsed.verdict == VERDICT_NOT_MENTIONED
    assert parsed.partial is True


def test_parse_judge_output_any_contradiction_wins() -> None:
    parsed = parse_judge_output(
        _judge_json(("必须书面", VERDICT_SUPPORTED), ("可以口头", VERDICT_CONTRADICTED)),
        section_text="Section 4. Rental must be in writing.",
    )
    assert parsed.verdict == VERDICT_CONTRADICTED


def test_parse_judge_output_rejects_invented_option() -> None:
    """自造选项（「部分支持」）不能被折算成最接近的选项。"""
    import json

    parsed = parse_judge_output(
        json.dumps({"elements": [{"statement": "x", "verdict": "部分支持", "reason": ""}]}, ensure_ascii=False),
        section_text="Section 4.",
    )
    assert parsed.verdict == ""
    assert parsed.unscored_reason == "protocol_deviation"


def test_parse_judge_output_marks_fabricated_quote() -> None:
    import json

    parsed = parse_judge_output(
        json.dumps(
            {
                "elements": [{"statement": "必须书面", "verdict": VERDICT_SUPPORTED, "reason": ""}],
                "quote": "本条要求租赁合同必须公证并备案",
            },
            ensure_ascii=False,
        ),
        section_text="Section 4. Rental under this Act must be in writing.",
    )
    assert parsed.evidence_ok is False


def test_parse_judge_output_trailing_contradiction_is_parse_failure() -> None:
    """JSON 说支持、末行又写别的 → 没有可信答案。"""
    parsed = parse_judge_output(
        _judge_json(("必须书面", VERDICT_SUPPORTED)) + "\n判定：矛盾",
        section_text="Section 4.",
    )
    assert parsed.verdict == ""
    assert parsed.unscored_reason == "parse_failed"


def test_aggregate_elements_unjudgeable_is_not_mentioned() -> None:
    verdict, partial = _aggregate_elements([ElementVerdict(statement="x", verdict="无法判断")])
    assert (verdict, partial) == ("", False)


def test_judge_vote_fabricated_quote_flag() -> None:
    vote = JudgeVote(model="m", role="balanced", verdict=VERDICT_SUPPORTED, evidence_ok=False)
    assert vote.fabricated_quote is True


# ---------------------------------------------------------------- 合议


def _vote(verdict: str, **kwargs) -> JudgeVote:
    return JudgeVote(model="m", role="balanced", verdict=verdict, **kwargs)


def test_tally_strict_majority() -> None:
    result = tally([_vote(VERDICT_SUPPORTED), _vote(VERDICT_SUPPORTED), _vote(VERDICT_CONTRADICTED)])
    assert result.verdict == VERDICT_SUPPORTED
    assert result.valid == 3
    assert result.unanimous is False
    assert result.needs_human is True  # 有人判矛盾 → 必须人工复核


def test_tally_failed_votes_do_not_enter_denominator() -> None:
    result = tally(
        [
            _vote(VERDICT_SUPPORTED),
            _vote(VERDICT_SUPPORTED),
            JudgeVote(model="m", role="balanced", unscored_reason="timeout"),
        ]
    )
    assert result.verdict == VERDICT_SUPPORTED
    assert result.valid == 2


def test_tally_insufficient_votes_is_abstention() -> None:
    result = tally([_vote(VERDICT_SUPPORTED), JudgeVote(model="m", role="balanced", unscored_reason="judge_error")])
    assert result.verdict == ""
    assert result.valid == 1 < MIN_VALID_VOTES
    assert result.unscored_reason == "insufficient_votes"


def test_tally_split_is_abstention() -> None:
    result = tally([_vote(VERDICT_SUPPORTED), _vote(VERDICT_CONTRADICTED)])
    assert result.verdict == ""
    assert result.unscored_reason == "no_majority"


def test_tally_all_failed_is_abstention() -> None:
    result = tally([JudgeVote(model="m", role="balanced", unscored_reason="timeout")])
    assert result.verdict == ""
    assert result.needs_human


def test_tally_fabricated_quote_forces_review() -> None:
    result = tally([_vote(VERDICT_SUPPORTED, evidence_ok=False), _vote(VERDICT_SUPPORTED)])
    assert result.verdict == VERDICT_SUPPORTED
    assert result.needs_human is True


# ---------------------------------------------------------------- run_jury


def _scripted_call(answer: str):
    def _call(prompt: str, model: str, role: str) -> tuple[str, int]:
        return answer, 10

    return _call


def test_run_jury_unanimous() -> None:
    reset_jury_cache()
    answer = _judge_json(("租赁必须书面", VERDICT_SUPPORTED))
    result = run_jury(
        request=CitationRequest(law_name="Rental Act", section_number="4", claim="租赁必须书面"),
        law_title="Rental Act",
        section_number="4",
        section_text="Section 4. Rental must be in writing.",
        models=["m1"],
        call=_scripted_call(answer),
        use_cache=False,
    )
    assert result.verdict == VERDICT_SUPPORTED
    assert result.unanimous is True
    assert result.needs_human is False
    assert len(result.votes) == 3


def test_run_jury_all_judges_failing_is_abstention() -> None:
    def _boom(prompt: str, model: str, role: str) -> tuple[str, int]:
        raise RuntimeError("provider down")

    result = run_jury(
        request=CitationRequest(law_name="Rental Act", section_number="4", claim="租赁必须书面"),
        law_title="Rental Act",
        section_number="4",
        section_text="Section 4. Rental must be in writing.",
        models=["m1"],
        call=_boom,
        use_cache=False,
        deadline=5.0,
    )
    assert result.verdict == ""
    assert result.needs_human


def test_run_jury_caches_result() -> None:
    reset_jury_cache()
    answer = _judge_json(("租赁必须书面", VERDICT_SUPPORTED))
    request = CitationRequest(law_name="Rental Act", section_number="9", claim="租赁必须书面（缓存）")
    first = run_jury(
        request=request,
        law_title="Rental Act",
        section_number="9",
        section_text="Section 9. Rental must be in writing.",
        models=["m1"],
        call=_scripted_call(answer),
    )
    second = run_jury(
        request=request,
        law_title="Rental Act",
        section_number="9",
        section_text="Section 9. Rental must be in writing.",
        models=["m1"],
        call=_scripted_call(answer),
    )
    assert first.verdict == VERDICT_SUPPORTED
    assert second.cached is True


def test_run_jury_requires_claim() -> None:
    with pytest.raises(ValueError):
        run_jury(
            request=CitationRequest(law_name="Rental Act", section_number="4"),
            law_title="Rental Act",
            section_number="4",
            section_text="Section 4.",
        )


def test_parsed_vote_defaults() -> None:
    assert ParsedVote().scored is False
    assert ParsedVote(verdict=VERDICT_SUPPORTED).scored is True


# ---------------------------------------------------------------- 纯数字体例（印度法系）


def test_numeric_style_rejects_bullet_list() -> None:
    from plugins.barlc_asean_law.adapter import _SECTION_NUMERIC_RE, _numeric_style_plausible

    bullets = "Heading\n1. first bullet\n2. second bullet\nNote\n5. unrelated\n"
    assert _numeric_style_plausible(list(_SECTION_NUMERIC_RE.finditer(bullets)), bullets) is False


def test_numeric_style_accepts_long_articles() -> None:
    from plugins.barlc_asean_law.adapter import _SECTION_NUMERIC_RE, _numeric_style_plausible

    line = "In this Act, unless there is anything repugnant in the subject or context, the provisions apply."
    text = "PRELIMINARY.\n" + "\n".join(f"{i}. {line}" for i in range(1, 12))
    assert _numeric_style_plausible(list(_SECTION_NUMERIC_RE.finditer(text)), text) is True
    assert len(BarlcAdapter.split_sections(text, lang="en")) == 11


def test_numeric_style_preferred_when_article_split_is_degenerate() -> None:
    """实测柬埔寨：Article 只在正文交叉引用处出现 → 37 条、中位段长 1 万字；数字体例 1296 条。"""
    from plugins.barlc_asean_law.adapter import _SECTION_EN_RE, _SECTION_NUMERIC_RE, _numeric_preferred

    body = "This is a long article body. " * 400
    text = "".join(
        f"Article {i} (cross reference),\n"
        + "".join(f"{i * 10 + k}. Real article heading\n{body}\n" for k in range(1, 6))
        for i in range(1, 5)
    )
    primary = list(_SECTION_EN_RE.finditer(text))
    numeric = list(_SECTION_NUMERIC_RE.finditer(text))
    assert _numeric_preferred(primary, numeric, text) is True
    sections = BarlcAdapter.split_sections(text, lang="en")
    # 改选数字体例：条数等于数字头条数，且没有一条是中位段长 5 万字的粘连块
    assert len(sections) == len(numeric) == 20
    assert sections[0].number == "11"


# ---------------------------------------------------------------- 按款引用


@pytest.mark.parametrize(
    ("raw", "expected"), [("4(2)", "2"), ("第4条第2款", "2"), ("第七条第（三）项", "3"), ("4", "")]
)
def test_subclause_of(raw: str, expected: str) -> None:
    assert BarlcAdapter.subclause_of(raw) == expected


def test_find_section_degrades_subclause_to_article() -> None:
    sections = [LawSection(number="4", text="Section 4. Rental must be in writing. (1) ... (2) ...")]
    found = BarlcAdapter.find_section(sections, "第4条第2款")
    assert found is sections[0]


# ---------------------------------------------------------------- 生效版本


def _detail_with_dates(effective: str | None, revise: str | None) -> LawDetail:
    base = _detail()
    return LawDetail(
        **{
            **{
                name: getattr(base, name)
                for name in base.__dataclass_fields__
                if name not in {"effective_date", "revise_date"}
            },
            "effective_date": effective,
            "revise_date": revise,
        }
    )


def test_version_warnings_flags_not_yet_effective() -> None:
    from plugins.barlc_asean_law.verify import _version_warnings

    warnings = _version_warnings(_detail_with_dates("2020-01-01", None), "2019-06-01")
    assert warnings and "尚未生效" in warnings[0]


def test_version_warnings_flags_later_revision() -> None:
    from plugins.barlc_asean_law.verify import _version_warnings

    warnings = _version_warnings(_detail_with_dates("2010-01-01", "2022-05-05"), "2020-01-01")
    assert warnings and "应适用旧版" in warnings[0]


def test_version_warnings_never_claims_validity() -> None:
    """BARLC 没有「是否现行有效」字段，没时点又没有修订时不许产生任何结论。"""
    from plugins.barlc_asean_law.verify import _version_warnings

    assert _version_warnings(_detail_with_dates("2010-01-01", None), "") == ()
    assert _version_warnings(_detail_with_dates(None, None), "2020-01-01") == ()


def test_version_warnings_rejects_non_iso_date() -> None:
    from plugins.barlc_asean_law.verify import _version_warnings

    warnings = _version_warnings(_detail_with_dates("2010-01-01", None), "2020年1月")
    assert warnings and "不是 YYYY-MM-DD" in warnings[0]


# ---------------------------------------------------------------- 上下文窗口


def test_neighbour_text_returns_adjacent_sections_only() -> None:
    from plugins.barlc_asean_law.verify import _neighbour_text

    sections = [LawSection(number=n, text=f"Section {n}. text") for n in ("1", "2", "3")]
    before, after = _neighbour_text(sections, sections[1])
    assert before.startswith("Section 1.")
    assert after.startswith("Section 3.")
    assert _neighbour_text(sections, sections[0])[0] == ""
    assert _neighbour_text(sections, sections[-1])[1] == ""


# ---------------------------------------------------------------- 国别码校验


def test_unknown_country_is_rejected_with_valid_codes() -> None:
    from plugins.barlc_asean_law.models import BarlcUnknownCountry

    class _CountryAdapter(_FakeAdapter):
        def known_country_codes(self):
            return {"LAWCOUNTRYTG", "LAWCOUNTRYMLXY"}

    verifier = JudicialVerifier(_CountryAdapter())
    with pytest.raises(BarlcUnknownCountry) as excinfo:
        verifier.resolve_law(CRED, law_name="Civil Code", country_code="LAWCOUNTRYMY")
    assert "LAWCOUNTRYMLXY" in str(excinfo.value)
    assert excinfo.value.country_code == "LAWCOUNTRYMY"


# ---------------------------------------------------------------- 款/项定位


def test_extract_paragraph_locates_parenthesised_clause() -> None:
    from plugins.barlc_asean_law.adapter import extract_paragraph

    text = "Section 4. Rental must be in writing. (1) Must be registered. (2) Fees apply."
    assert extract_paragraph(text, "2") == "(2) Fees apply."
    assert extract_paragraph(text, "9") == ""


def test_extract_paragraph_refuses_non_sequential_markers() -> None:
    """编号不连续 = 多半是正文里的编号引用，不是分项列表。"""
    from plugins.barlc_asean_law.adapter import extract_paragraph

    assert extract_paragraph("(2) a (4) b", "2") == ""
    assert extract_paragraph("(1) only", "1") == ""


def test_check_reports_matched_paragraph_but_judges_whole_article() -> None:
    """定位到款时要明说「判定仍基于整条」——引导句常在分项之外。"""
    text = "Section 4. Rental must be in writing. (1) Must be registered. (2) Fees apply."
    verifier = JudicialVerifier(
        _FakeAdapter(
            hits=[_hit("321381", "1999年商业和工业房地产租赁法", "Rental Act", "LAWCOUNTRYTG")],
            sections=[LawSection(number="4", text=text)],
        )
    )
    check = verifier.check(
        CRED,
        CitationRequest(law_name="Rental Act", section_number="第4条第2款"),
        jury=False,
    )
    assert check.matched_paragraph == "(2) Fees apply."
    assert check.section_text == text  # 判定单元仍是整条
    assert "判定仍基于整条原文" in check.reason


# ---------------------------------------------------------------- 分页懒匹配


def test_scan_pages_finds_law_on_later_page() -> None:
    """目标法排在第 61 位之后时，只看第一页会变成假「不存在该引用」。"""

    class _PagedAdapter(_FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[int] = []

        def search(self, credential, *, keyword, country_code=None, field="Title", page=1, page_size=20):
            self.calls.append(page)
            if page == 1:
                return 120, [_hit(f"x{i}", "", f"Unrelated Code {i}", "LAWCOUNTRYTG") for i in range(60)]
            return 120, [_hit("321381", "1999年商业和工业房地产租赁法", "Rental Act", "LAWCOUNTRYTG")]

    adapter = _PagedAdapter()
    verifier = JudicialVerifier(adapter)
    resolved = verifier.resolve_law(CRED, law_name="Rental Act", country_code="LAWCOUNTRYTG")

    assert resolved is not None
    assert resolved.detail.sys_id == "321381"
    assert adapter.calls == [1, 2], "应逐页懒取，命中即停"


def test_scan_pages_stops_when_first_page_matches() -> None:
    class _OnePageAdapter(_FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def search(self, credential, *, keyword, country_code=None, field="Title", page=1, page_size=20):
            self.calls += 1
            return (
                500,
                [_hit("321381", "1999年商业和工业房地产租赁法", "Rental Act", "LAWCOUNTRYTG")],
            )

    adapter = _OnePageAdapter()
    verifier = JudicialVerifier(adapter)
    verifier.resolve_law(CRED, law_name="Rental Act", country_code="LAWCOUNTRYTG")
    assert adapter.calls == 1, "第一页命中就不该再翻页"


# ---------------------------------------------------------------- 跨进程缓存


def test_shared_cache_prefers_backend_and_survives_failures() -> None:
    from plugins.barlc_asean_law.cache import SharedCache

    class _Backend:
        def __init__(self) -> None:
            self.store: dict[str, object] = {}

        def get(self, key: str):
            return self.store.get(key)

        def set(self, key: str, value, ttl: int):
            self.store[key] = value

        def delete(self, key: str):
            self.store.pop(key, None)

    cache = SharedCache(namespace="unit", ttl=60)
    backend = _Backend()
    cache._backend = backend  # 注入假后端，避免测试依赖 Redis
    cache.put(("a", "中文 键"), {"v": 1})
    assert cache.get(("a", "中文 键")) == {"v": 1}
    # 键必须被清洗（含中文/空格时摘要），不能把原文塞进缓存键
    assert all(" " not in key and "键" not in key for key in backend.store)

    class _Broken:
        def get(self, key):
            raise RuntimeError("redis down")

        def set(self, key, value, ttl):
            raise RuntimeError("redis down")

        def delete(self, key):
            raise RuntimeError("redis down")

    cache._backend = _Broken()
    cache.put(("b",), 2)  # 后端炸了也不能抛
    assert cache.get(("b",)) == 2  # 退化到进程内可用
