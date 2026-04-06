"""执行阶段文书生成服务：支持强制执行申请书、财产调查申请书、限制高消费申请书、追加被执行人申请书"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException
from apps.documents.storage import get_docx_templates_root

from .lawyer_letter_generator_service import GeneratedDocument

logger = logging.getLogger(__name__)

TEMPLATE_DIR: Path = Path(str(get_docx_templates_root() / "2-案件材料" / "3-催收材料"))


class ExecutionDocType(str, Enum):
    """执行文书类型枚举"""

    ENFORCEMENT = "enforcement_application"
    PROPERTY_INVESTIGATION = "property_investigation"
    SPENDING_RESTRICTION = "spending_restriction"
    ADD_EXECUTEE = "add_executee"


DOC_TYPE_TEMPLATE_MAP: dict[ExecutionDocType, str] = {
    ExecutionDocType.ENFORCEMENT: "强制执行申请书.docx",
    ExecutionDocType.PROPERTY_INVESTIGATION: "财产调查申请书.docx",
    ExecutionDocType.SPENDING_RESTRICTION: "限制高消费申请书.docx",
    ExecutionDocType.ADD_EXECUTEE: "追加被执行人申请书.docx",
}

_DOC_TYPE_DISPLAY: dict[ExecutionDocType, str] = {
    ExecutionDocType.ENFORCEMENT: "强制执行申请书",
    ExecutionDocType.PROPERTY_INVESTIGATION: "财产调查申请书",
    ExecutionDocType.SPENDING_RESTRICTION: "限制高消费申请书",
    ExecutionDocType.ADD_EXECUTEE: "追加被执行人申请书",
}

_PROPERTY_TYPE_DISPLAY: dict[str, str] = {
    "bank_deposit": "银行存款",
    "real_estate": "不动产",
    "vehicle": "车辆",
    "equity": "股权",
    "other": "其他",
}

_ADD_REASON_DISPLAY: dict[str, str] = {
    "unpaid_capital": "未缴出资",
    "withdrawn_capital": "抽逃出资",
    "sole_shareholder": "一人公司财产混同",
    "other": "其他",
}


# ── 各文书参数 dataclass ──


@dataclass(frozen=True)
class EnforcementParams:
    """强制执行申请书参数"""

    case_id: int
    applicant_name: str
    applicant_address: str
    applicant_id_number: str
    respondent_name: str
    respondent_address: str
    respondent_id_number: str
    judgment_number: str
    execution_amount: Decimal
    execution_requests: str


@dataclass(frozen=True)
class PropertyInvestigationParams:
    """财产调查申请书参数"""

    case_id: int
    applicant_name: str
    applicant_address: str
    respondent_name: str
    respondent_address: str
    execution_case_number: str
    property_types: list[str]


@dataclass(frozen=True)
class SpendingRestrictionParams:
    """限制高消费申请书参数"""

    case_id: int
    applicant_name: str
    applicant_address: str
    respondent_name: str
    respondent_address: str
    legal_representative: str
    execution_case_number: str
    outstanding_amount: Decimal


@dataclass(frozen=True)
class AddExecuteeParams:
    """追加被执行人申请书参数"""

    case_id: int
    applicant_name: str
    applicant_address: str
    original_respondent_name: str
    original_respondent_address: str
    added_respondent_name: str
    added_respondent_address: str
    added_respondent_id_number: str
    add_reason: str
    legal_basis: str


class ExecutionDocGeneratorService:
    """执行阶段文书生成服务"""

    def generate_enforcement(self, params: EnforcementParams) -> GeneratedDocument:
        """生成强制执行申请书"""
        today_str = date.today().strftime("%Y年%m月%d日")
        context: dict[str, Any] = {
            "applicant_name": params.applicant_name,
            "applicant_address": params.applicant_address,
            "applicant_id_number": params.applicant_id_number,
            "respondent_name": params.respondent_name,
            "respondent_address": params.respondent_address,
            "respondent_id_number": params.respondent_id_number,
            "judgment_number": params.judgment_number,
            "execution_amount": f"{params.execution_amount:,.2f}",
            "execution_requests": params.execution_requests.replace("\n", "\a"),
            "date": today_str,
        }

        doc_type = ExecutionDocType.ENFORCEMENT
        content = self._render(doc_type, context)
        filename = self._generate_filename(doc_type, params.case_id)
        self._log_generation(params.case_id, _DOC_TYPE_DISPLAY[doc_type], filename)

        logger.info(
            "生成强制执行申请书：案件=%s, 文件=%s",
            params.case_id,
            filename,
        )
        return GeneratedDocument(filename=filename, content=content)

    def generate_property_investigation(self, params: PropertyInvestigationParams) -> GeneratedDocument:
        """生成财产调查申请书"""
        today_str = date.today().strftime("%Y年%m月%d日")

        property_types_text = "、".join(_PROPERTY_TYPE_DISPLAY.get(pt, pt) for pt in params.property_types)

        context: dict[str, Any] = {
            "applicant_name": params.applicant_name,
            "applicant_address": params.applicant_address,
            "respondent_name": params.respondent_name,
            "respondent_address": params.respondent_address,
            "execution_case_number": params.execution_case_number,
            "property_types_text": property_types_text,
            "date": today_str,
        }

        doc_type = ExecutionDocType.PROPERTY_INVESTIGATION
        content = self._render(doc_type, context)
        filename = self._generate_filename(doc_type, params.case_id)
        self._log_generation(params.case_id, _DOC_TYPE_DISPLAY[doc_type], filename)

        logger.info(
            "生成财产调查申请书：案件=%s, 文件=%s",
            params.case_id,
            filename,
        )
        return GeneratedDocument(filename=filename, content=content)

    def generate_spending_restriction(self, params: SpendingRestrictionParams) -> GeneratedDocument:
        """生成限制高消费申请书"""
        today_str = date.today().strftime("%Y年%m月%d日")
        context: dict[str, Any] = {
            "applicant_name": params.applicant_name,
            "applicant_address": params.applicant_address,
            "respondent_name": params.respondent_name,
            "respondent_address": params.respondent_address,
            "legal_representative": params.legal_representative,
            "execution_case_number": params.execution_case_number,
            "outstanding_amount": f"{params.outstanding_amount:,.2f}",
            "date": today_str,
        }

        doc_type = ExecutionDocType.SPENDING_RESTRICTION
        content = self._render(doc_type, context)
        filename = self._generate_filename(doc_type, params.case_id)
        self._log_generation(params.case_id, _DOC_TYPE_DISPLAY[doc_type], filename)

        logger.info(
            "生成限制高消费申请书：案件=%s, 文件=%s",
            params.case_id,
            filename,
        )
        return GeneratedDocument(filename=filename, content=content)

    def generate_add_executee(self, params: AddExecuteeParams) -> GeneratedDocument:
        """生成追加被执行人申请书"""
        today_str = date.today().strftime("%Y年%m月%d日")

        add_reason_text = _ADD_REASON_DISPLAY.get(params.add_reason, params.add_reason)

        context: dict[str, Any] = {
            "applicant_name": params.applicant_name,
            "applicant_address": params.applicant_address,
            "original_respondent_name": params.original_respondent_name,
            "original_respondent_address": params.original_respondent_address,
            "added_respondent_name": params.added_respondent_name,
            "added_respondent_address": params.added_respondent_address,
            "added_respondent_id_number": params.added_respondent_id_number,
            "add_reason_text": add_reason_text,
            "legal_basis": params.legal_basis.replace("\n", "\a"),
            "date": today_str,
        }

        doc_type = ExecutionDocType.ADD_EXECUTEE
        content = self._render(doc_type, context)
        filename = self._generate_filename(doc_type, params.case_id)
        self._log_generation(params.case_id, _DOC_TYPE_DISPLAY[doc_type], filename)

        logger.info(
            "生成追加被执行人申请书：案件=%s, 文件=%s",
            params.case_id,
            filename,
        )
        return GeneratedDocument(filename=filename, content=content)

    def _render(self, doc_type: ExecutionDocType, context: dict[str, object]) -> bytes:
        """
        通用渲染方法：
        1. 根据 doc_type 查找模板文件
        2. 校验模板存在
        3. 调用 DocxRenderer 渲染
        """
        template_file = DOC_TYPE_TEMPLATE_MAP[doc_type]
        template_path = TEMPLATE_DIR / template_file

        if not template_path.exists():
            raise ValidationException(
                message=_("模板文件不存在：%(path)s") % {"path": str(template_path)},
                code="TEMPLATE_NOT_FOUND",
            )

        renderer = self._build_docx_renderer()
        rendered_content = renderer.render(str(template_path), context)
        return cast(bytes, rendered_content)

    @staticmethod
    def _build_docx_renderer() -> Any:
        module = import_module("apps.documents.services.generation.pipeline")
        renderer_cls = module.DocxRenderer
        return renderer_cls()

    def _log_generation(self, case_id: int, doc_type: str, filename: str) -> None:
        """创建 CollectionLog 记录"""
        from apps.sales_dispute.models.collection_record import CollectionLog, CollectionRecord

        try:
            record = CollectionRecord.objects.get(case_id=case_id)
            CollectionLog.objects.create(
                record=record,
                action_type="litigation",
                action_date=date.today(),
                description=str(_("生成%(doc_type)s") % {"doc_type": doc_type}),
                document_type=doc_type,
                document_filename=filename,
            )
        except CollectionRecord.DoesNotExist:
            logger.warning("案件 %s 无催收记录，跳过日志创建", case_id)

    def _generate_filename(self, doc_type: ExecutionDocType, case_id: int) -> str:
        """生成文件名：{文书类型}-{案件ID}-{日期}.docx"""
        display = _DOC_TYPE_DISPLAY[doc_type]
        date_str = date.today().strftime("%Y%m%d")
        return f"{display}-{case_id}-{date_str}.docx"
