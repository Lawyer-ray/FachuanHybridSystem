import unittest
from unittest.mock import MagicMock

from apps.contracts.models import FeeMode
from apps.contracts.services.contract.contract_validator import ContractValidator
from apps.core.exceptions import ValidationException


class TestContractValidator(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock()
        self.validator = ContractValidator(config=self.mock_config)

    def test_validate_fee_mode_fixed(self):
        """测试固定收费模式校验"""
        # Valid
        self.validator.validate_fee_mode({"fee_mode": FeeMode.FIXED, "fixed_amount": "1000"})

        # Invalid
        with self.assertRaises(ValidationException) as cm:
            self.validator.validate_fee_mode({"fee_mode": FeeMode.FIXED, "fixed_amount": "0"})
        self.assertIn("fixed_amount", cm.exception.errors)

    def test_validate_fee_mode_semi_risk(self):
        """测试半风险模式校验"""
        # Valid
        self.validator.validate_fee_mode({"fee_mode": FeeMode.SEMI_RISK, "fixed_amount": "1000", "risk_rate": "0.1"})

        # Missing risk_rate
        with self.assertRaises(ValidationException) as cm:
            self.validator.validate_fee_mode({"fee_mode": FeeMode.SEMI_RISK, "fixed_amount": "1000"})
        self.assertIn("risk_rate", cm.exception.errors)

    def test_validate_fee_mode_custom(self):
        """测试自定义模式校验"""
        # Valid
        self.validator.validate_fee_mode({"fee_mode": FeeMode.CUSTOM, "custom_terms": "some terms"})

        # Empty terms
        with self.assertRaises(ValidationException) as cm:
            self.validator.validate_fee_mode({"fee_mode": FeeMode.CUSTOM, "custom_terms": "  "})
        self.assertIn("custom_terms", cm.exception.errors)

    def test_validate_stages_valid(self):
        """测试有效的阶段验证"""
        self.mock_config.get_stages_for_case_type.return_value = [("stage1", "Stage 1"), ("stage2", "Stage 2")]

        result = self.validator.validate_stages(["stage1"], "civil")
        self.assertEqual(result, ["stage1"])

    def test_validate_stages_invalid(self):
        """测试无效的阶段验证"""
        self.mock_config.get_stages_for_case_type.return_value = [("stage1", "Stage 1")]

        with self.assertRaises(ValidationException) as cm:
            self.validator.validate_stages(["invalid_stage"], "civil")
        self.assertIn("representation_stages", cm.exception.errors)
