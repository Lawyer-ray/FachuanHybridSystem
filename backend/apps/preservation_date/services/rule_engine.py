"""
财产保全规则引擎 fallback 模块

当 LLM 提取失败或返回空结果时，使用正则表达式规则引擎作为兜底方案,
从法院文书中提取财产保全措施信息。

规则引擎基于法律文书常见表述模式进行匹配，不依赖大模型。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .models import PreservationMeasure

logger = logging.getLogger("apps.preservation_date")


@dataclass
class RuleMatch:
    """规则匹配结果."""

    measure_type: str
    property_description: str
    raw_text: str
    start_date: str | None = None
    end_date: str | None = None
    duration: str | None = None
    is_pending: bool = False


# ---- 正则规则定义 ----

# 轮候措施匹配
PENDING_PATTERNS: list[tuple[str, str, bool]] = [
    # (pattern, measure_type, is_pending)
    (r"轮候冻结[\\：为、]?(.*?)(?=，|,|；|;|。|$)", "轮候冻结", True),
    (r"轮候查封[\\：为、]?(.*?)(?=，|,|；|;|。|$)", "轮候查封", True),
    (r"轮候扣押[\\：为、]?(.*?)(?=，|,|；|;|。|$)", "轮候扣押", True),
]

# 正式措施匹配 (需更精确，避免匹配到"轮候冻结"中的"冻结")
FORMAL_PATTERNS: list[tuple[str, str]] = [
    (r"(?<!轮候)冻结[\\：为、]?(.*?)(?=，|,|；|;|。|$)", "冻结"),
    (r"(?<!轮候)查封[\\：为、]?(.*?)(?=，|,|；|;|。|$)", "查封"),
    (r"(?<!轮候)扣押[\\：为、]?(.*?)(?=，|,|；|;|。|$)", "扣押"),
    (r"续行冻结[\\：为、]?(.*?)(?=，|,|；|;|。|$)", "续行冻结"),
    (r"续行查封[\\：为、]?(.*?)(?=，|,|；|;|。|$)", "续行查封"),
]

# 日期匹配模式
DATE_RANGE_PATTERN = re.compile(
    r"自\s*(\d{4}[年/\\.\-]\d{1,2}[月/\\.\-]\d{1,2}[日]?)[起]"
    r"\s*[至到]\s*"
    r"(\d{4}[年/\\.\-]\d{1,2}[月/\\.\-]\d{1,2}[日]?)[止]?",
    re.UNICODE,
)

DATE_SINGLE_PATTERN = re.compile(
    r"(\d{4}[年/\\.\-]\d{1,2}[月/\\.\-]\d{1,2}[日]?)",
    re.UNICODE,
)

# 期限匹配
DURATION_PATTERN = re.compile(
    r"(?:期限|有效期)[为是]?\s*([一二三四五六七八九十百千万\\d]+[个\\s]*[年月日])",
    re.UNICODE,
)

# 财产线索关键词 (用于识别描述不完整的情况)
PROPERTY_KEYWORDS: list[str] = [
    "账号", "账户", "银行", "存款", "房产", "房屋", "不动产",
    "股权", "股份", "股票", "车辆", "机动车", "土地使用权",
    "商标", "专利", "著作权", "债权", "应收账款",
]


class PreservationRuleEngine:
    """财产保全规则提取引擎.

    基于正则表达式从文书中提取保全措施，作为 LLM 的 fallback。
    """

    def __init__(self) -> None:
        self._pending_patterns = [
            (re.compile(p), mt, ip) for p, mt, ip in PENDING_PATTERNS
        ]
        self._formal_patterns = [
            (re.compile(p), mt) for p, mt in FORMAL_PATTERNS
        ]

    def extract(self, text: str) -> list[PreservationMeasure]:
        """从文本中提取保全措施.

        提取策略:
        1. 按句子拆分 (以。! 等结尾)
        2. 在每个句子中匹配轮候和正式措施
        3. 提取日期和期限信息
        4. 组装为 PreservationMeasure

        Args:
            text: 预处理后的文书文本

        Returns:
            提取到的保全措施列表
        """
        if not text or not text.strip():
            return []

        measures: list[PreservationMeasure] = []

        # 按段落/句子拆分处理
        segments = self._segment_text(text)

        for segment in segments:
            segment_measures = self._extract_from_segment(segment)
            measures.extend(segment_measures)

        # 去重: 相同 measure_type + property_description 的去重
        measures = self._deduplicate(measures)

        logger.info(
            "规则引擎提取完成: 共 %d 条措施, 来自 %d 个段落",
            len(measures), len(segments),
        )
        return measures

    def _segment_text(self, text: str) -> list[str]:
        """将文本按句子拆分.

        Args:
            text: 输入文本

        Returns:
            句子列表
        """
        # 先按换行拆分，再按中文句号/分号等拆分
        paragraphs = re.split(r"[\n\r]+", text)
        segments: list[str] = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # 按句子拆分 (中文句号、问号、感叹号)
            sentences = re.split(r"(?<=[。！？;；])", para)
            for sent in sentences:
                sent = sent.strip()
                if len(sent) > 5:  # 过滤过短的片段
                    segments.append(sent)

        return segments

    def _extract_from_segment(self, segment: str) -> list[PreservationMeasure]:
        """从单个段落/句子中提取措施.

        Args:
            segment: 文本段落

        Returns:
            该段落中提取的措施列表
        """
        measures: list[PreservationMeasure] = []
        matched_spans: list[tuple[int, int]] = []

        # 先匹配轮候措施 (优先级高，避免被正式措施截断)
        for pattern, measure_type, is_pending in self._pending_patterns:
            for match in pattern.finditer(segment):
                span = match.span()
                # 检查是否与已有匹配重叠
                if self._is_overlapping(span, matched_spans):
                    continue
                matched_spans.append(span)

                raw_text = match.group(0)
                prop_desc = match.group(1).strip() if match.lastindex and match.group(1) else raw_text

                # 清理 property_description
                prop_desc = self._clean_property_desc(prop_desc)

                if not prop_desc or len(prop_desc) < 3:
                    continue

                # 提取日期 (从整段和匹配文本附近)
                dates = self._extract_dates(segment, match.end())
                duration = self._extract_duration(segment)

                measures.append(PreservationMeasure(
                    measure_type=measure_type,
                    property_description=prop_desc,
                    duration=None,  # 轮候无期限
                    start_date=None,  # 轮候无起算日
                    end_date=None,  # 轮候无到期日
                    is_pending=True,
                    pending_note="轮候状态,期限自转为正式查封/冻结之日起算",
                    raw_text=raw_text,
                ))

        # 再匹配正式措施
        for pattern, measure_type in self._formal_patterns:
            for match in pattern.finditer(segment):
                span = match.span()
                if self._is_overlapping(span, matched_spans):
                    continue
                matched_spans.append(span)

                raw_text = match.group(0)
                prop_desc = match.group(1).strip() if match.lastindex and match.group(1) else raw_text
                prop_desc = self._clean_property_desc(prop_desc)

                if not prop_desc or len(prop_desc) < 3:
                    continue

                # 提取日期和期限
                dates = self._extract_dates(segment, match.end())
                duration = self._extract_duration(segment)

                # 解析日期
                start_date = self._parse_date(dates[0]) if dates else None
                end_date = self._parse_date(dates[1]) if len(dates) > 1 else None

                # 如果只有一个日期，根据期限推算
                if start_date and not end_date and duration:
                    end_date = self._calculate_end_date(start_date, duration)

                # 确定 is_pending
                is_pending = measure_type in ("续行查封", "续行冻结")

                measures.append(PreservationMeasure(
                    measure_type=measure_type,
                    property_description=prop_desc,
                    duration=duration,
                    start_date=start_date,
                    end_date=end_date,
                    is_pending=is_pending,
                    pending_note="续保措施,系对原保全的延续" if is_pending else None,
                    raw_text=raw_text,
                ))

        return measures

    def _is_overlapping(self, span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
        """检查 span 是否与已有 spans 重叠.

        Args:
            span: (start, end)
            spans: 已有 span 列表

        Returns:
            是否重叠
        """
        start, end = span
        for s, e in spans:
            # 简单判断: 如果有交集则视为重叠
            if not (end <= s or start >= e):
                return True
        return False

    def _clean_property_desc(self, desc: str) -> str:
        """清理财产描述，去除无关词汇.

        Args:
            desc: 原始描述

        Returns:
            清理后的描述
        """
        # 去除句首的"被申请人""被保全人"等
        desc = re.sub(r"^(被申请人|被保全人|被执行人|申请人|原告|被告)[\\的为]", "", desc)
        # 去除末尾的标点
        desc = desc.rstrip("，,;；.。")
        return desc.strip()

    def _extract_dates(self, text: str, after_pos: int = 0) -> list[str]:
        """从文本中提取日期.

        优先提取日期范围 (自X起至Y止)，其次提取独立日期。

        Args:
            text: 文本
            after_pos: 从该位置之后开始查找 (关联性更高)

        Returns:
            日期字符串列表
        """
        dates: list[str] = []
        search_text = text[after_pos:] if after_pos < len(text) else text

        # 尝试匹配范围
        range_match = DATE_RANGE_PATTERN.search(search_text)
        if range_match:
            dates.append(range_match.group(1))
            dates.append(range_match.group(2))
            return dates

        # 回退到匹配独立日期 (找距离 after_pos 最近的)
        all_dates = DATE_SINGLE_PATTERN.findall(search_text)
        if all_dates:
            # 最多取2个日期
            dates.extend(all_dates[:2])

        return dates

    def _extract_duration(self, text: str) -> str | None:
        """提取期限描述.

        Args:
            text: 文本

        Returns:
            期限字符串或 None
        """
        match = DURATION_PATTERN.search(text)
        if match:
            return match.group(1).strip()
        return None

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """解析日期字符串.

        支持格式:
        - YYYY-MM-DD
        - YYYY/MM/DD
        - YYYY.MM.DD
        - YYYY年MM月DD日

        Args:
            date_str: 日期字符串

        Returns:
            datetime 或 None
        """
        if not date_str:
            return None

        # 规范化
        date_str = re.sub(r"[\s]+", "", date_str)

        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%Y年%m月%d日",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # 回退: 正则提取数字
        nums = re.findall(r"\d+", date_str)
        if len(nums) >= 3:
            try:
                year = int(nums[0])
                month = int(nums[1])
                day = int(nums[2])
                return datetime(year, month, day)
            except (ValueError, TypeError):
                pass

        return None

    def _calculate_end_date(self, start_date: datetime, duration: str) -> datetime | None:
        """根据起始日期和期限推算到期日.

        Args:
            start_date: 起始日期
            duration: 期限描述

        Returns:
            到期日期或 None
        """
        duration = duration.strip()

        # 提取数字
        num_match = re.search(r"(\d+)", duration)
        if not num_match:
            return None

        num = int(num_match.group(1))

        if "年" in duration:
            # 按年: 注意闰年等因素，简单处理
            try:
                year = start_date.year + num
                # 处理2月29日问题
                month = start_date.month
                day = start_date.day
                if month == 2 and day == 29:
                    # 尝试创建，如果失败则取2月最后一天
                    try:
                        return datetime(year, month, day) - timedelta(days=1)
                    except ValueError:
                        return datetime(year, 2, 28) - timedelta(days=1)
                return datetime(year, month, day) - timedelta(days=1)
            except ValueError:
                return None

        elif "月" in duration:
            # 按月
            try:
                total_months = start_date.month + num
                year = start_date.year + (total_months - 1) // 12
                month = ((total_months - 1) % 12) + 1
                day = start_date.day
                # 处理月份天数不同问题
                import calendar
                max_day = calendar.monthrange(year, month)[1]
                if day > max_day:
                    day = max_day
                return datetime(year, month, day) - timedelta(days=1)
            except ValueError:
                return None

        elif "日" in duration or "天" in duration:
            return start_date + timedelta(days=num - 1)

        return None

    def _deduplicate(self, measures: list[PreservationMeasure]) -> list[PreservationMeasure]:
        """去重：相同 measure_type + property_description 只保留一条.

        Args:
            measures: 措施列表

        Returns:
            去重后的列表
        """
        seen: set[str] = set()
        result: list[PreservationMeasure] = []

        for m in measures:
            key = f"{m.measure_type}:{m.property_description}"
            if key not in seen:
                seen.add(key)
                result.append(m)

        return result


def extract_with_rules(text: str) -> list[PreservationMeasure]:
    """便捷函数: 使用规则引擎提取保全措施.

    Args:
        text: 文书文本

    Returns:
        保全措施列表
    """
    engine = PreservationRuleEngine()
    return engine.extract(text)
