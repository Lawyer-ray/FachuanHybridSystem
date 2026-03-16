"""和解协议生成服务：包含债务确认、还款计划、加速到期、违约责任、争议解决条款"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

from .lawyer_letter_generator_service import GeneratedDocument

logger = logging.getLogger(__name__)

TEMPLATE_DIR: Path = Path(__file__).resolve().parents[3] / "documents" / "docx_templates" / "2-案件材料" / "3-催收材料"
TEMPLATE_FILE = "和解协议.docx"


class DisputeResolution(str, Enum):
    """争议解决方式枚举"""

    NEGOTIATION = "negotiation"
    ARBITRATION = "arbitration"
    LITIGATION = "litigation"


_RESOLUTION_DISPLAY: dict[DisputeResolution, str] = {
    DisputeResolution.NEGOTIATION: "协商",
    DisputeResolution.ARBITRATION: "仲裁",
    DisputeResolution.LITIGATION: "诉讼",
}


@dataclass(frozen=True)
class InstallmentPlan:
    """分期还款计划"""

    due_date: date
    amount: Decimal


@dataclass(frozen=True)
class SettlementParams:
    """和解协议生成参数"""

    case_id: int
    creditor_name: str
    creditor_address: str
    creditor_id_number: str
    debtor_name: str
    debtor_address: str
    debtor_id_number: str
    total_debt: Decimal
    installments: list[InstallmentPlan]
    acceleration_clause: str
    penalty_rate: Decimal
    dispute_resolution: DisputeResolution
    arbitration_institution: str = ""


class SettlementGeneratorService:
    """和解协议生成服务"""

    def generate(self, params: SettlementParams) -> GeneratedDocument:
        """
        生成和解协议。

        1. 校验模板文件存在
        2. 构建上下文（甲乙方信息、债务总额、还款计划、加速到期、违约金、争议解决）
        3. 调用 DocxRenderer 渲染
        4. 创建 CollectionLog 记录
        5. 返回文件名和字节流
        """
        from apps.sales_dispute.models.collection_record import CollectionLog, CollectionRecord

        template_path = TEMPLATE_DIR / TEMPLATE_FILE

        if not template_path.exists():
            raise ValidationException(
                message=_("模板文件不存在：%(path)s") % {"path": str(template_path)},
                code="TEMPLATE_NOT_FOUND",
            )

        context = self._build_context(params)
        renderer = self._build_docx_renderer()
        content = renderer.render(str(template_path), context)

        filename = self._generate_filename(params)

        # 创建 CollectionLog 记录
        try:
            record = CollectionRecord.objects.get(case_id=params.case_id)
            CollectionLog.objects.create(
                record=record,
                action_type="lawyer_letter",
                action_date=date.today(),
                description=str(_("生成和解协议")),
                document_type="和解协议",
                document_filename=filename,
            )
        except CollectionRecord.DoesNotExist:
            logger.warning("案件 %s 无催收记录，跳过日志创建", params.case_id)

        logger.info(
            "生成和解协议：案件=%s, 文件=%s",
            params.case_id,
            filename,
        )
        return GeneratedDocument(filename=filename, content=content)

    @staticmethod
    def _build_docx_renderer() -> Any:
        module = import_module("apps.documents.services.generation.pipeline")
        renderer_cls = module.DocxRenderer
        return renderer_cls()

    def _build_context(self, params: SettlementParams) -> dict[str, Any]:
        """构建模板上下文，多段落条款文本使用 \\a 分隔符"""
        today_str = date.today().strftime("%Y年%m月%d日")

        installments_list: list[dict[str, str]] = [
            {
                "due_date": plan.due_date.strftime("%Y年%m月%d日"),
                "amount": f"{plan.amount:,.2f}",
            }
            for plan in params.installments
        ]

        # 违约金比例转百分比字符串
        penalty_rate_pct = f"{params.penalty_rate * 100:.2f}%"

        # 争议解决方式中文显示
        resolution_display = _RESOLUTION_DISPLAY[params.dispute_resolution]

        return {
            "creditor_name": params.creditor_name,
            "creditor_address": params.creditor_address,
            "creditor_id_number": params.creditor_id_number,
            "debtor_name": params.debtor_name,
            "debtor_address": params.debtor_address,
            "debtor_id_number": params.debtor_id_number,
            "total_debt": f"{params.total_debt:,.2f}",
            "installments": installments_list,
            "acceleration_clause": params.acceleration_clause.replace("\n", "\a"),
            "penalty_rate": penalty_rate_pct,
            "dispute_resolution": resolution_display,
            "arbitration_institution": params.arbitration_institution,
            "date": today_str,
        }

    def _generate_filename(self, params: SettlementParams) -> str:
        """生成文件名：和解协议-{案件ID}-{日期}.docx"""
        date_str = date.today().strftime("%Y%m%d")
        return f"和解协议-{params.case_id}-{date_str}.docx"
