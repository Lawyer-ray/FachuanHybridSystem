"""对账单 LLM 解析 + 出库单交叉比对"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("apps.evidence_sorting")

# 比对状态
STATUS_MATCHED = "matched"
STATUS_UNMATCHED = "unmatched"  # 出库单不在对账单中
STATUS_MISSING = "missing"  # 对账单明细缺少出库单

# 文件夹状态标注
FOLDER_CONFIRMED = "已确认"
FOLDER_UNSIGNED = "对账单未签名"
FOLDER_MISSING_DELIVERY = "缺少出库单"
FOLDER_DELIVERY_NOT_ENOUGH = "出库单数量不够"
FOLDER_DELIVERY_MISMATCH = "出库单与对账单不匹配"
FOLDER_NEED_SUPPLEMENT = "需补充对账单"

# LLM Prompt
STATEMENT_PARSE_PROMPT = """你是一个专业的财务文档分析助手。请从以下对账单的 OCR 文本中提取结构化信息。

OCR 文本:
{ocr_text}

请按以下 JSON 格式返回:
{{
    "month": "对账单所属月份，格式 YYYY-MM，如 2022-08。如果跨月则用 YYYY-MM~YYYY-MM",
    "total_amount": 总金额数字（不带单位），如 187480,
    "signed": true或false，是否有签名/盖章,
    "line_items": [
        {{
            "date": "YYYYMMDD格式的日期",
            "amount": 金额数字,
            "description": "简要描述"
        }}
    ]
}}

