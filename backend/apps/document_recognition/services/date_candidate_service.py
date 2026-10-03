"""日期候选服务

职责链：提取合并（LLM key_events + 正则候选）→ 落库为候选行 →
律师人工确认后写入重要日期提醒 → 撤销。

设计要点（评审定稿）：
- 幂等由候选行状态机承担：事务内 ``select_for_update`` 锁行，已 confirmed
  的行直接返回原 reminder_id；**不走** ``upsert_case_log_reminder_internal``
  （它按 case_log+source 定位只取一条，多日期会互相覆盖）。
- 未绑定案件的任务确认日期 → 创建**独立提醒**（无 case_log，metadata 带
  task 溯源），记一笔快捕获场景不强制选案。
- 存量自动写入的旧提醒无 metadata.source：确认前按
  ``(case_log_id, due_at)`` 查重复用，避免同一时间出现双提醒。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
from apps.reminders.models import ReminderType

from ._datetime_extraction_mixin import DatetimeExtractionMixin
from .data_classes import DocumentType

logger = logging.getLogger("apps.document_recognition")

REMINDER_SOURCE = "document_recognition"

# 类型展示优先级：开庭最关键，其次保全到期、举证、上诉……
REMINDER_TYPE_PRIORITY: dict[str, int] = {
    "hearing": 0,
    "asset_preservation_expires": 1,
    "evidence_deadline": 2,
    "appeal_deadline": 3,
    "payment_deadline": 4,
    "submission_deadline": 5,
    "statute_limitations": 6,
    "other": 7,
}

# 降级路径：上下文未命中类型关键词时按文书类型给默认
DEFAULT_TYPE_BY_DOCUMENT_TYPE: dict[DocumentType, str] = {
    DocumentType.SUMMONS: "hearing",
    DocumentType.EXECUTION_RULING: "asset_preservation_expires",
    DocumentType.OTHER: "other",
}

MAX_CANDIDATES = 8
STALE_DAYS = 180

_DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d")

# 期间表达式：从/自 X 起 至/到 Y（Y 年份允许 5 位——OCR 把 2025 识别成 20254 的高频错）
_PERIOD_RANGE_RE = re.compile(
    r"(?:从|自)(\d{4})年(\d{1,2})月(\d{1,2})日(?:起)?(?:至|到)(\d{4,5})年(\d{1,2})月(\d{1,2})日"
)
# 期间长度（中文大写数字）：如「冻结期间为壹年」
_PERIOD_YEARS_RE = re.compile(r"期间(?:为|是|共)?(壹|一|贰|两|二|三|叁|四|肆|五|伍)年")
_CN_YEAR_NUM: dict[str, int] = {
    "壹": 1,
    "一": 1,
    "贰": 2,
    "两": 2,
    "二": 2,
    "三": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
}

# ---------------------------------------------------------------------------
# 相对期限推算：「收到本通知次日起两日内交纳」等表述本身不含日期，
# 以文书落款/打印日期为锚，按「起算当日不计入、自次日起算」推算届满日。
# ---------------------------------------------------------------------------

# 文书签发/落款日期（阿拉伯数字）：如「2025年11月11日」
_ISSUE_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
# 文书签发/落款日期（中文数字）：如「二〇二五年十一月十一日」
_ISSUE_DATE_CN_RE = re.compile(
    r"([〇零一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月([一二三四五六七八九十]{1,3})日"
)

# 相对期限数字：阿拉伯或中文（含大写与「两」），1~3 位
_REL_DAYS_GROUP = r"(\d{1,3}|[一二三四五六七八九十两壹贰叁肆伍陆柒捌玖拾]{1,3})"

# 带「收到/送达」锚的相对期限：如「收到本通知次日起两日内」「自收到本决定书之日起7日内」
_RELATIVE_ANCHOR_RE = re.compile(
    rf"(?:收到|接到|收悉|送达)[^，。；;\n]{{0,14}}?(?:之|次)?(?:日起?|后){_REL_DAYS_GROUP}日内"
)
# 无锚动作版：期限动词直接跟在「N日内」后，如「7日内付款」「十五日内向本院交纳」
_RELATIVE_ACTION_RE = re.compile(rf"{_REL_DAYS_GROUP}日内[^，。；;\n]{{0,16}}?(?:交纳|缴纳|缴款|缴费|付款|支付|付清)")

# 相对期限的事件类型：按动作动词判（「保全费…交纳」须判 payment 而非被名词「保全」带偏）
_RELATIVE_EVENT_TYPES: list[tuple[str, tuple[str, ...]]] = [
    ("payment_deadline", ("交纳", "缴纳", "缴款", "缴费", "付款", "支付", "付清")),
    ("submission_deadline", ("补正", "提交材料", "递交材料")),
    ("appeal_deadline", ("上诉",)),
    ("evidence_deadline", ("举证",)),
]

_CN_DIGITS: dict[str, int] = {
    "一": 1,
    "壹": 1,
    "二": 2,
    "贰": 2,
    "两": 2,
    "三": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陆": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
}
_CN_YEAR_DIGITS: dict[str, int] = {"〇": 0, "零": 0, **_CN_DIGITS}


def _add_years(start: datetime, years: int) -> datetime:
    """start + N 年（2/29 闰年回退到 2/28）。"""
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        return start.replace(year=start.year + years, day=28)


def _apply_period_rules(text: str, drafts: list[DateCandidateDraft]) -> list[DateCandidateDraft]:
    """期间结构后处理（确定性规则，不依赖 LLM）：

    1. 「从X起至Y止」的**起始日 X 不是提醒事件**，从候选中剔除；
    2. 期间长度（中文数字）+ 起始日可算出到期日，用于校正被 OCR 乱码
       （如 20254 年）或 LLM 误读的止点 Y。
    """
    if not text or not drafts:
        return drafts

    periods: list[tuple[str, datetime, datetime | None, datetime | None]] = []
    for m in _PERIOD_RANGE_RE.finditer(text):
        try:
            start = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        end: datetime | None = None
        try:
            end = datetime(int(m.group(4)), int(m.group(5)), int(m.group(6)))
        except ValueError:
            pass
        # 期间句前 30 字内找「…期间为N年」
        years_match = _PERIOD_YEARS_RE.search(text[max(0, m.start() - 30) : m.start() + 5])
        years = _CN_YEAR_NUM.get(years_match.group(1)) if years_match else None
        computed_end = _add_years(start, years) if years else None
        periods.append((m.group(0), start, end, computed_end))
        logger.info(
            "识别到期间表达式: %s (start=%s, end=%s, 按%s年推算=%s)",
            m.group(0),
            start.date(),
            end.date() if end else None,
            years,
            computed_end.date() if computed_end else None,
        )
    if not periods:
        return drafts

    kept: list[DateCandidateDraft] = []
    for draft in drafts:
        drop = False
        fix_to: datetime | None = None
        for expr, start, _end, computed_end in periods:
            anchor = expr[:12]
            if anchor not in (draft.context_text or ""):
                continue
            if draft.due_at.date() == start.date():
                drop = True  # 期间起始日：非提醒事件
            elif computed_end is not None and draft.due_at.date() != computed_end.date():
                fix_to = computed_end  # 止点被 OCR/LLM 读错 → 算术校正
        if drop:
            logger.info("剔除期间起始日候选: %s (%s)", draft.due_at.date(), draft.context_text[:40])
            continue
        if fix_to is not None:
            logger.warning(
                "期间到期日算术校正: %s -> %s (%s)",
                draft.due_at.date(),
                fix_to.date(),
                draft.context_text[:40],
            )
            draft.due_at = datetime.combine(fix_to.date(), draft.due_at.time())
        kept.append(draft)
    return kept


def _parse_cn_number(text: str) -> int | None:
    """中文数字（1~99，含大写、「两」、「十」组合）或阿拉伯数字 → int；无法解析返回 None。"""
    if text.isdigit():
        return int(text)
    for sep in ("十", "拾"):
        if sep in text:
            left, _, right = text.partition(sep)
            if (left and left not in _CN_DIGITS) or (right and right not in _CN_DIGITS):
                return None
            tens = _CN_DIGITS.get(left, 1) if left else 1
            ones = _CN_DIGITS.get(right, 0) if right else 0
            return tens * 10 + ones
    return _CN_DIGITS.get(text)


def _parse_cn_year(text: str) -> int | None:
    """中文数字年份逐位转换：「二〇二五」→ 2025。"""
    value = 0
    for ch in text:
        digit = _CN_YEAR_DIGITS.get(ch)
        if digit is None:
            return None
        value = value * 10 + digit
    return value


def _find_issue_date(text: str) -> datetime | None:
    """文书签发/落款日期：取全文**最后一个**「YYYY年M月D日」（阿拉伯或中文数字）。

    落款惯例在文末（如「打印日期：二〇二五年十一月十一日」），取最后一个
    可避开正文中其他业务日期（开庭日、举证截止日等）。
    """
    found: list[datetime] = []
    for m in _ISSUE_DATE_RE.finditer(text):
        try:
            found.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            continue
    for m in _ISSUE_DATE_CN_RE.finditer(text):
        year, month, day = _parse_cn_year(m.group(1)), _parse_cn_number(m.group(2)), _parse_cn_number(m.group(3))
        if year is None or month is None or day is None:
            continue
        try:
            found.append(datetime(year, month, day))
        except ValueError:
            continue
    valid = [dt for dt in found if 2020 <= dt.year <= 2030]
    return valid[-1] if valid else None


def _relative_event_type(context: str) -> str:
    """按动作动词推断相对期限的事件类型（未命中返回 other）。"""
    for reminder_type, verbs in _RELATIVE_EVENT_TYPES:
        if any(verb in context for verb in verbs):
            return reminder_type
    return "other"


def _iter_relative_deadlines(text: str) -> list[tuple[re.Match[str], int, int, int]]:
    """逐句扫描相对期限表述，返回 (匹配对象, 天数N, 句首偏移, 句长)。

    每句优先「收到/送达」锚版，未命中再用动作版（避免同句被两个模式重复推算）。
    句首偏移供后续取窗——上下文窗口不得跨句，否则相邻句的期限动词会互相污染。
    """
    results: list[tuple[re.Match[str], int, int, int]] = []
    pos = 0
    for sentence in re.split(r"[。；;\n]", text):
        sent_start, sent_len = pos, len(sentence)
        pos = sent_start + sent_len + 1  # 跳过单字符分隔符
        if not sentence:
            continue
        m = _RELATIVE_ANCHOR_RE.search(sentence) or _RELATIVE_ACTION_RE.search(sentence)
        if m is None:
            continue
        days = _parse_cn_number(m.group(1))
        if days is None or not 1 <= days <= 365:
            continue
        results.append((m, days, sent_start, sent_len))
    return results


def _match_relative_draft_by_context(
    drafts: list[DateCandidateDraft], core: str, claimed: set[int]
) -> DateCandidateDraft | None:
    """按「原文表述出现在候选 context 中」精确认领（LLM 保留原文时最可靠）。"""
    if not core:
        return None
    for draft in drafts:
        if id(draft) not in claimed and core in (draft.context_text or ""):
            return draft
    return None


def _match_relative_draft_by_fingerprint(
    drafts: list[DateCandidateDraft], event_type: str, anchor: datetime, claimed: set[int]
) -> DateCandidateDraft | None:
    """按「同类型且日期=锚日」指纹认领——LLM 把落款日直接当事件日的典型形态。"""
    for draft in drafts:
        if id(draft) not in claimed and draft.reminder_type == event_type and draft.due_at.date() == anchor.date():
            return draft
    return None


def _apply_relative_deadline_rules(text: str, drafts: list[DateCandidateDraft]) -> list[DateCandidateDraft]:
    """相对期限推算（确定性规则，不依赖 LLM）。

    「保全费请你方于收到本通知次日起两日内向本院交纳」这类表述不含日期，
    LLM 常就近把落款日当事件日。规则以签发/落款日期为锚，按「起算当日
    不计入、自次日起算」推算届满日 = 锚 + N 天（「次日起两日内」：次日为
    第 1 天 → 锚 + 2；「（之）日起七日内」→ 锚 + 7）。

    认领分三轮，避免多期限句互相争抢同一条候选（context 精确匹配优先于
    指纹兜底）：1) 原文表述出现在候选 context → 校正该候选；2) 未认领事件
    按「同类型且日期=锚日」指纹认领；3) 仍未认领（LLM 漏提）→ 补正则候选。
    """
    if not text:
        return drafts
    anchor = _find_issue_date(text)
    if anchor is None:
        return drafts

    events: list[dict[str, Any]] = []
    for m, days, sent_start, sent_len in _iter_relative_deadlines(text):
        # 取窗不越过句边界：相邻句的期限动词（如前句的「交纳」）不得污染本句类型判断
        ctx_from = max(sent_start, sent_start + m.start() - 20)
        ctx_to = min(sent_start + sent_len, sent_start + m.end() + 25)
        context = text[ctx_from:ctx_to].strip()
        events.append(
            {
                "core": m.group(0)[:18],
                "days": days,
                "deadline": anchor + timedelta(days=days),
                "context": context,
                "event_type": _relative_event_type(context),
                "claimed": False,
            }
        )

    results = list(drafts)
    claimed_drafts: set[int] = set()

    def _claim(draft: DateCandidateDraft, event: dict[str, Any]) -> None:
        if draft.due_at.date() != event["deadline"].date():
            logger.warning(
                "相对期限届满日校正: %s -> %s (锚=%s + %d天, %s)",
                draft.due_at.date(),
                event["deadline"].date(),
                anchor.date(),
                event["days"],
                event["context"][:40],
            )
            draft.due_at = datetime.combine(event["deadline"].date(), draft.due_at.time())
        draft.confidence = max(draft.confidence, 0.9)
        claimed_drafts.add(id(draft))
        event["claimed"] = True

    # 1) context 精确认领
    for event in events:
        draft = _match_relative_draft_by_context(results, event["core"], claimed_drafts)
        if draft is not None:
            _claim(draft, event)

    # 2) 指纹兜底认领（LLM 把落款日当事件日的典型形态）
    for event in events:
        if event["claimed"]:
            continue
        draft = _match_relative_draft_by_fingerprint(results, event["event_type"], anchor, claimed_drafts)
        if draft is not None:
            _claim(draft, event)

    # 3) LLM 漏提 → 补正则候选
    for event in events:
        if event["claimed"]:
            continue
        if any(d.due_at.date() == event["deadline"].date() and d.reminder_type == event["event_type"] for d in results):
            continue  # LLM 已按 prompt 正确推算，不重复补
        results.append(
            DateCandidateDraft(
                due_at=event["deadline"],
                reminder_type=event["event_type"],
                context_text=event["context"][:255],
                source="regex",
                confidence=0.85,
            )
        )
        logger.info(
            "相对期限推算候选: 届满=%s (锚=%s + %d天, type=%s)",
            event["deadline"].date(),
            anchor.date(),
            event["days"],
            event["event_type"],
        )
    return results


def _dedupe_same_context(drafts: list[DateCandidateDraft]) -> list[DateCandidateDraft]:
    """同一原文上下文只保留一个候选（按既定排序取首个；空上下文不参与）。"""
    seen: set[str] = set()
    unique: list[DateCandidateDraft] = []
    for draft in drafts:
        key = draft.context_text
        if not key or key not in seen:
            if key:
                seen.add(key)
            unique.append(draft)
    return unique


@dataclass
class DateCandidateDraft:
    """合并后的日期候选（落库前的内存形态）。"""

    due_at: datetime
    reminder_type: str
    context_text: str
    source: str  # llm | regex | merged
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "due_at": self.due_at.isoformat(),
            "reminder_type": self.reminder_type,
            "context_text": self.context_text,
            "source": self.source,
            "confidence": self.confidence,
        }


class _RegexCandidateExtractor(DatetimeExtractionMixin):
    """仅用 Mixin 的纯函数能力，避免依赖 InfoExtractor 的 LLM 注入。"""


def parse_candidate_datetime(value: str) -> datetime | None:
    """解析 LLM/前端提交的日期时间字符串（统一返回 naive 本地时间）。"""
    from django.utils.timezone import localtime

    text = value.strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    # 带时区偏移的输入（如 LLM 输出 +00:00）：先换算到本地时区再去 tzinfo，
    # 直接 replace 会把偏移量原样丢弃导致时间错位
    return localtime(parsed).replace(tzinfo=None)


def _normalize_aware(dt: datetime) -> datetime:
    """naive 本地时间补时区（与 reminders.validators.normalize_due_at 口径一致）。"""
    from django.utils.timezone import make_aware

    return dt if dt.tzinfo else make_aware(dt)


def build_date_candidates(
    text: str,
    analysis: Any | None,
    document_type: DocumentType,
    *,
    regex_extractor: Any | None = None,
) -> list[DateCandidateDraft]:
    """合并 LLM key_events 与正则候选为去重后的候选列表。

    去重键 = (日期时间, 提醒类型)：同值 LLM 优先（source 升级为 merged、
    置信度取 max）；同日不同类型都保留（开庭日与举证截止同日是真实场景）。
    """
    extractor = regex_extractor or _RegexCandidateExtractor()
    default_type = DEFAULT_TYPE_BY_DOCUMENT_TYPE.get(document_type, "other")

    drafts: dict[tuple[datetime, str], DateCandidateDraft] = {}

    # 1. LLM 事件
    key_events = list(getattr(analysis, "key_events", None) or [])
    for event in key_events:
        parsed = parse_candidate_datetime(str(getattr(event, "datetime", "") or ""))
        if parsed is None:
            logger.warning("LLM 日期事件解析失败，跳过: %s", getattr(event, "datetime", None))
            continue
        event_type = getattr(event, "event_type", "other") or "other"
        if event_type not in ReminderType.values:
            event_type = "other"
        context = str(getattr(event, "context", "") or "")[:255]
        drafts[(parsed, event_type)] = DateCandidateDraft(
            due_at=parsed,
            reminder_type=event_type,
            context_text=context,
            source="llm",
            confidence=float(getattr(event, "confidence", 0.7) or 0.7),
        )

    # 2. 正则候选（透出全部，含上下文与类型推断）
    for candidate in extractor.extract_datetime_candidates(text):
        parsed = candidate["datetime"]
        reminder_type = candidate.get("reminder_type") or default_type
        key = (parsed, reminder_type)
        regex_confidence = round(min(float(candidate.get("context_score", 0)), 100) / 100 * 0.85, 2)
        existing = drafts.get(key)
        if existing is None:
            drafts[key] = DateCandidateDraft(
                due_at=parsed,
                reminder_type=reminder_type,
                context_text=str(candidate.get("context_text", ""))[:255],
                source="regex",
                confidence=regex_confidence,
            )
        else:
            existing.source = "merged"
            existing.confidence = max(existing.confidence, regex_confidence)
            if not existing.context_text:
                existing.context_text = str(candidate.get("context_text", ""))[:255]

    # 3. 期间结构后处理：起始日剔除、到期日算术校正、相对期限推算、同上下文去重
    drafts_list = _apply_period_rules(text, list(drafts.values()))
    drafts_list = _apply_relative_deadline_rules(text, drafts_list)

    # 4. 陈旧候选降置信（改判文书可能含历史日期，折叠而非丢弃）
    today = timezone.localdate()
    for draft in drafts_list:
        if (today - draft.due_at.date()).days > STALE_DAYS:
            draft.confidence = min(draft.confidence, 0.3)

    ordered = sorted(
        drafts_list,
        key=lambda d: (REMINDER_TYPE_PRIORITY.get(d.reminder_type, 99), -d.confidence, d.due_at),
    )
    return _dedupe_same_context(ordered)[:MAX_CANDIDATES]


def persist_candidates(task: Any, drafts: list[DateCandidateDraft]) -> int:
    """把候选草稿落库为候选行（任务已有候选时跳过，保证幂等）。"""
    from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionDateCandidate

    if task.date_candidates.exists():
        return 0

    rows = [
        DocumentRecognitionDateCandidate(
            task=task,
            due_at=_normalize_aware(draft.due_at),
            reminder_type=draft.reminder_type,
            context_text=draft.context_text,
            source=draft.source,
            confidence=draft.confidence,
            status=DateCandidateStatus.PENDING,
        )
        for draft in drafts
    ]
    DocumentRecognitionDateCandidate.objects.bulk_create(rows)
    refresh_task_confirmation_status(task)
    logger.info("日期候选已落库: task_id=%s, count=%d", task.id, len(rows))
    return len(rows)


def refresh_task_confirmation_status(task: Any) -> None:
    """按候选行状态刷新任务级日期确认进度（冗余字段，供筛选与侧栏）。"""
    from apps.document_recognition.models import DateConfirmationStatus

    counts = {"pending": 0, "confirmed": 0, "skipped": 0}
    for row in task.date_candidates.values_list("status", flat=True):
        counts[row] = counts.get(row, 0) + 1

    total = sum(counts.values())
    if total == 0:
        new_status = DateConfirmationStatus.NONE
    elif counts["pending"] == 0:
        new_status = DateConfirmationStatus.COMPLETE
    elif counts["confirmed"] + counts["skipped"] > 0:
        new_status = DateConfirmationStatus.PARTIAL
    else:
        new_status = DateConfirmationStatus.PENDING

    if task.date_confirmation_status != new_status:
        task.date_confirmation_status = new_status
        task.save(update_fields=["date_confirmation_status"])


def list_candidates(task: Any) -> list[dict[str, Any]]:
    """候选行序列化（API/admin 共用）。"""
    return [
        {
            "id": row.id,
            "due_at": row.due_at.isoformat(),
            "reminder_type": row.reminder_type,
            "reminder_type_label": _reminder_type_label(row.reminder_type),
            "context_text": row.context_text,
            "source": row.source,
            "confidence": row.confidence,
            "status": row.status,
            "reminder_id": row.reminder_id,
            "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        }
        for row in task.date_candidates.select_related("reminder").order_by("due_at", "id")
    ]


def _reminder_type_label(reminder_type: str) -> str:
    try:
        return str(ReminderType(reminder_type).label)
    except ValueError:
        return reminder_type


def _resolve_reminder_service() -> Any:
    from apps.reminders.services.wiring import get_reminder_service

    return get_reminder_service()


def _get_task_for_update(task_id: int, user: Any | None) -> Any:
    """行锁取任务并套归属口径（审计 P1 修复）。

    归属过滤并入同一次 ``.get()``（保持 ``select_for_update().get()`` 调用链，
    不破坏行锁防并发语义）；管理员见全量，普通用户见自己的任务与存量 NULL
    任务（兼容旧数据口径，详见 task_service.task_ownership_q）。
    非归属人非管理员与任务不存在同样抛 NotFoundError（404，不泄露存在性）。
    """
    from apps.document_recognition.models import DocumentRecognitionTask
    from apps.document_recognition.services.task_service import task_ownership_q

    qs = DocumentRecognitionTask.objects.select_for_update()
    ownership = task_ownership_q(user)
    try:
        if ownership is None:
            return qs.get(id=task_id)
        return qs.get(ownership, id=task_id)
    except DocumentRecognitionTask.DoesNotExist:
        raise NotFoundError(message="任务不存在", code="TASK_NOT_FOUND", errors={}) from None


def _build_reminder_content(reminder_type: str, context_text: str) -> str:
    label = _reminder_type_label(reminder_type)
    snippet = (context_text or "").strip()[:60]
    return f"{label}：{snippet}" if snippet else label


@transaction.atomic
def confirm_candidates(task_id: int, items: list[dict[str, Any]], user: Any | None = None) -> list[dict[str, Any]]:
    """批量确认/忽略日期候选，逐项返回结果。

    每项: {candidate_id, action: confirm|skip, due_at?, reminder_type?}。
    幂等：已 confirmed 的候选直接返回原 reminder_id。
    非归属人非管理员对任务不可见 → NotFoundError（404）。
    """
    from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionStatus

    task = _get_task_for_update(task_id, user)
    if task.status != DocumentRecognitionStatus.SUCCESS:
        raise ValidationException(
            message="任务尚未识别完成，不能确认日期",
            code="TASK_NOT_READY",
            errors={},
        )

    user_id = getattr(user, "id", None) if user else None
    reminder_service = _resolve_reminder_service()
    now = timezone.now()
    results: list[dict[str, Any]] = []

    candidate_ids = [item["candidate_id"] for item in items]
    locked_rows = {row.id: row for row in task.date_candidates.select_for_update().filter(id__in=candidate_ids)}

    for item in items:
        results.append(
            _confirm_single_item(
                task=task,
                item=item,
                row=locked_rows.get(item["candidate_id"]),
                reminder_service=reminder_service,
                user_id=user_id,
                now=now,
            )
        )

    refresh_task_confirmation_status(task)
    return results


def _confirm_single_item(
    *,
    task: Any,
    item: dict[str, Any],
    row: Any | None,
    reminder_service: Any,
    user_id: int | None,
    now: datetime,
) -> dict[str, Any]:
    from apps.document_recognition.models import DateCandidateStatus

    candidate_id = item["candidate_id"]
    action = item.get("action", "confirm")

    if row is None:
        return {
            "candidate_id": candidate_id,
            "status": "error",
            "reminder_id": None,
            "message": "候选不存在",
            "error_code": "CANDIDATE_NOT_FOUND",
        }

    if action == "skip":
        if row.status == DateCandidateStatus.CONFIRMED:
            return {
                "candidate_id": candidate_id,
                "status": "confirmed",
                "reminder_id": row.reminder_id,
                "message": "候选已确认过提醒，忽略无效",
                "error_code": None,
            }
        row.status = DateCandidateStatus.SKIPPED
        row.save(update_fields=["status", "updated_at"])
        return {
            "candidate_id": candidate_id,
            "status": "skipped",
            "reminder_id": None,
            "message": "已忽略",
            "error_code": None,
        }

    # action == confirm
    if row.status == DateCandidateStatus.CONFIRMED and row.reminder_id:
        return {
            "candidate_id": candidate_id,
            "status": "confirmed",
            "reminder_id": row.reminder_id,
            "message": "已确认过，幂等返回",
            "error_code": None,
        }

    due_at_raw = item.get("due_at") or row.due_at.isoformat()
    parsed = parse_candidate_datetime(str(due_at_raw)) if isinstance(due_at_raw, str) else due_at_raw
    if parsed is None:
        return {
            "candidate_id": candidate_id,
            "status": "error",
            "reminder_id": None,
            "message": "时间格式不正确",
            "error_code": "INVALID_TIME_FORMAT",
        }
    aware_due_at = _normalize_aware(parsed)

    reminder_type = item.get("reminder_type") or row.reminder_type
    if reminder_type not in ReminderType.values:
        return {
            "candidate_id": candidate_id,
            "status": "error",
            "reminder_id": None,
            "message": f"不支持的提醒类型: {reminder_type}",
            "error_code": "INVALID_REMINDER_TYPE",
        }

    message = "已写入提醒"
    reminder = _find_existing_reminder(reminder_service, task, aware_due_at)
    if reminder is not None:
        message = "复用了同时间点的既有提醒，未重复创建"
    else:
        reminder = reminder_service.create_reminder(
            case_log_id=task.case_log_id,
            reminder_type=reminder_type,
            content=_build_reminder_content(reminder_type, row.context_text),
            due_at=aware_due_at,
            metadata={
                "source": REMINDER_SOURCE,
                "source_id": f"task:{task.id}:candidate:{row.id}",
                "task_id": task.id,
            },
        )
        # 确认过的重要日期默认列入案件「重要时间」视图（服务层无该参数，落实例后补写）
        reminder.include_in_important_time = True
        reminder.save(update_fields=["include_in_important_time"])

    row.due_at = aware_due_at
    row.reminder_type = reminder_type
    row.status = DateCandidateStatus.CONFIRMED
    row.reminder_id = reminder.id
    row.confirmed_by_id = user_id
    row.confirmed_at = now
    row.save(
        update_fields=[
            "due_at",
            "reminder_type",
            "status",
            "reminder_id",
            "confirmed_by_id",
            "confirmed_at",
            "updated_at",
        ]
    )

    logger.info(
        "日期候选已确认: task_id=%s, candidate_id=%s, reminder_id=%s, standalone=%s",
        task.id,
        candidate_id,
        reminder.id,
        task.case_log_id is None,
    )
    return {
        "candidate_id": candidate_id,
        "status": "confirmed",
        "reminder_id": reminder.id,
        "message": message,
        "error_code": None,
    }


def _find_existing_reminder(reminder_service: Any, task: Any, aware_due_at: datetime) -> Any | None:
    """按 (case_log_id, due_at) 查重复用（含无 source 的旧自动提醒）；独立提醒无查重域。"""
    if task.case_log_id is None:
        return None
    existing = reminder_service.list_reminders(case_log_id=task.case_log_id)
    for reminder in existing:
        if reminder.due_at == aware_due_at:
            return reminder
    return None


@transaction.atomic
def revoke_confirmation(task_id: int, candidate_id: int, user: Any | None = None) -> dict[str, Any]:
    """撤销确认：删除本功能创建的提醒，候选行回到待确认。

    非归属人非管理员对任务不可见 → NotFoundError（404）。
    """
    from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionDateCandidate

    task = _get_task_for_update(task_id, user)
    try:
        row = task.date_candidates.select_for_update().get(id=candidate_id)
    except DocumentRecognitionDateCandidate.DoesNotExist:
        raise NotFoundError(message="候选不存在", code="CANDIDATE_NOT_FOUND", errors={}) from None

    if row.status != DateCandidateStatus.CONFIRMED:
        raise ValidationException(message="候选未确认，无需撤销", code="NOT_CONFIRMED", errors={})

    if row.reminder_id:
        reminder_service = _resolve_reminder_service()
        reminder = reminder_service.get_reminder(row.reminder_id)
        metadata = reminder.metadata if isinstance(reminder.metadata, dict) else {}
        if metadata.get("source") != REMINDER_SOURCE:
            raise ValidationException(
                message="该提醒不是文书识别创建的，不能在此撤销",
                code="NOT_REVOKABLE",
                errors={},
            )
        reminder_service.delete_reminder(reminder.id)

    row.status = DateCandidateStatus.PENDING
    row.reminder_id = None
    row.confirmed_by_id = None
    row.confirmed_at = None
    row.save(update_fields=["status", "reminder_id", "confirmed_by_id", "confirmed_at", "updated_at"])
    refresh_task_confirmation_status(task)

    logger.info("日期候选已撤销: task_id=%s, candidate_id=%s", task_id, candidate_id)
    return {
        "candidate_id": candidate_id,
        "status": "pending",
        "reminder_id": None,
        "message": "已撤销并删除提醒",
        "error_code": None,
    }
