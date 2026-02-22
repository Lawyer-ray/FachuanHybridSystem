"""Business logic services."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from apps.documents.utils.formatters import format_currency, format_date, format_percentage, get_choice_display

# 当事人角色常量（对应 apps.contracts.models.PartyRole）
_ROLE_PRINCIPAL = "PRINCIPAL"
_ROLE_BENEFICIARY = "BENEFICIARY"
_ROLE_OPPOSING = "OPPOSING"

if TYPE_CHECKING:
    from apps.core.interfaces import IContractService

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    上下文构建器

    从数据库提取数据并构建替换词上下文字典.
    优先使用 EnhancedContextBuilder 进行上下文构建,
    同时保留直接构建的能力以支持向后兼容.
    """

    DEFAULT_DATE_FORMAT = "%Y年%m月%d日"

    def __init__(
        self,
        date_format: str | None = None,
        use_enhanced: bool = False,
        contract_service: IContractService | None = None,
    ) -> None:
        """
        初始化上下文构建器

        Args:
            date_format: 日期格式字符串
            use_enhanced: 是否使用 EnhancedContextBuilder(默认 True)
            contract_service: 合同服务(可选,用于依赖注入)
        """
        self.date_format = date_format or self.DEFAULT_DATE_FORMAT
        self._use_enhanced = use_enhanced
        self._enhanced_builder = None
        self._contract_service = contract_service

    @property
    def contract_service(self) -> IContractService:
        """延迟加载合同服务"""
        if self._contract_service is None:
            from apps.documents.services.wiring import get_contract_service

            self._contract_service = get_contract_service()
        return self._contract_service

    @property
    def enhanced_builder(self) -> Any:
        """延迟加载 EnhancedContextBuilder"""
        if self._enhanced_builder is None:
            from apps.documents.services.placeholders.context_builder import EnhancedContextBuilder

            self._enhanced_builder = EnhancedContextBuilder() # type: ignore
        return self._enhanced_builder

    def build_contract_context(self, contract_id: int) -> dict[str, Any]:
        """
        构建合同相关的完整上下文

        优先使用 EnhancedContextBuilder 通过占位符服务构建上下文,
        如果失败则回退到直接构建模式.

        Args:
            contract_id: 合同 ID

        Returns:
            包含所有替换词的字典
        """
        if self._use_enhanced:
            try:
                context = self.enhanced_builder.build_contract_context(contract_id)
                if context:
                    logger.debug("使用 EnhancedContextBuilder 构建合同上下文成功,合同ID: %s", contract_id)
                    return cast(dict[str, Any], context)
            except Exception as e:
                logger.warning(
                    "EnhancedContextBuilder 构建失败,回退到直接构建模式: %s", e,
                    extra={"contract_id": contract_id},
                )

        return self._build_contract_context_directly(contract_id)

    def _build_contract_context_directly(self, contract_id: int) -> dict[str, Any]:
        """
        直接从数据库构建合同上下文(向后兼容)

        通过 ServiceLocator 获取合同数据,避免跨模块直接导入 Model.

        Args:
            contract_id: 合同 ID

        Returns:
            包含所有替换词的字典
        """
        # 使用 ServiceLocator 获取合同服务,避免跨模块直接导入 Model
        # Requirements: 1.3
        contract_dto = self.contract_service.get_contract_with_details_internal(contract_id)
        if contract_dto is None:
            logger.warning("合同不存在: %s", contract_id)
            return {}

        # 从 DTO 构建上下文
        context: dict[str, Any] = {
            "contract_name": contract_dto.get("name") or "",
            "contract_type": contract_dto.get("case_type_display") or "",
            "contract_type_code": contract_dto.get("case_type") or "",
            "contract_status": contract_dto.get("status_display") or "",
            "contract_date": self._format_date(contract_dto.get("specified_date")),
            "contract_start_date": self._format_date(contract_dto.get("start_date")),
            "contract_end_date": self._format_date(contract_dto.get("end_date")),
            "fee_mode": contract_dto.get("fee_mode_display") or "",
            "fee_mode_code": contract_dto.get("fee_mode") or "",
            "fixed_amount": self._format_currency(contract_dto.get("fixed_amount")),
            "fixed_amount_raw": contract_dto.get("fixed_amount") or Decimal("0"),
            "risk_rate": self._format_percentage(contract_dto.get("risk_rate")),
            "risk_rate_raw": contract_dto.get("risk_rate") or Decimal("0"),
            "custom_terms": contract_dto.get("custom_terms") or "",
            "representation_stages": ", ".join(contract_dto.get("representation_stages") or []),
        }

        # 处理当事人信息
        parties = contract_dto.get("contract_parties") or []
        principals = [p for p in parties if p.get("role") == _ROLE_PRINCIPAL]
        beneficiaries = [p for p in parties if p.get("role") == _ROLE_BENEFICIARY]
        opposing = [p for p in parties if p.get("role") == _ROLE_OPPOSING]

        def _get_client_field(party: dict[str, Any], field: str) -> str:
            """兼容嵌套 client 字典和扁平结构两种 DTO 格式"""
            nested = party.get("client")
            if isinstance(nested, dict):
                return nested.get(field) or ""
            # 扁平结构：client_name / id_number / phone / address 直接在 party 里
            if field == "name":
                return party.get("client_name") or ""
            return party.get(field) or ""

        if principals:
            context.update(
                {
                    "principal_name": _get_client_field(principals[0], "name"),
                    "principal_id_number": _get_client_field(principals[0], "id_number"),
                    "principal_phone": _get_client_field(principals[0], "phone"),
                    "principal_address": _get_client_field(principals[0], "address"),
                    "all_principals": [
                        {
                            "name": _get_client_field(p, "name"),
                            "id_number": _get_client_field(p, "id_number"),
                        }
                        for p in principals
                    ],
                }
            )
        else:
            context.update(
                {
                    "principal_name": "",
                    "principal_id_number": "",
                    "principal_phone": "",
                    "principal_address": "",
                    "all_principals": [],
                }
            )

        if beneficiaries:
            context.update(
                {
                    "beneficiary_name": _get_client_field(beneficiaries[0], "name"),
                    "beneficiary_id_number": _get_client_field(beneficiaries[0], "id_number"),
                }
            )
        else:
            context.update({"beneficiary_name": "", "beneficiary_id_number": ""})

        if opposing:
            context.update(
                {
                    "opposing_party_name": _get_client_field(opposing[0], "name"),
                    "all_opposing_parties": [_get_client_field(p, "name") for p in opposing],
                }
            )
        else:
            context.update({"opposing_party_name": "", "all_opposing_parties": []})

        # 处理律师信息
        assignments = contract_dto.get("assignments") or []

        def _get_lawyer_field(assignment: dict[str, Any], field: str) -> str:
            """兼容嵌套 lawyer 字典和扁平结构两种 DTO 格式"""
            nested = assignment.get("lawyer")
            if isinstance(nested, dict):
                return nested.get(field) or ""
            # 扁平结构：lawyer_name / lawyer_phone / lawyer_license_no 直接在 assignment 里
            if field in ("real_name", "username"):
                return assignment.get("lawyer_name") or ""
            if field == "phone":
                return assignment.get("lawyer_phone") or ""
            if field == "license_no":
                return assignment.get("lawyer_license_no") or ""
            return assignment.get(field) or ""

        primary_assignment = next((a for a in assignments if a.get("is_primary")), None)

        if primary_assignment:
            context.update(
                {
                    "primary_lawyer_name": _get_lawyer_field(primary_assignment, "real_name"),
                    "primary_lawyer_phone": _get_lawyer_field(primary_assignment, "phone"),
                    "primary_lawyer_license": _get_lawyer_field(primary_assignment, "license_no"),
                }
            )
        elif assignments:
            context.update(
                {
                    "primary_lawyer_name": _get_lawyer_field(assignments[0], "real_name"),
                    "primary_lawyer_phone": _get_lawyer_field(assignments[0], "phone"),
                    "primary_lawyer_license": _get_lawyer_field(assignments[0], "license_no"),
                }
            )
        else:
            context.update({"primary_lawyer_name": "", "primary_lawyer_phone": "", "primary_lawyer_license": ""})

        context["all_lawyers"] = [
            {
                "name": _get_lawyer_field(a, "real_name"),
                "is_primary": bool(a.get("is_primary")),
            }
            for a in assignments
        ]

        return context

    def _format_date(self, value: date | None) -> str:
        return format_date(value, self.date_format)

    def _format_currency(self, value: Decimal | None) -> str:
        return format_currency(value)

    def _format_percentage(self, value: Decimal | None) -> str:
        return format_percentage(value)

    def _build_contract_info_from_dict(self, contract_data: dict[str, Any]) -> dict[str, Any]:
        """从字典数据构建合同基本信息"""
        from apps.core.enums import CaseType

        return {
            "contract_name": contract_data.get("name") or "",
            "contract_type": get_choice_display(contract_data.get("case_type"), CaseType), # type: ignore
            "contract_type_code": contract_data.get("case_type") or "",
            "contract_status": contract_data.get("status_display") or "",
            "contract_date": format_date(contract_data.get("specified_date"), self.date_format),
            "contract_start_date": format_date(contract_data.get("start_date"), self.date_format),
            "contract_end_date": format_date(contract_data.get("end_date"), self.date_format),
            "fee_mode": contract_data.get("fee_mode_display") or "",
            "fee_mode_code": contract_data.get("fee_mode") or "",
            "fixed_amount": format_currency(contract_data.get("fixed_amount")),
            "fixed_amount_raw": contract_data.get("fixed_amount") or Decimal("0"),
            "risk_rate": format_percentage(contract_data.get("risk_rate")),
            "risk_rate_raw": contract_data.get("risk_rate") or Decimal("0"),
            "custom_terms": contract_data.get("custom_terms") or "",
            "representation_stages": ", ".join(contract_data.get("representation_stages") or []),
        }

    def _build_party_info_from_dict(self, contract_data: dict[str, Any]) -> dict[str, Any]:
        """从字典数据构建当事人信息"""
        context: dict[str, Any] = {}

        # 获取当事人列表
        parties = contract_data.get("contract_parties") or []

        # 按角色分组当事人
        parties_by_role: dict[str, list[Any]] = {
            _ROLE_PRINCIPAL: [],
            _ROLE_BENEFICIARY: [],
            _ROLE_OPPOSING: [],
        }

        for party in parties:
            role = party.get("role")
            if role in parties_by_role:
                parties_by_role[role].append(party)

        # 委托人(取第一个)
        principals = parties_by_role[_ROLE_PRINCIPAL]
        if principals:
            principal = principals[0]
            client = principal.get("client") or {}
            context.update(
                {
                    "principal_name": client.get("name") or "",
                    "principal_id_number": client.get("id_number") or "",
                    "principal_phone": client.get("phone") or "",
                    "principal_address": client.get("address") or "",
                }
            )
            # 所有委托人列表
            context["all_principals"] = [
                {"name": p.get("client", {}).get("name"), "id_number": p.get("client", {}).get("id_number")}
                for p in principals
            ]
        else:
            context.update(
                {
                    "principal_name": "",
                    "principal_id_number": "",
                    "principal_phone": "",
                    "principal_address": "",
                    "all_principals": [],
                }
            )

        # 受益人
        beneficiaries = parties_by_role[_ROLE_BENEFICIARY]
        if beneficiaries:
            beneficiary = beneficiaries[0]
            client = beneficiary.get("client") or {}
            context.update(
                {
                    "beneficiary_name": client.get("name") or "",
                    "beneficiary_id_number": client.get("id_number") or "",
                }
            )
        else:
            context.update(
                {
                    "beneficiary_name": "",
                    "beneficiary_id_number": "",
                }
            )

        # 对方当事人
        opposing = parties_by_role[_ROLE_OPPOSING]
        if opposing:
            context["opposing_party_name"] = opposing[0].get("client", {}).get("name") or ""
            context["all_opposing_parties"] = [p.get("client", {}).get("name") for p in opposing]
        else:
            context["opposing_party_name"] = ""
            context["all_opposing_parties"] = []

        return context

    def _build_lawyer_info_from_dict(self, contract_data: dict[str, Any]) -> dict[str, Any]:
        """从字典数据构建律师信息"""
        context: dict[str, Any] = {}

        assignments = contract_data.get("assignments") or []

        # 主办律师
        primary_assignment = next((a for a in assignments if a.get("is_primary")), None)
        if primary_assignment:
            lawyer = primary_assignment.get("lawyer") or {}
            context.update(
                {
                    "primary_lawyer_name": lawyer.get("real_name") or lawyer.get("username") or "",
                    "primary_lawyer_phone": lawyer.get("phone") or "",
                    "primary_lawyer_license": lawyer.get("license_no") or "",
                }
            )
        elif assignments:
            # 没有主办律师,取第一个
            lawyer = assignments[0].get("lawyer") or {}
            context.update(
                {
                    "primary_lawyer_name": lawyer.get("real_name") or lawyer.get("username") or "",
                    "primary_lawyer_phone": lawyer.get("phone") or "",
                    "primary_lawyer_license": lawyer.get("license_no") or "",
                }
            )
        else:
            context.update(
                {
                    "primary_lawyer_name": "",
                    "primary_lawyer_phone": "",
                    "primary_lawyer_license": "",
                }
            )

        # 所有律师列表
        context["all_lawyers"] = [
            {
                "name": a.get("lawyer", {}).get("real_name") or a.get("lawyer", {}).get("username") or "",
                "phone": a.get("lawyer", {}).get("phone") or "",
                "license": a.get("lawyer", {}).get("license_no") or "",
                "is_primary": a.get("is_primary", False),
            }
            for a in assignments
        ]

        return context
