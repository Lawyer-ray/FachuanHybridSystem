"""律师函生成服务：支持温和版、强硬版、最后通牒三版本递进"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)

TEMPLATE_DIR: Path = Path(__file__).resolve().parents[3] / "documents" / "docx_templates" / "2-案件材料" / "3-催收材料"


class LetterTone(str, Enum):
    """律师函语气枚举"""

    MILD = "mild"
    FIRM = "firm"
    ULTIMATUM = "ultimatum"


TONE_TEMPLATE_MAP: dict[LetterTone, str] = {
    LetterTone.MILD: "律师函-温和版.docx",
    LetterTone.FIRM: "律师函-强硬版.docx",
    LetterTone.ULTIMATUM: "律师函-最后通牒.docx",
}

_TONE_DISPLAY: dict[LetterTone, str] = {
    LetterTone.MILD: "温和版",
    LetterTone.FIRM: "强硬版",
    LetterTone.ULTIMATUM: "最后通牒",
}


@dataclass(frozen=True)
class LawyerLetterParams:
    """律师函生成参数"""

    case_id: int
    tone: LetterTone
    creditor_name: str
    debtor_name: str
    principal: Decimal
    interest_amount: Decimal
    contract_no: str = ""
    deadline_days: int = 7


@dataclass(frozen=True)
class GeneratedDocument:
    """生成文档结果"""

    filename: str
    content: bytes


class LawyerLetterGeneratorService:
    """律师函生成服务"""

    def generate(self, params: LawyerLetterParams) -> GeneratedDocument:
        """
        生成律师函。

        1. 根据 tone 选择模板文件
        2. 校验模板文件存在
        3. 构建上下文
        4. 调用 DocxRenderer 渲染
        5. 创建 CollectionLog 记录
        6. 返回文件名和字节流
        """
        from apps.documents.services.generation.pipeline import DocxRenderer
        from apps.sales_dispute.models.collection_record import CollectionLog, CollectionRecord

        template_file = TONE_TEMPLATE_MAP[params.tone]
        template_path = TEMPLATE_DIR / template_file

        if not template_path.exists():
            raise ValidationException(
                message=_("模板文件不存在：%(path)s") % {"path": str(template_path)},
                code="TEMPLATE_NOT_FOUND",
            )

        context = self._build_context(params)
        renderer = DocxRenderer()
        content = renderer.render(str(template_path), context)

        filename = self._generate_filename(params)

        # 创建 CollectionLog 记录
        tone_display = _TONE_DISPLAY[params.tone]
        try:
            record = CollectionRecord.objects.get(case_id=params.case_id)
            CollectionLog.objects.create(
                record=record,
                action_type="lawyer_letter",
                action_date=date.today(),
                description=str(_("生成律师函（%(tone)s）") % {"tone": tone_display}),
                document_type=f"律师函-{tone_display}",
                document_filename=filename,
            )
        except CollectionRecord.DoesNotExist:
            logger.warning("案件 %s 无催收记录，跳过日志创建", params.case_id)

        logger.info(
            "生成律师函：案件=%s, 语气=%s, 文件=%s",
            params.case_id,
            params.tone.value,
            filename,
        )
        return GeneratedDocument(filename=filename, content=content)

    def _build_context(self, params: LawyerLetterParams) -> dict[str, Any]:
        """构建模板上下文，多段落文本使用 \\a 分隔符"""
        total_amount = params.principal + params.interest_amount
        tone_display = _TONE_DISPLAY[params.tone]
        today_str = date.today().strftime("%Y年%m月%d日")

        return {
            "creditor_name": params.creditor_name,
            "debtor_name": params.debtor_name,
            "principal": f"{params.principal:,.2f}",
            "interest_amount": f"{params.interest_amount:,.2f}",
            "total_amount": f"{total_amount:,.2f}",
            "contract_no": params.contract_no,
            "deadline_days": params.deadline_days,
            "tone_display": tone_display,
            "date": today_str,
        }

    def _generate_filename(self, params: LawyerLetterParams) -> str:
        """生成文件名：律师函-{语气}-{案件ID}-{日期}.docx"""
        tone_display = _TONE_DISPLAY[params.tone]
        date_str = date.today().strftime("%Y%m%d")
        return f"律师函-{tone_display}-{params.case_id}-{date_str}.docx"
