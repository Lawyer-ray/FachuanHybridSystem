"""合同自动导入的归一化层单测。

这些断言锁定的是**会让错误数据静默入库**的行为，改动 normalize 前请先读：
- 金额：中文大写、「各付/共付」取合计、风险比例**不能**被当成金额；
- 日期：相对/条件式表述返回 None（不猜），中文日期与逐位年份正确；
- 律师：``is_primary`` 排他，且主办必须落在能在表单里选中的（已匹配）人上；
- 当事人：律所必须被剔除（建 Client 会污染数据且 PROTECT 后删不掉）。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.contracts.models import FeeMode
from apps.contracts.services.contract.intake.extract_schema import ContractExtraction, ExtractedLawyer, ExtractedParty
from apps.contracts.services.contract.intake.normalize import (
    chinese_to_int,
    normalize_case_type,
    normalize_extraction,
    normalize_fee_mode,
    parse_amount,
    parse_date,
)
from apps.core.models.enums import CaseType

pytestmark = pytest.mark.unit


class TestChineseAmount:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("贰万", 20000),
            ("壹万零伍佰", 10500),
            ("叁万伍仟", 35000),
            ("壹拾万", 100000),
            ("壹佰贰拾万", 1200000),
        ],
    )
    def test_basic_units(self, text: str, expected: int) -> None:
        assert chinese_to_int(text) == expected

    def test_non_numeric_returns_none(self) -> None:
        assert chinese_to_int("律师费另议") is None


class TestParseAmount:
    def test_prefers_arabic_in_parentheses(self) -> None:
        amount, reason = parse_amount("律师费人民币壹万元整（10000.00）")
        assert amount == Decimal("10000.00")
        assert reason == ""

    def test_takes_total_not_share(self) -> None:
        """「各支付壹万元，共贰万元」必须取合计贰万，不能只取第一个壹万。"""
        amount, _ = parse_amount("甲方向乙方1、2各支付律师费人民币壹万元整（10000.00），共贰万元整（20000.00）")
        assert amount == Decimal("20000.00")

    @pytest.mark.parametrize(
        "text",
        ["按回款额的20%收取", "按回款额20%", "按实际回款比例分成"],
    )
    def test_risk_ratio_is_not_amount(self, text: str) -> None:
        """回归：比例曾被错误解析成 20 元写进固定律师费。"""
        amount, reason = parse_amount(text)
        assert amount is None
        assert "风险比例" in reason

    def test_wan_unit_with_decimal(self) -> None:
        amount, _ = parse_amount("律师费 0.5 万元")
        assert amount == Decimal("5000.00")

    def test_no_amount(self) -> None:
        amount, reason = parse_amount("")
        assert amount is None
        assert reason


class TestParseDate:
    def test_iso(self) -> None:
        assert parse_date("2026-11-10")[0] == date(2026, 11, 10)

    def test_chinese_digits_year(self) -> None:
        """回归：「二〇二六」是逐位读，曾被算成 6 年。"""
        assert parse_date("二〇二六年十一月十日")[0] == date(2026, 11, 10)

    @pytest.mark.parametrize(
        "text",
        ["签订三日内", "本合同生效后", "服务期间至税务机关作出结论为止", "长期"],
    )
    def test_relative_expressions_are_not_guessed(self, text: str) -> None:
        parsed, reason = parse_date(text)
        assert parsed is None
        assert "相对/条件式" in reason

    def test_blank_signature_line(self) -> None:
        parsed, _ = parse_date("年 月 日")
        assert parsed is None


class TestEnumNormalization:
    def test_chinese_alias(self) -> None:
        assert normalize_case_type("非诉") == (CaseType.SPECIAL.value, True)

    def test_unknown_case_type_not_guessed(self) -> None:
        value, ok = normalize_case_type("某种奇怪的类型")
        assert value == ""
        assert ok is False

    def test_fee_mode_english_passthrough(self) -> None:
        assert normalize_fee_mode("FULL_RISK") == (FeeMode.FULL_RISK.value, True)

    def test_fee_mode_chinese_alias(self) -> None:
        assert normalize_fee_mode("半风险收费")[0] == FeeMode.SEMI_RISK.value


def _extraction(**overrides: object) -> ContractExtraction:
    base: dict[str, object] = {
        "title": "非诉法律服务合同",
        "case_type": "special",
        "client_name": "某供应链公司",
        "parties": [
            ExtractedParty(name="某供应链公司", role_in_contract="甲方", id_number="91440300MA5ABCDE1"),
            ExtractedParty(name="某律师事务所", role_in_contract="乙方", is_law_firm=True),
        ],
        "lawyers": [],
    }
    base.update(overrides)
    return ContractExtraction(**base)  # type: ignore[arg-type]


class TestLawFirmExclusion:
    def test_law_firm_dropped_from_parties(self) -> None:
        draft = normalize_extraction(_extraction())
        names = [party.name for party in draft.parties]
        assert "某律师事务所" not in names
        assert "某供应链公司" in names
        assert any("已自动忽略律所" in w for w in draft.warnings)

    def test_law_firm_detected_even_if_model_forgets_flag(self) -> None:
        extraction = _extraction(
            parties=[
                ExtractedParty(name="某供应链公司", role_in_contract="甲方"),
                ExtractedParty(name="北京某（广州）律师事务所", role_in_contract="乙方", is_law_firm=False),
            ]
        )
        draft = normalize_extraction(extraction)
        assert [p.name for p in draft.parties] == ["某供应链公司"]


class TestPrimaryLawyer:
    def test_multiple_primaries_collapse_to_one(self) -> None:
        extraction = _extraction(
            lawyers=[
                ExtractedLawyer(name="张甲", is_primary=True),
                ExtractedLawyer(name="李乙", is_primary=True),
            ]
        )
        draft = normalize_extraction(extraction)
        assert sum(1 for lawyer in draft.lawyers if lawyer.is_primary) == 1
        assert "lawyers" in draft.needs_review

    def test_primary_prefers_matched_lawyer(self) -> None:
        """未匹配到系统账号的律师前端填不进表单，不能设为主办。"""
        extraction = _extraction(
            lawyers=[
                ExtractedLawyer(name="未入库", is_primary=True),
                ExtractedLawyer(name="已入库", is_primary=True),
            ]
        )
        draft = normalize_extraction(
            extraction,
            lawyer_lookup={"已入库": (7, "已入库")},
        )
        primary = [lawyer for lawyer in draft.lawyers if lawyer.is_primary]
        assert len(primary) == 1
        assert primary[0].lawyer_id == 7

    def test_unmatched_lawyer_left_blank(self) -> None:
        extraction = _extraction(lawyers=[ExtractedLawyer(name="查无此人", is_primary=False)])
        draft = normalize_extraction(extraction, lawyer_lookup={})
        assert draft.lawyers[0].lawyer_id is None
        assert draft.lawyers[0].matched is False


class TestClientMatching:
    def test_match_by_id_number(self) -> None:
        draft = normalize_extraction(
            _extraction(),
            client_lookup={"91440300MA5ABCDE1": (42, "某供应链公司")},
        )
        assert draft.parties[0].client_id == 42
        assert draft.parties[0].match_kind == "exact_id"

    def test_match_by_name(self) -> None:
        draft = normalize_extraction(
            _extraction(),
            client_lookup={"某供应链公司": (43, "某供应链公司")},
        )
        assert draft.parties[0].client_id == 43
        assert draft.parties[0].match_kind == "exact_name"

    def test_unmatched_party_has_no_client_id(self) -> None:
        draft = normalize_extraction(_extraction(), client_lookup={})
        assert draft.parties[0].client_id is None


class TestDraftFields:
    def test_contract_name_includes_client_and_matter(self) -> None:
        extraction = _extraction(matter_summary="税务稽查应对非诉咨询")
        draft = normalize_extraction(extraction)
        assert draft.fields["name"] == "某供应链公司_税务稽查应对非诉咨询"

    def test_redundant_custom_terms_dropped(self) -> None:
        """收费条款整段被抬进 custom_terms 时，与 fixed_amount 重复，应丢弃。"""
        extraction = _extraction(
            fee_mode="FIXED",
            amount_text="共贰万元整（20000.00）",
            custom_terms="甲方向乙方各支付律师费人民币壹万元整（10000.00），共贰万元整（20000.00）",
        )
        draft = normalize_extraction(extraction)
        assert draft.fields["fixed_amount"] == "20000.00"
        assert "custom_terms" not in draft.fields

    def test_meaningful_custom_terms_kept(self) -> None:
        extraction = _extraction(
            fee_mode="FIXED",
            amount_text="共贰万元整（20000.00）",
            custom_terms="律师费分两期支付，逾期按日万分之五计息，解除合同不予退还",
        )
        draft = normalize_extraction(extraction)
        assert "custom_terms" in draft.fields
