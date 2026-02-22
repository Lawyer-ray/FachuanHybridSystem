from decimal import Decimal
from unittest.mock import Mock

from apps.documents.services.placeholders.contract.advisor_fee_terms_service import AdvisorFeeTermsService
from apps.documents.services.placeholders.contract.fee_terms_service import FeeTermsService


class TestFeeTermsFix:
    def test_fixed_fee_terms_no_duplicate_zheng(self):
        service = FeeTermsService()

        contract = Mock()
        contract.fee_mode = "fixed"
        contract.fixed_amount = Decimal("30000.00")

        result = service.generate_fee_terms(contract)

        assert "元整整" not in result
        assert "人民币叁万元整" in result
        assert result == "本合同签订之日起5日内，甲方向乙方一次性支付律师费30000.0元（大写：人民币叁万元整）。"

    def test_semi_risk_fee_terms_no_duplicate_zheng(self):
        service = FeeTermsService()

        contract = Mock()
        contract.fee_mode = "semi_risk"
        contract.fixed_amount = Decimal("10000.00")
        contract.risk_rate = 20

        result = service.generate_fee_terms(contract)

        assert "元整整" not in result
        assert "人民币壹万元整" in result

    def test_advisor_fixed_fee_terms_no_duplicate_zheng(self):
        service = AdvisorFeeTermsService()

        contract = Mock()
        contract.fee_mode = "fixed"
        contract.fixed_amount = Decimal("50000.00")

        result = service.generate_advisor_fee_terms(contract)

        assert "元整整" not in result
        assert "人民币伍万元整" in result
        assert result == "甲方向乙方支付法律顾问费¥50000.0元（大写：人民币伍万元整）"

    def test_amount_with_decimal(self):
        service = FeeTermsService()

        contract = Mock()
        contract.fee_mode = "fixed"
        contract.fixed_amount = Decimal("30000.50")

        result = service.generate_fee_terms(contract)

        assert "元整整" not in result
        assert "伍角" in result or "元伍角" in result
