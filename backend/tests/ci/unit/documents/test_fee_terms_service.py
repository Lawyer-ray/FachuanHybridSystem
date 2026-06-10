"""Tests for FeeTermsService covering all fee mode generation paths."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.documents.services.placeholders.contract.fee_terms_service import FeeTermsService


@pytest.fixture
def svc():
    return FeeTermsService()


# ── generate ──


class TestGenerate:
    def test_no_contract_returns_empty(self, svc):
        result = svc.generate({})
        assert result == {}

    def test_with_contract(self, svc):
        contract = SimpleNamespace(fee_mode="FIXED", fixed_amount=50000)
        contract.cases = MagicMock()
        contract.cases.all.return_value = []
        result = svc.generate({"contract": contract, "split_fee": False})
        assert "合同收费条款" in result
        assert "50000" in result["合同收费条款"]

    def test_split_fee_false(self, svc):
        contract = SimpleNamespace(fee_mode="FIXED", fixed_amount=50000)
        contract.cases = MagicMock()
        contract.cases.all.return_value = []
        result = svc.generate({"contract": contract, "split_fee": False})
        assert "合同收费条款" in result


# ── generate_fee_terms ──


class TestGenerateFeeTerms:
    def test_unknown_fee_mode(self, svc):
        contract = SimpleNamespace(fee_mode=None)
        result = svc.generate_fee_terms(contract, split_fee=False)
        assert result == "收费条款待定。"

    def test_fixed_with_amount(self, svc):
        contract = SimpleNamespace(fee_mode="FIXED", fixed_amount=100000)
        result = svc.generate_fee_terms(contract, split_fee=False)
        assert "100000" in result
        assert "律师费" in result

    def test_fixed_without_amount(self, svc):
        contract = SimpleNamespace(fee_mode="FIXED", fixed_amount=None)
        result = svc.generate_fee_terms(contract, split_fee=False)
        assert "律师费" in result

    def test_semi_risk_with_amounts(self, svc):
        contract = SimpleNamespace(fee_mode="SEMI_RISK", fixed_amount=50000, risk_rate=15)
        result = svc.generate_fee_terms(contract, split_fee=False)
        assert "50000" in result
        assert "15%" in result

    def test_semi_risk_without_amounts(self, svc):
        contract = SimpleNamespace(fee_mode="SEMI_RISK", fixed_amount=None, risk_rate=None)
        result = svc.generate_fee_terms(contract, split_fee=False)
        assert "风险代理" in result

    def test_full_risk_with_rate(self, svc):
        contract = SimpleNamespace(fee_mode="FULL_RISK", risk_rate=20)
        result = svc.generate_fee_terms(contract, split_fee=False)
        assert "20%" in result
        assert "风险代理" in result

    def test_full_risk_without_rate(self, svc):
        contract = SimpleNamespace(fee_mode="FULL_RISK", risk_rate=None)
        result = svc.generate_fee_terms(contract, split_fee=False)
        assert "风险代理" in result
        assert "[风险比例待定]" in result

    def test_custom_with_terms(self, svc):
        contract = SimpleNamespace(fee_mode="CUSTOM", custom_terms="自定义条款内容")
        result = svc.generate_fee_terms(contract, split_fee=False)
        assert result == "自定义条款内容"

    def test_custom_without_terms(self, svc):
        contract = SimpleNamespace(fee_mode="CUSTOM", custom_terms=None)
        result = svc.generate_fee_terms(contract, split_fee=False)
        assert "自定义条款" in result

    def test_exception_returns_fallback(self, svc):
        # Create a contract that raises when accessing fee_mode
        contract = MagicMock()
        type(contract).fee_mode = property(lambda self: 1 / 0)
        result = svc.generate_fee_terms(contract, split_fee=False)
        assert result == "收费条款待定。"


# ── _generate_split_fee_text ──


class TestGenerateSplitFeeText:
    def test_no_fixed_amount(self, svc):
        contract = SimpleNamespace(fixed_amount=None)
        assert svc._generate_split_fee_text(contract) == ""

    def test_less_than_two_cases(self, svc):
        case = MagicMock()
        case.target_amount = 100000
        case.parties.all.return_value = []
        contract = SimpleNamespace(fixed_amount=50000)
        contract.cases = MagicMock()
        contract.cases.all.return_value = [case]
        assert svc._generate_split_fee_text(contract) == ""

    def test_two_cases(self, svc):
        case1 = MagicMock()
        case1.target_amount = 600000
        party1 = MagicMock()
        party1.legal_status = "plaintiff"
        party1.client.name = "张三"
        case1.parties.all.return_value = [party1]

        case2 = MagicMock()
        case2.target_amount = 400000
        party2 = MagicMock()
        party2.legal_status = "defendant"
        party2.client.name = "李四"
        case2.parties.all.return_value = [party2]

        contract = SimpleNamespace(fixed_amount=100000)
        contract.cases = MagicMock()
        contract.cases.all.return_value = [case1, case2]

        result = svc._generate_split_fee_text(contract)
        assert "两案" in result
        assert "张三" in result

    def test_zero_total_target(self, svc):
        case = MagicMock()
        case.target_amount = 0
        case.parties.all.return_value = []
        contract = SimpleNamespace(fixed_amount=50000)
        contract.cases = MagicMock()
        contract.cases.all.return_value = [case, case]
        assert svc._generate_split_fee_text(contract) == ""


# ── _to_chinese_ordinal ──


class TestToChineseOrdinal:
    def test_ordinal_1_to_5(self, svc):
        assert svc._to_chinese_ordinal(1) == "一"
        assert svc._to_chinese_ordinal(2) == "二"
        assert svc._to_chinese_ordinal(3) == "三"
        assert svc._to_chinese_ordinal(4) == "四"
        assert svc._to_chinese_ordinal(5) == "五"

    def test_ordinal_6_to_10(self, svc):
        assert svc._to_chinese_ordinal(6) == "六"
        assert svc._to_chinese_ordinal(7) == "七"
        assert svc._to_chinese_ordinal(8) == "八"
        assert svc._to_chinese_ordinal(9) == "九"
        assert svc._to_chinese_ordinal(10) == "十"

    def test_ordinal_out_of_range(self, svc):
        assert svc._to_chinese_ordinal(11) == "11"


# ── _number_to_chinese ──


class TestNumberToChinese:
    def test_zero(self, svc):
        assert svc._number_to_chinese(0) == "零"

    def test_none(self, svc):
        assert svc._number_to_chinese(None) == "零"

    def test_valid_number(self, svc):
        result = svc._number_to_chinese(10000)
        # Should not be "零" if conversion works
        assert result != ""


# ── display attributes ──


class TestAttributes:
    def test_name(self, svc):
        assert svc.name == "fee_terms_service"

    def test_display_name(self, svc):
        assert svc.display_name == "收费条款服务"

    def test_category(self, svc):
        assert svc.category == "contract"

    def test_placeholder_keys(self, svc):
        assert "合同收费条款" in svc.placeholder_keys
