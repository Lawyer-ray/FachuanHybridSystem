"""Business logic services."""

from __future__ import annotations

from typing import Any

from apps.contracts.models import FeeMode
from apps.core.business_config import BusinessConfig
from apps.core.exceptions import ValidationException


class ContractValidator:
    def __init__(self, config: BusinessConfig) -> None:
        self.config = config

    def validate_fee_mode(self, data: dict[str, Any]) -> None:
        fee_mode = data.get("fee_mode")
        errors: dict[str, str] = {}

        validators = {
            FeeMode.FIXED: self._validate_fixed,
            FeeMode.SEMI_RISK: self._validate_semi_risk,
            FeeMode.FULL_RISK: self._validate_full_risk,
            FeeMode.CUSTOM: self._validate_custom,
        }

        validator = validators.get(fee_mode)
        if validator:
            validator(data, errors)

        if errors:
            raise ValidationException("收费模式验证失败", errors=errors)

    def _validate_fixed(self, data: dict[str, Any], errors: dict[str, str]) -> None:
        if not data.get("fixed_amount") or float(data["fixed_amount"]) <= 0:
            errors["fixed_amount"] = "固定收费需填写金额"

    def _validate_semi_risk(self, data: dict[str, Any], errors: dict[str, str]) -> None:
        if not data.get("fixed_amount") or float(data["fixed_amount"]) <= 0:
            errors["fixed_amount"] = "半风险需填写前期金额"
        if not data.get("risk_rate") or float(data["risk_rate"]) <= 0:
            errors["risk_rate"] = "半风险需填写风险比例"

    def _validate_full_risk(self, data: dict[str, Any], errors: dict[str, str]) -> None:
        if not data.get("risk_rate") or float(data["risk_rate"]) <= 0:
            errors["risk_rate"] = "全风险需填写风险比例"

    def _validate_custom(self, data: dict[str, Any], errors: dict[str, str]) -> None:
        if not data.get("custom_terms") or not str(data["custom_terms"]).strip():
            errors["custom_terms"] = "自定义收费需填写条款文本"

    def validate_stages(self, stages: list[str], case_type: str | None) -> list[str]:
        if not stages:
            return []

        valid_stages = [v for v, _ in self.config.get_stages_for_case_type(case_type)]
        invalid = set(stages) - set(valid_stages)
        if invalid:
            raise ValidationException(
                "无效的代理阶段", errors={"representation_stages": f"无效阶段: {', '.join(invalid)}"}
            )

        return stages
