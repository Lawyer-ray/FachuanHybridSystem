"""对账函生成服务：列明交易明细和欠款金额"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

from .lawyer_letter_generator_service import GeneratedDocument

logger = logging.getLogger(__name__)

TEMPLATE_DIR: Path = Path(__file__).resolve().parents[3] / "documents" / "docx_templates" / "2-案件材料" / "3-催收材料"
TEMPLATE_FILE = "对账函.docx"


@dataclass(frozen=True)
class TransactionItem:
    """交易明细项"""

    transaction_date: date
    description: str
    amount: Decimal


@dataclass(frozen=True)
class ReconciliationParams:
    """对账函生成参数"""

    case_id: int
    creditor_name: str
    debtor_name: str
    transactions: list[TransactionItem]
    paid_amount: Decimal
    outstanding_amount: Decimal


class ReconciliationGeneratorService:
    """对账函生成服务"""

    def generate(self, params: ReconciliationParams) -> GeneratedDocument:
        """
        生成对账函。

        1. 校验模板文件存在
        2. 构建上下文（交易明细列表、已付总额、欠款总额）
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
                action_type="written_collection",
                action_date=date.today(),
                description=str(_("生成对账函")),
                document_type="对账函",
                document_filename=filename,
            )
        except CollectionRecord.DoesNotExist:
            logger.warning("案件 %s 无催收记录，跳过日志创建", params.case_id)

        logger.info(
            "生成对账函：案件=%s, 文件=%s",
            params.case_id,
            filename,
        )
        return GeneratedDocument(filename=filename, content=content)

    @staticmethod
    def _build_docx_renderer() -> Any:
        module = import_module("apps.documents.services.generation.pipeline")
        renderer_cls = module.DocxRenderer
        return renderer_cls()

    def _build_context(self, params: ReconciliationParams) -> dict[str, Any]:
        """构建模板上下文"""
        today_str = date.today().strftime("%Y年%m月%d日")

        transactions_list: list[dict[str, str]] = [
            {
                "date": item.transaction_date.strftime("%Y年%m月%d日"),
                "description": item.description,
                "amount": f"{item.amount:,.2f}",
            }
            for item in params.transactions
        ]

        return {
            "creditor_name": params.creditor_name,
            "debtor_name": params.debtor_name,
            "transactions": transactions_list,
            "paid_amount": f"{params.paid_amount:,.2f}",
            "outstanding_amount": f"{params.outstanding_amount:,.2f}",
            "date": today_str,
        }

    def _generate_filename(self, params: ReconciliationParams) -> str:
        """生成文件名：对账函-{案件ID}-{日期}.docx"""
        date_str = date.today().strftime("%Y%m%d")
        return f"对账函-{params.case_id}-{date_str}.docx"
