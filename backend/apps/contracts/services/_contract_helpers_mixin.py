"""合同服务辅助方法 Mixin（验证、权限、日志）"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.contracts.models import Contract, FeeMode

from apps.core.business_config import BusinessConfig

logger = logging.getLogger("apps.contracts")


class ContractHelpersMixin:
    """合同验证、权限检查、日志记录辅助方法"""

    config: BusinessConfig

    def _log_finance_change(
        self, contract_id: int, user_id: int, action: str, changes: dict[str, Any], level: str = "INFO"
    ) -> None:
        """记录财务变更日志"""
        try:
            from apps.contracts.models import ContractFinanceLog

            ContractFinanceLog.objects.create(
                contract_id=contract_id,
                action=action,
                level=level,
                actor_id=user_id,
                payload=changes,
            )
        except Exception as e:
            logger.error(f"记录财务日志失败: {e}", extra={"contract_id": contract_id, "action": action})

    def _validate_fee_mode(self, data: dict[str, Any]) -> None:
        """验证收费模式数据"""
        from apps.contracts.models import FeeMode as FeeModeModel

        fee_mode = data.get("fee_mode")
        fixed_amount = data.get("fixed_amount")
        risk_rate = data.get("risk_rate")
        custom_terms = data.get("custom_terms")
        errors: dict[str, str] = {}

        if fee_mode == FeeModeModel.FIXED:
            if not fixed_amount or float(fixed_amount) <= 0:
                errors["fixed_amount"] = "固定收费需填写金额"
        elif fee_mode == FeeModeModel.SEMI_RISK:
            if not fixed_amount or float(fixed_amount) <= 0:
                errors["fixed_amount"] = "半风险需填写前期金额"
            if not risk_rate or float(risk_rate) <= 0:
                errors["risk_rate"] = "半风险需填写风险比例"
        elif fee_mode == FeeModeModel.FULL_RISK:
            if not risk_rate or float(risk_rate) <= 0:
                errors["risk_rate"] = "全风险需填写风险比例"
        elif fee_mode == FeeModeModel.CUSTOM and (not custom_terms or not str(custom_terms).strip()):
            errors["custom_terms"] = "自定义收费需填写条款文本"

        if errors:
            raise ValidationException("收费模式验证失败", errors=errors)

    def _validate_stages(self, stages: list[str], case_type: str | None) -> list[str]:
        """验证代理阶段"""
        if not stages:
            return []
        valid_stages = [v for v, _ in self.config.get_stages_for_case_type(case_type)]
        invalid = set(stages) - set(valid_stages)
        if invalid:
            raise ValidationException(
                "无效的代理阶段", errors={"representation_stages": f"无效阶段: {', '.join(invalid)}"}
            )
        return stages

    def _check_contract_access(
        self,
        contract: Contract,
        user: Any,
        org_access: dict[str, Any] | None,
    ) -> bool:
        """检查用户是否有权访问合同"""
        if getattr(user, "is_admin", False):
            return True
        if not org_access:
            return False
        user_id = getattr(user, "id", None)
        has_access = (
            contract.assignments.filter(lawyer_id__in=org_access.get("lawyers", set())).exists()
            or (user_id is not None and contract.assignments.filter(lawyer_id=user_id).exists())
        )
        if not has_access:
            has_access = user_id is not None and contract.cases.filter(assignments__lawyer_id=user_id).exists()
        return has_access