注意:
1. line_items 是对账单中列出的每笔出库/发货明细
2. 日期必须转为 YYYYMMDD 格式（8位纯数字）
3. 金额为数字，不带元/¥等符号
4. 如果无法识别某些字段，设为 null
5. 只返回 JSON，不要其他内容
"""


@dataclass
class LineItem:
    """对账单明细行"""

    date: str | None = None
    amount: float | None = None
    description: str = ""


@dataclass
class StatementInfo:
    """对账单解析结果"""

    month: str = ""
    total_amount: float | None = None
    signed: bool = False
    line_items: list[LineItem] = field(default_factory=list)
    filename: str = ""
    ocr_text: str = ""
    image_data: str = ""


@dataclass
class DeliveryNote:
    """出库单信息"""

    filename: str = ""
    date: str | None = None
    amount: str | None = None
    ocr_text: str = ""
    image_data: str = ""
    match_status: str = STATUS_UNMATCHED
    remark: str = ""


@dataclass
class MonthGroup:
    """按月归档的结果"""

    month: str  # YYYY年MM月
    folder_name: str  # 完整文件夹名（含状态标注）
    statement: StatementInfo | None = None
    deliveries: list[DeliveryNote] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class ReconcileResult:
    """比对结果"""

    month_groups: list[MonthGroup] = field(default_factory=list)
    unsigned_statements: list[StatementInfo] = field(default_factory=list)
    receipts: list[dict[str, Any]] = field(default_factory=list)
    others: list[dict[str, Any]] = field(default_factory=list)
    unmatched_deliveries: list[DeliveryNote] = field(default_factory=list)


class ReconcilerService:
    """对账单解析 + 交叉比对"""

    def parse_statement(
        self,
        ocr_text: str,
        backend: str | None = None,
        model: str | None = None,
    ) -> StatementInfo:
        """用 LLM 解析对账单 OCR 文本"""
        from apps.core.llm import get_llm_service

        llm = get_llm_service()
        prompt = STATEMENT_PARSE_PROMPT.format(ocr_text=ocr_text)

        try:
            resp = llm.complete(
                prompt=prompt,
                backend=backend,
                model=model,
                temperature=0.1,
                fallback=True,
            )
            return self._parse_llm_response(resp.content or "")
        except Exception as e:
            logger.warning("LLM 解析对账单失败: %s", e)
            return StatementInfo()

    def _parse_llm_response(self, text: str) -> StatementInfo:
        """解析 LLM 返回的 JSON"""
        # 提取 JSON 块
        json_text = text
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            json_text = m.group(1)
        else:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                json_text = m.group(0)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            logger.warning("JSON 解析失败: %s", text[:200])
            return StatementInfo()

        items: list[LineItem] = []
        for item in data.get("line_items") or []:
            items.append(LineItem(
                date=self._normalize_date(item.get("date")),
                amount=self._to_float(item.get("amount")),
                description=item.get("description", ""),
            ))

        return StatementInfo(
            month=data.get("month", ""),
            total_amount=self._to_float(data.get("total_amount")),
            signed=bool(data.get("signed", False)),
            line_items=items,
        )

    def reconcile(
        self,
        statements: list[dict[str, Any]],
        deliveries: list[dict[str, Any]],
        receipts: list[dict[str, Any]],
        others: list[dict[str, Any]],
        backend: str | None = None,
        model: str | None = None,
    ) -> ReconcileResult:
        """
        交叉比对

        Args:
            statements: 对账单列表 [{filename, ocr_text, date, amount, signed, image_data}]
            deliveries: 出库单列表 [{filename, ocr_text, date, amount, image_data}]
            receipts: 收款凭证列表
            others: 其他文件列表
        """
        result = ReconcileResult(
            receipts=receipts,
            others=others,
        )

        # 1. 用 LLM 解析每张对账单
        parsed_statements: list[StatementInfo] = []
        for st in statements:
            info = self.parse_statement(
                st.get("ocr_text", ""),
                backend=backend,
                model=model,
            )
            info.filename = st.get("filename", "")
            info.ocr_text = st.get("ocr_text", "")
            info.image_data = st.get("image_data", "")
            # 如果 LLM 没检测到签名状态，用分类阶段的结果
            if not info.signed and st.get("signed"):
                info.signed = True
            parsed_statements.append(info)

        # 2. 构建出库单列表
        delivery_notes: list[DeliveryNote] = []
        for d in deliveries:
            delivery_notes.append(DeliveryNote(
                filename=d.get("filename", ""),
                date=d.get("date"),
                amount=d.get("amount"),
                ocr_text=d.get("ocr_text", ""),
                image_data=d.get("image_data", ""),
            ))

        # 3. 按月份分组对账单
        month_map: dict[str, StatementInfo] = {}
        for st in parsed_statements:
            month_key = self._extract_month_key(st)
            if month_key:
                # 已签名的优先
                if month_key not in month_map or (st.signed and not month_map[month_key].signed):
                    month_map[month_key] = st
                # 未签名的单独收集
                if not st.signed:
                    result.unsigned_statements.append(st)
            else:
                # 无法确定月份的对账单
                if not st.signed:
                    result.unsigned_statements.append(st)

        # 4. 按月份分组出库单并比对
        used_deliveries: set[int] = set()

        for month_key, statement in sorted(month_map.items()):
            group = MonthGroup(
                month=month_key,
                folder_name="",
                statement=statement,
            )

            # 找到属于这个月的出库单
            matched_count = 0
            unmatched_in_statement: list[LineItem] = []

            for li in statement.line_items:
                found = False
                for i, dn in enumerate(delivery_notes):
                    if i in used_deliveries:
                        continue
                    if self._match_delivery(li, dn):
                        dn.match_status = STATUS_MATCHED
                        group.deliveries.append(dn)
                        used_deliveries.add(i)
                        matched_count += 1
                        found = True
                        break
                if not found:
                    unmatched_in_statement.append(li)

            # 也把日期在这个月范围内但没匹配到明细的出库单加进来
            month_prefix = month_key.replace("年", "").replace("月", "")
            # 转为 YYYYMM 格式
            month_yyyymm = self._month_key_to_yyyymm(month_key)
            if month_yyyymm:
                for i, dn in enumerate(delivery_notes):
                    if i in used_deliveries:
                        continue
                    if dn.date and dn.date[:6] == month_yyyymm:
                        dn.match_status = STATUS_UNMATCHED
                        dn.remark = "这张单未出现在对账单中"
                        group.deliveries.append(dn)
                        used_deliveries.add(i)

            # 5. 生成文件夹名和问题标注
            issues: list[str] = []
            if not statement.signed:
                issues.append(FOLDER_UNSIGNED)
            if unmatched_in_statement:
                if len(group.deliveries) == 0:
                    issues.append(FOLDER_MISSING_DELIVERY)
                else:
                    issues.append(FOLDER_DELIVERY_NOT_ENOUGH)
            if any(d.match_status == STATUS_UNMATCHED for d in group.deliveries):
                if FOLDER_DELIVERY_NOT_ENOUGH not in issues and FOLDER_MISSING_DELIVERY not in issues:
                    issues.append(FOLDER_DELIVERY_MISMATCH)

            group.issues = issues
            group.folder_name = self._build_folder_name(month_key, statement, group, issues)
            result.month_groups.append(group)

        # 6. 未匹配的出库单
        for i, dn in enumerate(delivery_notes):
            if i not in used_deliveries:
                result.unmatched_deliveries.append(dn)

        logger.info(
            "比对完成: %d 个月份组, %d 张未匹配出库单",
            len(result.month_groups), len(result.unmatched_deliveries),
        )
        return result

    def _match_delivery(self, line_item: LineItem, delivery: DeliveryNote) -> bool:
        """比对一条对账单明细和一张出库单"""
        # 日期匹配
        if line_item.date and delivery.date:
            if line_item.date != delivery.date:
                return False
        elif not line_item.date and not delivery.date:
            return False

        # 金额匹配（容差 1%）
        if line_item.amount is not None and delivery.amount is not None:
            try:
                d_amount = float(delivery.amount)
                tolerance = max(abs(line_item.amount) * 0.01, 1.0)
                if abs(line_item.amount - d_amount) <= tolerance:
                    return True
            except (ValueError, TypeError):
                pass

        # 只有日期匹配也算（金额可能 OCR 识别不准）
        if line_item.date and delivery.date and line_item.date == delivery.date:
            return True

        return False

    def _extract_month_key(self, st: StatementInfo) -> str:
        """从对账单信息提取月份 key，如 '2022年08月'"""
        if st.month:
            # 处理 "2022-08" 或 "2022-01~2022-02" 格式
            m = re.match(r"(\d{4})-(\d{1,2})", st.month)
            if m:
                y, mo = m.group(1), m.group(2).zfill(2)
                # 检查是否跨月
                if "~" in st.month:
                    m2 = re.search(r"~\s*\d{4}-(\d{1,2})", st.month)
                    if m2:
                        mo2 = m2.group(1).zfill(2)
                        return f"{y}年{mo}-{mo2}月"
                return f"{y}年{mo}月"
        return ""

    def _month_key_to_yyyymm(self, month_key: str) -> str | None:
        """'2022年08月' → '202208'"""
        m = re.match(r"(\d{4})年(\d{2})", month_key)
        if m:
            return m.group(1) + m.group(2)
        return None

    def _build_folder_name(
        self,
        month_key: str,
        statement: StatementInfo,
        group: MonthGroup,
        issues: list[str],
    ) -> str:
        """生成文件夹名称"""
        doc_type = "对账单与出库单" if group.deliveries else "对账单"

        if not issues:
            status = FOLDER_CONFIRMED
        else:
            status = "_".join(issues)

        # 统计具体问题数量
        unmatched_count = sum(
            1 for d in group.deliveries if d.match_status == STATUS_UNMATCHED
        )
        if unmatched_count > 0 and FOLDER_DELIVERY_MISMATCH not in status:
            status += f"_{unmatched_count}张出库单无法确认"
        elif unmatched_count > 0:
            status = status.replace(
                FOLDER_DELIVERY_MISMATCH,
                f"{unmatched_count}张出库单无法确认",
            )

        return f"{month_key}{doc_type}（{status}）"

    @staticmethod
    def _normalize_date(val: Any) -> str | None:
        if not val:
            return None
        s = str(val)
        digits = re.sub(r"\D", "", s)
        if len(digits) == 8:
            return digits
        return None

    @staticmethod
    def _to_float(val: Any) -> float | None:
        if val is None:
            return None
        try:
            return float(str(val).replace(",", ""))
        except (ValueError, TypeError):
            return None
