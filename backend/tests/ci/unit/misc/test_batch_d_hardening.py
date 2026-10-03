"""批次 D 速赢项回归测试。

- json.loads 裸读请求体加固：非法 JSON 必须 400（ValidationException）而非 500
- 收费模式校验 Decimal 化：非数值输入不再抛 ValueError，而是走 errors 字典
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from apps.core.exceptions import ValidationException


@pytest.mark.django_db
class TestRawJsonBodyHardening:
    def test_image_rotation_body_rejects_malformed_json(self):
        from apps.image_rotation.api.image_rotation_api import _body

        request = RequestFactory().post("/x/", data="{not-json", content_type="application/json")
        with pytest.raises(ValidationException) as exc_info:
            _body(request)
        assert "JSON" in exc_info.value.message

    def test_image_rotation_body_accepts_valid_json(self):
        from apps.image_rotation.api.image_rotation_api import _body

        request = RequestFactory().post("/x/", data='{"a": 1}', content_type="application/json")
        assert _body(request) == {"a": 1}

    def test_evidence_sorting_body_rejects_malformed_json(self):
        from apps.evidence_sorting.api.evidence_sorting_api import _body

        request = RequestFactory().post("/x/", data="[broken", content_type="application/json")
        with pytest.raises(ValidationException):
            _body(request)


class TestFeeModeDecimalValidation:
    def _validator(self):
        from apps.contracts.services.contract.domain.validator import ContractValidator

        return ContractValidator()

    def test_non_numeric_amount_reports_error_not_crash(self):
        """非数值金额不再 ValueError(500)，而是进入 errors。"""
        errors: dict[str, str] = {}
        self._validator()._validate_fixed({"fixed_amount": "abc"}, errors)
        assert errors["fixed_amount"] == "固定收费需填写金额"

    def test_numeric_string_amount_accepted(self):
        errors: dict[str, str] = {}
        self._validator()._validate_fixed({"fixed_amount": "10000.50"}, errors)
        assert "fixed_amount" not in errors

    def test_negative_amount_rejected(self):
        errors: dict[str, str] = {}
        self._validator()._validate_semi_risk({"fixed_amount": "-1", "risk_rate": "0.1"}, errors)
        assert errors["fixed_amount"] == "半风险需填写前期金额"
        assert "risk_rate" not in errors
