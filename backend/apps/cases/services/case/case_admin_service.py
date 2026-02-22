"""Business logic services."""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction

from apps.cases.models import Case, CaseAssignment, CaseNumber, CaseParty, SupervisingAuthority

from .wiring import get_case_filing_number_service, get_document_service

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseFilingNumberService, IDocumentService

logger = logging.getLogger(__name__)


class CaseAdminService:
    """案件 Admin 服务"""

    def __init__(
        self,
        document_service: IDocumentService | None = None,
        filing_number_service: ICaseFilingNumberService | None = None,
    ) -> None:
        """
        构造函数支持依赖注入

            document_service: 文档服务实例(可选,用于依赖注入)
            filing_number_service: 建档编号服务实例(可选,用于依赖注入)
        """
        self._document_service = document_service
        self._filing_number_service = filing_number_service

    @property
    def document_service(self) -> IDocumentService:
        """
        延迟加载文档服务

        通过 ServiceLocator 获取 IDocumentService 实例,
        支持依赖注入以便于测试.

            IDocumentService 实例
        """
        if self._document_service is None:
            self._document_service = get_document_service()
        return self._document_service

    @property
    def filing_number_service(self) -> ICaseFilingNumberService:
        """
        延迟加载建档编号服务

        支持依赖注入以便于测试.

            FilingNumberService 实例
        """
        if self._filing_number_service is None:
            self._filing_number_service = get_case_filing_number_service()
        return self._filing_number_service

    def get_matched_folder_templates(self, case_type: str, legal_statuses: list[str] | None = None) -> str:
        """
        获取匹配的文件夹模板

            case_type: 案件类型
            legal_statuses: 案件的诉讼地位列表(我方当事人的诉讼地位)

            模板名称字符串,多个模板用"、"分隔
            如果查询失败返回 "查询失败"
        """
        try:
            if legal_statuses:
                return self.document_service.get_matched_folder_templates_with_legal_status(case_type, legal_statuses)
            return self.document_service.get_matched_folder_templates(case_type)
        except Exception:
            logger.exception(
                "get_matched_folder_templates_failed", extra={"case_type": case_type, "legal_statuses": legal_statuses}
            )
            return str(_("查询失败"))

    def get_matched_case_file_templates(self, case_type: str, case_stage: str) -> list[dict[str, Any]]:
        try:
            return self.document_service.find_matching_case_file_templates(
                case_type=case_type,
                case_stage=case_stage,
            )
        except Exception:
            logger.exception(
                "get_matched_case_file_templates_failed", extra={"case_type": case_type, "case_stage": case_stage}
            )
            return []

    @transaction.atomic
    def duplicate_case(self, case_id: int) -> Case:
        """
        复制案件及其所有关联数据(不复制日志和群聊)

            case_id: 原案件ID

            新创建的案件对象
        """
        # 获取原案件
        original = Case.objects.get(pk=case_id)

        # 复制主对象
        new_case = Case.objects.create(
            contract=original.contract,
            is_archived=False,  # 副本默认未建档
            name=f"{original.name} (副本)",
            status=original.status,
            effective_date=original.effective_date,
            cause_of_action=original.cause_of_action,
            target_amount=original.target_amount,
            case_type=original.case_type,
            current_stage=original.current_stage,
        )

        # 批量复制当事人
        parties_to_create = [
            CaseParty(
                case=new_case,
                client=party.client,
                legal_status=party.legal_status,
            )
            for party in original.parties.all()
        ]
        CaseParty.objects.bulk_create(parties_to_create)

        # 批量复制律师指派
        assignments_to_create = [
            CaseAssignment(
                case=new_case,
                lawyer=assignment.lawyer,
            )
            for assignment in original.assignments.all()
        ]
        CaseAssignment.objects.bulk_create(assignments_to_create)

        # 批量复制主管机关
        authorities_to_create = [
            SupervisingAuthority(
                case=new_case,
                name=authority.name,
                authority_type=authority.authority_type,
            )
            for authority in original.supervising_authorities.all()
        ]
        SupervisingAuthority.objects.bulk_create(authorities_to_create)

        # 批量复制案号
        case_numbers_to_create = [
            CaseNumber(
                case=new_case,
                number=case_number.number,
                remarks=case_number.remarks,
            )
            for case_number in original.case_numbers.all()
        ]
        CaseNumber.objects.bulk_create(case_numbers_to_create)

        # 注意:不复制 CaseLog(日志)和 CaseChat(群聊)

        return new_case

    @transaction.atomic
    def handle_case_filing_change(self, case_id: int, is_archived: bool) -> str | None:
        """
        处理案件建档状态变化

        业务逻辑:
        - 如果 is_archived=True 且 filing_number 为空,调用 FilingNumberService 生成编号
        - 如果 is_archived=True 且 filing_number 已存在,返回现有编号
        - 如果 is_archived=False,不修改 filing_number(保留在数据库中)

            case_id: 案件ID
            is_archived: 是否已建档

            str | None: 建档编号(如果已建档)

            NotFoundError: 案件不存在
            ValidationException: 数据验证失败

        Requirements: 5.1, 5.2, 6.1, 6.2, 6.3, 6.4
        """
        from apps.core.exceptions import NotFoundError

        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID为 {case_id} 的案件不存在"}
            ) from None

        # 如果取消建档,不修改 filing_number(保留在数据库中)
        if not is_archived:
            logger.info(
                "取消案件建档,保留建档编号",
                extra={"case_id": case_id, "filing_number": case.filing_number, "action": "handle_case_filing_change"},
            )
            return None

        # 如果已建档且已有编号,返回现有编号
        if case.filing_number:
            logger.info(
                "案件已有建档编号,返回现有编号",
                extra={"case_id": case_id, "filing_number": case.filing_number, "action": "handle_case_filing_change"},
            )
            return case.filing_number

        # 如果已建档但没有编号,生成新编号
        created_year = case.start_date.year
        filing_number = self.filing_number_service.generate_case_filing_number_internal(
            case_id=case_id,
            case_type=case.case_type, # type: ignore
            created_year=created_year,
        )

        # 保存编号到数据库
        case.filing_number = filing_number
        case.save(update_fields=["filing_number"])

        logger.info(
            "生成并保存案件建档编号",
            extra={"case_id": case_id, "filing_number": filing_number, "action": "handle_case_filing_change"},
        )

        return filing_number
