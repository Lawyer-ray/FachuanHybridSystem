"""从文本中解析提醒事项的服务。

通过正则表达式提取日期和时间，通过关键词推断提醒类型，
生成结构化的提醒解析结果，供前端填充到 Reminder Inline 表单。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ---- 日期正则 ----
DATE_SINGLE_PATTERN = re.compile(
    r"(\d{4}[年/\.\-]\d{1,2}[月/\.\-]\d{1,2}[日]?)",
    re.UNICODE,
)

# ---- 时间正则 ----
# 匹配 "下午3点" "上午9点" "下午3点半" "15时30分" "下午3:30" 等
TIME_PATTERN = re.compile(
    r"(上午|下午|晚间|晚上|凌晨|早上)?\s*"
    r"(\d{1,2})\s*[点时：:]\s*(\d{1,2})?\s*(分|半)?",
    re.UNICODE,
)

# ---- 关键词 → 提醒类型映射 ----
# 顺序很重要：先匹配更具体的关键词
KEYWORD_TYPE_MAP: list[tuple[str, str]] = [
    ("开庭", "hearing"),
    ("庭审", "hearing"),
    ("传票", "hearing"),
    ("开庭传票", "hearing"),
    ("保全到期", "asset_preservation_expires"),
    ("保全期限", "asset_preservation_expires"),
    ("财产保全", "asset_preservation_expires"),
    ("举证期限", "evidence_deadline"),
    ("举证", "evidence_deadline"),
    ("证据交换", "evidence_deadline"),
    ("上诉期限", "appeal_deadline"),
    ("上诉", "appeal_deadline"),
    ("时效到期", "statute_limitations"),
    ("诉讼时效", "statute_limitations"),
    ("时效", "statute_limitations"),
    ("缴费期限", "payment_deadline"),
    ("缴费", "payment_deadline"),
    ("交费", "payment_deadline"),
    ("交纳", "payment_deadline"),
    ("补正期限", "submission_deadline"),
    ("补正", "submission_deadline"),
    ("提交期限", "submission_deadline"),
    ("提交", "submission_deadline"),
]

# 默认类型
DEFAULT_REMINDER_TYPE = "other"

# 提醒类型 → 中文标签（与 ReminderType.choices 保持一致）
REMINDER_TYPE_LABELS: dict[str, str] = {
    "hearing": "开庭",
    "asset_preservation_expires": "财产保全到期日",
    "evidence_deadline": "举证到期日",
    "appeal_deadline": "上诉期到期日",
    "statute_limitations": "诉讼时效到期日",
    "payment_deadline": "缴费期限",
    "submission_deadline": "补正/材料提交期限",
    "other": "其他",
}

@dataclass
class ParsedReminder:
    """解析出的提醒条目。"""

    content: str
    reminder_type: str
    reminder_type_label: str
    due_at: str  # ISO 8601 格式: YYYY-MM-DDTHH:MM
    source_text: str  # 原始匹配文本片段

def _infer_reminder_type(text: str) -> str:
    """根据关键词推断提醒类型。"""
    for keyword, reminder_type in KEYWORD_TYPE_MAP:
        if keyword in text:
            return reminder_type
    return DEFAULT_REMINDER_TYPE

def _parse_date(date_str: str) -> datetime | None:
    """解析日期字符串。

    支持格式:
    - YYYY-MM-DD
    - YYYY/MM/DD
    - YYYY.MM.DD
    - YYYY年MM月DD日
    """
    if not date_str:
        return None

    # 规范化：去掉多余空格
    date_str = re.sub(r"\s+", "", date_str)

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

def _extract_time_near_date(text: str, date_end: int) -> tuple[int, int] | None:
    """在日期之后提取时间信息。

    Args:
        text: 原始文本
        date_end: 日期匹配结束位置

    Returns:
        (hour, minute) 或 None
    """
    # 在日期后 10 个字符范围内搜索时间
    search_start = date_end
    search_end = min(len(text), date_end + 15)
    search_text = text[search_start:search_end]

    match = TIME_PATTERN.search(search_text)
    if not match:
        return None

    period = match.group(1) or ""
    hour_str = match.group(2)
    minute_str = match.group(3)
    half = match.group(4)

    try:
        hour = int(hour_str)
    except (ValueError, TypeError):
        return None

    # 处理上午/下午
    if period in ("下午", "晚间", "晚上") and hour < 12:
        hour += 12
    elif period == "凌晨" and hour == 12:
        hour = 0

    # 处理分钟
    minute = 0
    if half == "半":
        minute = 30
    elif minute_str:
        try:
            minute = int(minute_str)
        except (ValueError, TypeError):
            minute = 0

    # 合法性检查
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return (hour, minute)

    return None

def _extract_sentence(text: str, start: int, end: int, context_radius: int = 30) -> str:
    """从文本中提取日期所在的句子片段。"""
    # 向前后扩展到句子边界
    sent_start = max(0, start - context_radius)
    sent_end = min(len(text), end + context_radius)

    # 向前找句子开始
    for i in range(start - 1, max(0, start - context_radius * 2), -1):
        if text[i] in "。\n；;！!？?":
            sent_start = i + 1
            break

    # 向后找句子结束
    for i in range(end, min(len(text), end + context_radius * 2)):
        if text[i] in "。\n；;！!？?":
            sent_end = i + 1
            break

    return text[sent_start:sent_end].strip()

def parse_reminders_from_text(text: str) -> list[ParsedReminder]:
    """从文本中解析出提醒事项。

    流程:
    1. 用正则提取所有日期
    2. 在日期附近查找时间信息
    3. 对每个日期，提取其所在句子的上下文
    4. 根据上下文关键词推断提醒类型
    5. 组装 ParsedReminder 列表

    Args:
        text: 日志内容文本

    Returns:
        解析出的提醒条目列表
    """
    if not text or not text.strip():
        return []

    results: list[ParsedReminder] = []
    seen_dates: set[str] = set()  # 去重

    for match in DATE_SINGLE_PATTERN.finditer(text):
        date_str = match.group(1)

        # 去重
        normalized_date = re.sub(r"[年/\.\-月日]", "", date_str)
        if normalized_date in seen_dates:
            continue
        seen_dates.add(normalized_date)

        # 解析日期
        parsed_dt = _parse_date(date_str)
        if parsed_dt is None:
            logger.info("无法解析日期: %s", date_str)
            continue

        # 在日期附近提取时间
        time_info = _extract_time_near_date(text, match.end())
        if time_info is not None:
            hour, minute = time_info
            parsed_dt = parsed_dt.replace(hour=hour, minute=minute)
        else:
            # 默认时间 09:00
            parsed_dt = parsed_dt.replace(hour=9, minute=0)

        # 提取上下文句子（包含时间部分）
        context_end = match.end()
        # 如果有时间，扩展上下文范围以包含时间描述
        if time_info is not None:
            search_start = match.end()
            search_end = min(len(text), match.end() + 15)
            time_match = TIME_PATTERN.search(text[search_start:search_end])
            if time_match:
                context_end = search_start + time_match.end()

        sentence = _extract_sentence(text, match.start(), context_end)

        # 推断类型
        reminder_type = _infer_reminder_type(sentence)
        reminder_type_label = REMINDER_TYPE_LABELS.get(reminder_type, "其他")

        # 生成内容描述
        content = _generate_content(sentence, reminder_type_label, parsed_dt)

        results.append(
            ParsedReminder(
                content=content,
                reminder_type=reminder_type,
                reminder_type_label=reminder_type_label,
                due_at=parsed_dt.strftime("%Y-%m-%dT%H:%M"),
                source_text=sentence,
            )
        )

    logger.info("从文本中解析出 %d 条提醒", len(results))
    return results

def _generate_content(sentence: str, type_label: str, dt: datetime) -> str:
    """生成提醒事项内容描述。"""
    # 截取句子，避免过长
    if len(sentence) > 80:
        sentence = sentence[:80] + "…"
    return f"{type_label}：{sentence}"
