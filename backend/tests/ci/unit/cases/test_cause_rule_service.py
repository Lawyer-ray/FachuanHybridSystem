"""Tests for apps.cases.services.data.cause_rule_service constants and CauseRuleService."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.data.cause_rule_service import (
    DEFAULT_DISPLAY_CONFIG,
    DISPLAY_CONFIG,
    FEE_RANGES,
    FIXED_FEES,
    SPECIAL_CAUSE_CODES,
    SPECIAL_CAUSE_NAMES,
    CauseRuleService,
    SpecialCaseType,
)


class TestSpecialCaseType:
    def test_constants(self) -> None:
        assert SpecialCaseType.PERSONALITY_RIGHTS == "personality_rights"
        assert SpecialCaseType.IP == "ip"
        assert SpecialCaseType.PAYMENT_ORDER == "payment_order"
        assert SpecialCaseType.REVOKE_ARBITRATION == "revoke_arbitration"
        assert SpecialCaseType.PUBLIC_NOTICE == "public_notice"
        assert SpecialCaseType.LABOR_DISPUTE == "labor_dispute"


class TestCauseMappings:
    def test_special_cause_codes(self) -> None:
        assert SPECIAL_CAUSE_CODES["9001"] == SpecialCaseType.PERSONALITY_RIGHTS
        assert SPECIAL_CAUSE_CODES["9300"] == SpecialCaseType.IP
        assert SPECIAL_CAUSE_CODES["9363"] == SpecialCaseType.IP

    def test_special_cause_names_payment_order(self) -> None:
        assert SPECIAL_CAUSE_NAMES["申请支付令"] == SpecialCaseType.PAYMENT_ORDER
        assert SPECIAL_CAUSE_NAMES["申请海事支付令"] == SpecialCaseType.PAYMENT_ORDER

    def test_special_cause_names_revoke_arbitration(self) -> None:
        assert SPECIAL_CAUSE_NAMES["申请撤销仲裁裁决"] == SpecialCaseType.REVOKE_ARBITRATION

    def test_special_cause_names_public_notice(self) -> None:
        assert SPECIAL_CAUSE_NAMES["公示催告程序案件"] == SpecialCaseType.PUBLIC_NOTICE
        assert SPECIAL_CAUSE_NAMES["申请公示催告"] == SpecialCaseType.PUBLIC_NOTICE

    def test_special_cause_names_labor_dispute(self) -> None:
        assert SPECIAL_CAUSE_NAMES["劳动争议"] == SpecialCaseType.LABOR_DISPUTE


class TestFixedFees:
    def test_revoke_arbitration_fee(self) -> None:
        assert FIXED_FEES[SpecialCaseType.REVOKE_ARBITRATION] == Decimal("400")

    def test_public_notice_fee(self) -> None:
        assert FIXED_FEES[SpecialCaseType.PUBLIC_NOTICE] == Decimal("100")

    def test_labor_dispute_fee(self) -> None:
        assert FIXED_FEES[SpecialCaseType.LABOR_DISPUTE] == Decimal("10")


class TestFeeRanges:
    def test_personality_rights_range(self) -> None:
        r = FEE_RANGES[SpecialCaseType.PERSONALITY_RIGHTS]
        assert r["min"] == Decimal("100")
        assert r["max"] == Decimal("500")
        assert r["half_min"] == Decimal("50")
        assert r["half_max"] == Decimal("250")

    def test_ip_range(self) -> None:
        r = FEE_RANGES[SpecialCaseType.IP]
        assert r["min"] == Decimal("500")
        assert r["max"] == Decimal("1000")


class TestDisplayConfig:
    def test_payment_order_show_all(self) -> None:
        cfg = DISPLAY_CONFIG[SpecialCaseType.PAYMENT_ORDER]
        assert cfg["show_acceptance_fee"] is True
        assert cfg["show_half_fee"] is True
        assert cfg["show_payment_order_fee"] is True

    def test_revoke_arbitration_hide_all(self) -> None:
        cfg = DISPLAY_CONFIG[SpecialCaseType.REVOKE_ARBITRATION]
        assert cfg["show_acceptance_fee"] is False
        assert cfg["show_half_fee"] is False
        assert cfg["show_payment_order_fee"] is False

    def test_default_display_config(self) -> None:
        assert DEFAULT_DISPLAY_CONFIG["show_acceptance_fee"] is True
        assert DEFAULT_DISPLAY_CONFIG["show_payment_order_fee"] is False


class TestCauseRuleService:
    def setup_method(self) -> None:
        self.svc = CauseRuleService()

    @patch("apps.cases.services.data.wiring.get_cause_court_query_service")
    def test_detect_normal_cause(self, mock_wiring: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_cause_ancestor_names_internal.return_value = ["合同纠纷"]
        mock_svc.get_cause_ancestor_codes_internal.return_value = ["1000"]
        mock_wiring.return_value = mock_svc
        result = self.svc.detect_special_case_type(1)
        assert result is None

    @patch("apps.cases.services.data.wiring.get_cause_court_query_service")
    def test_detect_by_name(self, mock_wiring: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_cause_ancestor_names_internal.return_value = ["劳动争议"]
        mock_svc.get_cause_ancestor_codes_internal.return_value = ["1000"]
        mock_wiring.return_value = mock_svc
        result = self.svc.detect_special_case_type(1)
        assert result == SpecialCaseType.LABOR_DISPUTE

    @patch("apps.cases.services.data.wiring.get_cause_court_query_service")
    def test_detect_by_code(self, mock_wiring: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_cause_ancestor_names_internal.return_value = ["普通合同"]
        mock_svc.get_cause_ancestor_codes_internal.return_value = ["9001"]
        mock_wiring.return_value = mock_svc
        result = self.svc.detect_special_case_type(1)
        assert result == SpecialCaseType.PERSONALITY_RIGHTS

    @patch("apps.cases.services.data.wiring.get_cause_court_query_service")
    def test_get_fee_rule_normal(self, mock_wiring: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_cause_ancestor_names_internal.return_value = ["合同纠纷"]
        mock_svc.get_cause_ancestor_codes_internal.return_value = ["1000"]
        mock_wiring.return_value = mock_svc
        rule = self.svc.get_fee_rule(1)
        assert rule["special_case_type"] is None
        assert rule["use_property_rule"] is True

    @patch("apps.cases.services.data.wiring.get_cause_court_query_service")
    def test_get_fee_rule_labor_dispute(self, mock_wiring: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_cause_ancestor_names_internal.return_value = ["劳动争议"]
        mock_svc.get_cause_ancestor_codes_internal.return_value = []
        mock_wiring.return_value = mock_svc
        rule = self.svc.get_fee_rule(1)
        assert rule["special_case_type"] == SpecialCaseType.LABOR_DISPUTE
        assert rule["fixed_fee"] == Decimal("10")
        assert rule["use_property_rule"] is False
        assert "劳动争议" in rule["fee_display_text"]
