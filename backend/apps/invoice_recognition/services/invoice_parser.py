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
    remark: str = field(default="")
    project_code: str = field(default="")


class InvoiceParser:
    """通过正则表达式和关键词匹配从 OCR/PDF 文本中提取结构化发票字段

    `remark` / `project_code` 用于把发票挂回律所案件：数电票的备注栏里常有
    `2025GZM0001-某某与某某公司合同纠纷;` 这样的行，`project_code`（GZ 项目号）  # privacy-allow 虚构样例，非真实项目号
    是律所自己的案件检索键，比购买方名字更可靠。

    本解析器**不碰税号/统一社会信用代码/身份证号**：数电票文本里这些字段与当事人
    同行出现，但属于敏感个人信息，不做结构化提取，脱敏交给上层。
    """

    _CODE_PATTERN: re.Pattern[str] = re.compile(r"(?:发票代码|No\.)[^\d]*(\d{10,12})")
    _NUMBER_PATTERN: re.Pattern[str] = re.compile(r"(?:发\s*票\s*号\s*码|No\.)[^\d]*(\d{20}|\d{8})(?!\d)")
    _NUMBER_FALLBACK_20: re.Pattern[str] = re.compile(r"(?<!\d)(\d{20})(?!\d)")
    _PROJECT_PATTERN: re.Pattern[str] = re.compile(r"\*[^*]+\*([^\s\n\r]{2,50})")
    _DATE_CN_PATTERN: re.Pattern[str] = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
    _DATE_ISO_PATTERN: re.Pattern[str] = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
    _AMOUNT_PATTERN: re.Pattern[str] = re.compile(r"合\s*计\s*[¥￥]([\d,]+\.\d{2})\s*[¥￥]([\d,]+\.\d{2})")
    _TOTAL_PATTERN: re.Pattern[str] = re.compile(r"[（(]\s*小写\s*[）)]\s*[¥￥]\s*([\d,]+\.\d{2})")

    #: 备注栏在 pdfplumber 文本里的版式：表格把「备」「注」两个竖排字切成独立行
    #: （也出现过挤在同一行 `注释`），内容行夹在中间，脚注「复核人/开票人」收尾。
    _REMARK_LABELS: tuple[str, ...] = ("备", "注", "注释")
    _REMARK_END_PATTERN: re.Pattern[str] = re.compile(r"复\s*核\s*人|开\s*票\s*人")
    #: 备注栏里混进来的固定栏位行（地址/开户行），不是律师写的备注内容。
    _REMARK_NOISE_PREFIXES: tuple[str, ...] = (
        "销售方地址",
        "销方地址",
        "销方开户银行",
        "销售方开户银行",
        "购买方地址",
        "购方地址",
        "购方开户银行",
        "购买方开户银行",
    )

    #: 律所项目号：优先严格形如 2025GZM0001，再放宽字母位数与序号长度。  # privacy-allow 虚构样例，非真实项目号
    #: 边界必须显式写成「前后不是字母数字」而不能用 `\b`：项目号在备注里常紧贴汉字
    #: （`备注：2025GZM0001`）或下划线，而 `\b` 把汉字/下划线都当单词字符，会漏抽。  # privacy-allow 虚构样例，非真实项目号
    _PROJECT_CODE_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"(?<![0-9A-Za-z])(\d{4}GZ[A-Z]\d{4})(?![0-9A-Za-z])"),
        re.compile(r"(?<![0-9A-Za-z])(\d{4}GZ[A-Z]{1,2}\d{3,6})(?![0-9A-Za-z])"),
    )

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
        remark = self._extract_remark(raw_text)
        project_code = self._extract_project_code(raw_text, remark=remark)

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
            remark=remark,
            project_code=project_code,
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
                f"开票日期:{parsed.invoice_date.year}年{parsed.invoice_date.month:02d}月{parsed.invoice_date.day:02d}日"
            )
        else:
            lines.append("开票日期:")
        lines.append(f"金额:{parsed.amount:.2f}" if parsed.amount is not None else "金额:")
        lines.append(f"税额:{parsed.tax_amount:.2f}" if parsed.tax_amount is not None else "税额:")
        lines.append(f"价税合计:{parsed.total_amount:.2f}" if parsed.total_amount is not None else "价税合计:")
        lines.append(f"购买方名称:{parsed.buyer_name}")
        lines.append(f"销售方名称:{parsed.seller_name}")
        lines.append(f"发票类目:{parsed.category}")
        return "\n".join(lines)

    def _extract_invoice_code(self, text: str) -> str:
        m = self._CODE_PATTERN.search(text)
        return m.group(1) if m else ""

    def _extract_invoice_number(self, text: str) -> str:
        m = self._NUMBER_PATTERN.search(text)
        if m:
            return m.group(1)
        # 数电发票：发票号码在红色印章图片中，pdfplumber 提取的文本里
        # 号码不紧跟在「发票号码」标签后，而是散落在文本中（如「制 264420…」）
        if re.search(r"电⼦?发票", text):
            m = self._NUMBER_FALLBACK_20.search(text)
            if m:
                return m.group(1)
        return ""

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
        m = self._AMOUNT_PATTERN.search(text)
        return self._parse_decimal(m.group(2)) if m else None

    def _extract_total_amount(self, text: str) -> Decimal | None:
        m = self._TOTAL_PATTERN.search(text)
        return self._parse_decimal(m.group(1)) if m else None

    def _extract_buyer_name(self, text: str) -> str:
        for pattern in [
            r"购买方名称[：:]\s*([^\n\r]{2,50})",
            r"购方名称[：:]\s*([^\n\r]{2,50})",
            r"(?:购\s*名称|买\s*名称)[：:]\s*([^\n\r销]{2,40})",
            r"名称[：:]\s*([^\n\r]{2,50})",
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(1).strip()
        return ""

    def _extract_seller_name(self, text: str) -> str:
        for pattern in [
            r"销售方名称[：:]\s*([^\n\r]{2,50})",
            r"销方名称[：:]\s*([^\n\r]{2,50})",
            r"销\s*名称[：:]\s*([^\n\r]{2,50})",
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(1).strip()
        return ""

    def _extract_project_name(self, text: str) -> str:
        m = self._PROJECT_PATTERN.search(text)
        return m.group(1).strip() if m else ""

    def _extract_remark(self, text: str) -> str:
        """抽取备注栏原文；抽不到返回空串。

        按内容定位而不是行号：表格切行会让「备」「注」各占一行，只认行号会在别的
        发票版式上静默错位。这里从标签行开始向下收，遇到「复核人/开票人」停。
        """
        lines = [line.strip() for line in text.splitlines()]

        start: int | None = None
        for index, line in enumerate(lines):
            if not any(label in line for label in self._REMARK_LABELS):
                continue
            # 单字「备」后常紧跟表格里的其它列文字（如「注 销 名称：…」），只看紧邻行
            neighbour_window = lines[index : index + 2]
            if any("注" in item for item in neighbour_window) or "注" in line:
                start = index + 1
                break

        if start is None:
            return ""

        kept: list[str] = []
        for line in lines[start:]:
            if self._REMARK_END_PATTERN.search(line):
                break
            kept.append(self._strip_remark_noise(line))

        return "\n".join(item for item in kept if item).strip()

    def _strip_remark_noise(self, line: str) -> str:
        """去掉备注区里的空行、纯「备」/「注」标签行和地址开户行等固定栏位行。"""
        compact = line.strip()
        if not compact or compact in self._REMARK_LABELS:
            return ""
        for prefix in self._REMARK_NOISE_PREFIXES:
            if compact.startswith(prefix):
                return ""
        return compact

    def _extract_project_code(self, text: str, remark: str = "") -> str:
        """抽取律所项目号；优先在备注里找，没有再全文找。"""
        for source in (remark, text):
            if not source:
                continue
            for pattern in self._PROJECT_CODE_PATTERNS:
                m = pattern.search(source)
                if m:
                    return m.group(1)
        return ""
