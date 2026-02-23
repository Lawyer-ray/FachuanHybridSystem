from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedInvoice:
    invoice_code: str = field(default="")
    invoice_number: str = field(default="")
    invoice_date: date | None = field(default=None)
    amount: Decimal | None = field(default=None)
    tax_amount: Decimal | None = field(default=None)
    total_amount: Decimal | None = field(default=None)
    buyer_name: str = field(default="")
    seller_name: str = field(default="")
    project_name: str = field(default="")
    category: str = field(default="other")


class InvoiceParser:
    """通过正则表达式和关键词匹配从 OCR/PDF 文本中提取结构化发票字段"""

    # 发票代码：10-12 位数字，前面有关键词
    _CODE_PATTERN: re.Pattern[str] = re.compile(
        r"(?:发票代码|No\.)[^\d]*(\d{10,12})"
    )
    # 发票号码：8位（旧版）或20位（新版电子发票），前面有关键词
    _NUMBER_PATTERN: re.Pattern[str] = re.compile(
        r"(?:发票号码|No\.)[^\d]*(\d{20}|\d{8})(?!\d)"
    )
    # 项目名称：*类目*具体名称 格式，截止到空格/换行
    _PROJECT_PATTERN: re.Pattern[str] = re.compile(
        r"\*[^*]+\*([^\s\n\r]{2,50})"
    )
    # 日期：YYYY年MM月DD日 或 YYYY-MM-DD
    _DATE_CN_PATTERN: re.Pattern[str] = re.compile(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日"
    )
    _DATE_ISO_PATTERN: re.Pattern[str] = re.compile(
        r"(\d{4})-(\d{2})-(\d{2})"
    )
    # 金额：支持带逗号格式，如 1,234.56
    _AMOUNT_PATTERN: re.Pattern[str] = re.compile(
        r"(?:合计金额|金额)[^\d\-]*?([\d,]+\.\d{2})"
    )
    _TAX_PATTERN: re.Pattern[str] = re.compile(
        r"税额[^\d\-]*?([\d,]+\.\d{2})"
    )
    _TOTAL_PATTERN: re.Pattern[str] = re.compile(
        r"价税合计[^\d\-]*?([\d,]+\.\d{2})"
    )
    # 购买方名称
    _BUYER_PATTERN: re.Pattern[str] = re.compile(
        r"(?:购买方名称|购方名称|购买方|名称)[：:]\s*([^\n\r]{2,50})"
    )
    # 销售方名称
    _SELLER_PATTERN: re.Pattern[str] = re.compile(
        r"(?:销售方名称|销方名称|销售方|名称)[：:]\s*([^\n\r]{2,50})"
    )

    # 类目关键词映射（顺序重要，长关键词优先）
    _CATEGORY_KEYWORDS: list[tuple[str, str]] = [
        ("增值税专用发票", "vat_special"),
        ("增值税电子普通发票", "vat_electronic"),
        ("电子普通发票", "vat_electronic"),
        ("增值税普通发票", "vat_normal"),
        ("机动车销售统一发票", "vehicle_sales"),
        ("铁路电子客票", "train_ticket"),
        ("火车票", "train_ticket"),
        ("出租车发票", "taxi_receipt"),
        ("出租车", "taxi_receipt"),
        ("定额发票", "quota_invoice"),
        ("航空运输电子客票", "air_itinerary"),
        ("飞机行程单", "air_itinerary"),
        ("过路费", "toll_receipt"),
        ("通行费", "toll_receipt"),
    ]

    def parse(self, raw_text: str) -> ParsedInvoice:
        """从原始文本提取结构化字段"""
        invoice_code = self._extract_invoice_code(raw_text)
        invoice_number = self._extract_invoice_number(raw_text)
        invoice_date = self._extract_date(raw_text)
        amount = self._extract_amount(raw_text)
        tax_amount = self._extract_tax_amount(raw_text)
        total_amount = self._extract_total_amount(raw_text)
        buyer_name = self._extract_buyer_name(raw_text)
        seller_name = self._extract_seller_name(raw_text)
        project_name = self._extract_project_name(raw_text)
        category = self.detect_category(raw_text)

        logger.info(
            "解析发票完成: code=%s, number=%s, category=%s",
            invoice_code,
            invoice_number,
            category,
        )

        return ParsedInvoice(
            invoice_code=invoice_code,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            amount=amount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            buyer_name=buyer_name,
            seller_name=seller_name,
            project_name=project_name,
            category=category,
        )

    def detect_category(self, raw_text: str) -> str:
        """根据关键词判定发票类目，无法判定时返回 'other'"""
        for keyword, category in self._CATEGORY_KEYWORDS:
            if keyword in raw_text:
                return category
        return "other"

    def format_to_text(self, parsed: ParsedInvoice) -> str:
        """将结构化数据格式化为标准文本（用于 round-trip 验证）"""
        lines: list[str] = []
        lines.append(f"发票代码:{parsed.invoice_code}")
        lines.append(f"发票号码:{parsed.invoice_number}")
        if parsed.invoice_date is not None:
            lines.append(
                f"开票日期:{parsed.invoice_date.year}年"
                f"{parsed.invoice_date.month:02d}月"
                f"{parsed.invoice_date.day:02d}日"
            )
        else:
            lines.append("开票日期:")
        lines.append(
            f"金额:{parsed.amount:.2f}" if parsed.amount is not None else "金额:"
        )
        lines.append(
            f"税额:{parsed.tax_amount:.2f}"
            if parsed.tax_amount is not None
            else "税额:"
        )
        lines.append(
            f"价税合计:{parsed.total_amount:.2f}"
            if parsed.total_amount is not None
            else "价税合计:"
        )
        lines.append(f"购买方名称:{parsed.buyer_name}")
        lines.append(f"销售方名称:{parsed.seller_name}")
        lines.append(f"发票类目:{parsed.category}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 私有提取方法
    # ------------------------------------------------------------------ #

    def _extract_invoice_code(self, text: str) -> str:
        m = self._CODE_PATTERN.search(text)
        return m.group(1) if m else ""

    def _extract_invoice_number(self, text: str) -> str:
        m = self._NUMBER_PATTERN.search(text)
        return m.group(1) if m else ""

    def _extract_date(self, text: str) -> date | None:
        m = self._DATE_CN_PATTERN.search(text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                logger.warning("无效日期（中文格式）: %s", m.group(0))
        m = self._DATE_ISO_PATTERN.search(text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                logger.warning("无效日期（ISO格式）: %s", m.group(0))
        return None

    def _parse_decimal(self, value: str) -> Decimal | None:
        try:
            return Decimal(value.replace(",", ""))
        except InvalidOperation:
            logger.warning("无法解析金额: %s", value)
            return None

    def _extract_amount(self, text: str) -> Decimal | None:
        m = self._AMOUNT_PATTERN.search(text)
        return self._parse_decimal(m.group(1)) if m else None

    def _extract_tax_amount(self, text: str) -> Decimal | None:
        m = self._TAX_PATTERN.search(text)
        return self._parse_decimal(m.group(1)) if m else None

    def _extract_total_amount(self, text: str) -> Decimal | None:
        m = self._TOTAL_PATTERN.search(text)
        return self._parse_decimal(m.group(1)) if m else None

    def _extract_buyer_name(self, text: str) -> str:
        m = self._BUYER_PATTERN.search(text)
        return m.group(1).strip() if m else ""

    def _extract_seller_name(self, text: str) -> str:
        # 先找销售方，避免与购买方混淆
        m = re.search(
            r"(?:销售方名称|销方名称|销售方)[：:]\s*([^\n\r]{2,50})", text
        )
        return m.group(1).strip() if m else ""

    def _extract_project_name(self, text: str) -> str:
        m = self._PROJECT_PATTERN.search(text)
        return m.group(1).strip() if m else ""
