"""日期候选服务

职责链：提取合并（LLM key_events + 正则候选）→ 落库为候选行 →
律师人工确认后写入重要日期提醒 → 撤销。

设计要点（评审定稿）：
- 幂等由候选行状态机承担：事务内 ``select_for_update`` 锁行，已 confirmed
  的行直接返回原 reminder_id；**不走** ``upsert_case_log_reminder_internal``
  （它按 case_log+source 定位只取一条，多日期会互相覆盖）。
- 确认写提醒按优先级取关联锚点：``case_log_id`` → ``case_id`` → 独立提醒
  （Reminder 的 contract/case/case_log 最多绑一个）。任务已绑定案件但日志尚未
  落库时挂案件本身，避免产出三字段全空的孤立提醒；两者都无才是独立提醒
  （快捕获场景不强制选案，metadata 带 task 溯源）。
- 存量自动写入的旧提醒无 metadata.source：确认前按
  ``(case_log_id, due_at)`` 查重复用，避免同一时间出现双提醒。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
from apps.reminders.models import ReminderType

from ._datetime_extraction_mixin import DatetimeExtractionMixin
from .data_classes import DocumentType
from .date_candidate_policy import DERIVATION_LABELS
from .date_candidate_policy import EFFECTIVE_FIRST_NOTE as _policy_effective_first_note
from .date_candidate_policy import (
    FLAG_ANCHOR_FOREIGN_LLM,
    FLAG_DUPLICATE,
    FLAG_GENERIC_BOILERPLATE,
    AnchorDocument,
    AnchorKind,
    AnchorVerdict,
    CandidateDecision,
    DocumentRole,
    anchor_note_for,
    classify_document_role,
    confidence_for,
    decide_candidate,
    extract_period_length_verdict,
)
from .date_candidate_policy import find_issue_date as _policy_find_issue_date
from .date_candidate_policy import (
    is_optional_motion,
    parse_anchor_clause,
    party_role_verdict,
    period_length_anchor,
    period_length_event_type,
)

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

# 判决书 / 调解书里**只记救济期限**（上诉期、复议期），不记判项给付义务。
#
# 口径（业务确认 2026-11-14）：
#   - 判项写「被告于本判决发生法律效力之日起十日内支付 XX 元」——这是**当事人的**
#     履行义务，律师不需要在日历上跟进；
#   - 判决书正文引述的**合同条款**（「《采购单》约定货到 3 日内付款」）同理，一律不记；
#   - 判决书/调解书里律师真正要跟的是**上诉期**（未上诉则判决生效，影响后续一切）。
#
# 唯独例外：如果判项里出现「向**本院**缴纳」（诉讼费由法院收），那是要跟进的缴费，
# 不属于当事人之间的给付，保留。
_JUDGMENT_TITLE_RE = re.compile(r"(?:民事|刑事|行政)?(?:判决书|调解书)")
# 判项给付义务 / 合同条款的典型锚点（当事人之间，判决书里一律不记）：
#   - 判项：「本判决发生法律效力之日起十日内支付」；
#   - 合同：「《采购单》约定货到 3 日内付款」「合同约定…日内交付」。
_PAYMENT_ORDER_RE = re.compile(
    r"(?:发生法律效力|判决生效|调解书生效|本判决|本调解书"
    r"|合同约定|约定|协议约定|《[^》]{1,20}》[^。；]{0,20}约定)"
)
_REFUSAL_KEEP_RE = re.compile(r"向本院(?:缴纳|交纳|支付|退回)")

# 超出这个天数的「未来日期」视为长期约定（房贷 30 年到期日 / 土地租期等），降置信不默认勾选。
# 法院文书里真正要跟进的人工期限（上诉/举证/保全/缴费）几乎不会超过 10 年。
FAR_FUTURE_DAYS = 365 * 10

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

# 起算点是「判决/裁定发生法律效力之日」而非送达/收到之日：**保留候选，但标注待确认**。
#
# 口径（2026-11-14 业务定调）：缴费期限这类履行期限**要记**——律师确实要跟进。
# 但它的起算点是「判决生效之日」，而生效日取决于对方是否上诉（送达后 15 日内无人
# 上诉才生效），这件事只有书记员能确认。直接按「送达 + N 天」算会给出一个看似精确、
# 实则可能早半个月的假日期，因此：
#
#   - 候选**照常保留并进入确认列表**（律师看得到，不会漏）；
#   - 日期给「送达日 + N 天」作为**最早可能日**（保守，只会提前提醒）；
#   - 附一句起算点说明，提示律师与书记员确认生效日后自行改期。
#
# 即：宁可给一个明确标注「待确认起算点」的保守日期，也不默默丢弃律师需要的期限。
_EFFECTIVE_FIRST_RE = re.compile(r"(?:发生法律效力|生效|确定法律效力)")

# 起算点提示文案的单一来源在 date_candidate_policy（前后端都不各写一份）
EFFECTIVE_FIRST_NOTE = _policy_effective_first_note

# 相对期限的事件类型：按动作动词判（「保全费…交纳」须判 payment 而非被名词「保全」带偏）
# 顺序有讲究：先匹配到的赢，所以「上诉」必须排在「申请」之前
# （"如不服本判决…十五日内上诉" 是上诉期；"如不服本裁定…五日内申请复议" 是复议期）。
_RELATIVE_EVENT_TYPES: list[tuple[str, tuple[str, ...]]] = [
    ("payment_deadline", ("交纳", "缴纳", "缴款", "缴费", "付款", "支付", "付清")),
    ("appeal_deadline", ("上诉",)),
    # 「提交证据材料 / 证据目录」也是举证期限的标准写法；只列「举证」会让这类句子
    # 落成 other，而 other 一旦过期就会被"纯历史过滤"删掉，律师连"举证期已过"都看不到。
    ("evidence_deadline", ("举证", "提交证据", "证据材料", "证据目录")),
    # 「复议」是裁定书特有的救济期限（如「自收到裁定书之日起五日内申请复议」）。
    # ReminderType 没有复议类，归到 submission_deadline（向法院提交/申请的期限）。
    # 缺这条会落到 other → 过期后被「纯历史过滤」删掉，律师就完全看不到
    # 「复议期已过」这个事实（2026-11-14 全量扫描 119 份 PDF 发现）。
    ("submission_deadline", ("复议", "申请", "补正", "提交材料", "递交材料", "提出异议")),
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
    """文书签发/落款日期（口径入口，实现已下沉到 ``date_candidate_policy``）。

    保留本函数名是因为既有单测与调用方都用它；真正的实现在 policy 模块里，
    与「文书角色判定」共用同一份正则，避免两处口径漂移。
    """
    return _policy_find_issue_date(text)


def _has_explicit_year(parsed: datetime, context: str, text: str) -> bool:
    """该候选能否追溯到原文里**带年份**的日期表述（逐候选判断，不看全文有没有年份）。

    拒绝的唯一情形：原文出现了裸「M月D日」，其月/日与候选吻合，且该处**没有年份**，
    同时**整个证据链里找不到带年份的起点**。

    为什么必须逐候选判（2026-11-14 同一份执行裁定书 #285 的教训）：

        本案…依据（20XX）粤0000财保0000号民事裁定书于**2026年9月20日**继续冻结…
        上述继续冻结期限为**一年**。                        ← 有年份，应算出 2027-09-20
        现本案进入执行阶段，依据（20XX）粤0000执保0000号…于**3月26日**冻结了…
        上述账户冻结期限为**一年**。                          ← 无年份，不能猜 2026-03-26

    同一份文书里两种情况并存。先前用「全文有没有年份」做兜底，把上面那条**合法**的
    保全到期日也一起删掉了（正确结果被误杀），正是这个错误的直接后果。

    合法推算的判定（a→b）：候选日期 C 能由某个带年份的原文日期 A 通过「一年/N日」
    等确定性运算得到（这里用「A 与 C 相差整年/整月/整日，且 A 在原文明文出现」，
    以及「A 与 C 同日不同年」两种形态覆盖实务必场景）。
    """
    y, m, d = parsed.year, parsed.month, parsed.day
    anchors = (context or "", text or "")

    # 1) 候选自身带年份 → 确信
    for hay in anchors:
        if not hay:
            continue
        for pattern in (
            rf"{y}\s*年\s*0?{m}\s*月\s*0?{d}\s*日",
            rf"{y}-0?{m}-0?{d}",
            rf"{y}/0?{m}/0?{d}",
        ):
            if re.search(pattern, hay):
                return True

    # 2) 原文有裸「M月D日」且与候选同日 → 看那一处有没有年份
    bare_hit_without_year = False
    for hay in anchors:
        if not hay:
            continue
        for bare in re.finditer(rf"(?<!\d)(\d{{4}}年)?\s*0?{m}\s*月\s*0?{d}\s*日", hay):
            if bare.group(1):
                if int(bare.group(1)[:4]) == y:
                    return True
            else:
                bare_hit_without_year = True
    if bare_hit_without_year:
        # 原文这一处确实没写年份；只有在「能由某个带年份日期推算得出」时才放行
        return _derivable_from_year_anchor(parsed, text or "", context or "")

    # 3) 候选本身就是文书落款/签发日（_find_issue_date 取到的锚点）→ 放行。
    # 落款日是最确定的日期，LLM 把它当一个事件提出来是常见（也常被后续
    # 「相对期限校正」改写成真正的届满日，见 _apply_relative_deadline_rules）。
    # 在这里拦掉它会让整条校正链失去入口。
    issue = _find_issue_date(text or "")
    if issue is not None and issue.date() == parsed.date():
        return True

    # 4) 原文既无该日期的带年份写法、也无裸写法（多半是「N 年内/日后」的推算值）
    return _derivable_from_year_anchor(parsed, text or "", context or "")


def _derivable_from_year_anchor(parsed: datetime, text: str, context: str) -> bool:
    """候选能否由原文中**带年份**的日期按常见期限形态精确推算得出。

    只接受三种可验证的形态（都是法院文书里实际出现的口径）：

    | 形态 | 例子 |
    |:--|:--|
    | 锚 + N 年（保全/查封期限为一年） | `2026年9月20日继续冻结…期限为一年` → 2027-09-20 |
    | 锚 + 整月 | `2026年3月1日…期限六个月` → 2026-09-01 |
    | 锚 + N 日（N ≤ 90，覆盖举证/上诉/缴费等短期期限） | `2026年10月10日…次日起十五日内` → 2026-10-25 |

    刻意**不做**「只要在三年内就放行」这种粗放判断——那等于没判，会让瞎猜的年份
    （如把无年份的「3月26日」补成 2026）照样通过。
    """
    year_dates: list[datetime] = []
    for body in (context, text):
        if not body:
            continue
        # 阿拉伯数字形态（2026年9月20日）
        for m in re.finditer(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", body):
            try:
                year_dates.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
            except ValueError:
                continue
        # 中文数字落款（二〇二五年十一月十一日）：法院文书用中文数字落款比例很高，
        # 漏掉会让「落款日 + N 日」这类合法推算全部被误杀
        for m in re.finditer(
            r"([〇零一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月([一二三四五六七八九十]{1,3})日", body
        ):
            year = _parse_cn_digits(m.group(1))
            month = _cn_to_int(m.group(2))
            day = _cn_to_int(m.group(3))
            if year and month and day:
                try:
                    year_dates.append(datetime(year, month, day))
                except ValueError:
                    continue
    if not year_dates:
        return False

    target = datetime(parsed.year, parsed.month, parsed.day)
    for anchor in year_dates:
        if target <= anchor:
            continue
        # 形态一：+整年（年限为一年的保全/查封到期日）
        if (target.year - anchor.year) in (1, 2, 3) and (target.month, target.day) == (anchor.month, anchor.day):
            return True
        # 形态二：+整月
        months = (target.year - anchor.year) * 12 + (target.month - anchor.month)
        if 0 < months <= 24 and target.day == anchor.day:
            return True
        # 形态三：+N 日（短期期限）
        if 0 < (target - anchor).days <= 90:
            return True
    return False


def _parse_cn_digits(value: str) -> int | None:
    """「二〇二五」→ 2025（四位中文数字年份）。"""
    digits = {ch: i for i, ch in enumerate("〇一二三四五六七八九")}
    if len(value) != 4 or any(ch not in digits for ch in value):
        return None
    return int("".join(str(digits[ch]) for ch in value))


def _cn_to_int(value: str) -> int | None:
    """「十一」→ 11、「三」→ 3、「二十」→ 20（1~31 的月/日）。"""
    digits = {ch: i for i, ch in enumerate("〇一二三四五六七八九")}
    if not value:
        return None
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    if len(value) == 1 and value in digits:
        return digits[value]
    return None


def _is_judgment_document(text: str) -> bool:
    """本文书是不是判决书 / 调解书（按文首标题判，可靠且不依赖 LLM）。

    只看开头 400 字——标题在文首；正文里引用别的判决书不会误判。
    """
    return bool(_JUDGMENT_TITLE_RE.search((text or "")[:400]))


def _is_party_payment_obligation(draft: DateCandidateDraft, text: str) -> bool:
    """判决书/调解书里的这条候选，是否属于「不该记进律师日历」的那类。

    口径（业务确认 2026-11-14）：判决书/调解书里律师**只跟救济期限**。

    **按类型白名单判定**（最不容易漏）：

    | 类型 | 判决书/调解书里 | 理由 |
    |:--|:--|:--|
    | `appeal_deadline` 上诉期 | **保留** | 律师最关心的：不上诉则判决生效 |
    | `submission_deadline` 复议期/提交期限 | **保留** | 裁定书的救济期限（「五日内申请复议」） |
    | `payment_deadline` 缴费 | 剔除**除**「向本院缴纳」 | 判项给付是当事人的义务；调解书分期付款同理；只有诉讼费由法院收，要跟进 |
    | `hearing` 开庭 | **剔除** | 判决书里的开庭日都是**已开过的庭**（「本院于X日公开开庭审理」的历史陈述），不是未来要去的庭 |
    | `asset_preservation_expires` 保全到期 | **保留** | 判决书正文可能载明保全措施与期限，律师要跟进续封 |

    为什么不按话术逐条匹配：实测（2026-11-14）调解书分期付款有「向原告支付」
    「被告定于 X 日前支付」「于 X 日前支付」多套写法，漏一个就漏全部。
    按类型判 + 一个明确例外，既覆盖全又不会误伤救济期限。
    """
    if draft.reminder_type == "hearing":
        # 判决书里的开庭日是历史陈述；未来开庭靠传票/开庭通知，不靠判决书
        return True
    if draft.reminder_type == "payment_deadline":
        return not _REFUSAL_KEEP_RE.search(draft.context_text or "")  # 「向本院缴纳」保留
    if draft.reminder_type == "submission_deadline":
        # 救济期限（复议）保留；明确属于当事人间给付/合同约定的剔除
        context = draft.context_text or ""
        if _REFUSAL_KEEP_RE.search(context):
            return False
        return bool(_PAYMENT_ORDER_RE.search(context) or _PAY_TO_PARTY_RE.search(context))
    return False


# 给付给「对方当事人」而非法院（判决书/调解书里当事人的付款义务）
_PAY_TO_PARTY_RE = re.compile(
    r"(?:向|给)(?:原告|被告|申请人|被申请人|对方|申请执行人|被执行人)[^。；]{0,6}(?:支付|给付|付清|付款|履行)"
)


def _is_effective_first_derived(draft: DateCandidateDraft, text: str) -> bool:
    """候选的起算点是否为「发生法律效力之日」（而非送达日）。

    命中者**不丢弃**——它们往往是律师真正要跟进的缴费/履行期限；只是在确认弹窗里
    加一句「起算点为判决生效之日，请与书记员确认」，避免律师把「送达+10天」当成
    确定日期排期（真实链条是 送达 → 上诉期届满生效 → 再起算 10 日）。

    判据：候选类型是履行类（payment/submission），且原文上下文（或日期附近窗口，
    LLM 常只回截断的 context）含「发生法律效力/生效」。
    """
    if draft.reminder_type not in ("payment_deadline", "submission_deadline"):
        return False
    context = draft.context_text or ""
    if _EFFECTIVE_FIRST_RE.search(context):
        return True
    # LLM 常只回一个截断的 context，回落到「日期附近是否有生效表述」
    needle = draft.due_at.strftime("%Y-%-m-%-d") if draft.due_at else ""
    if needle and needle in text:
        idx = text.find(needle)
        window = text[max(0, idx - 80) : idx + 80]
        return bool(_EFFECTIVE_FIRST_RE.search(window))
    return False


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
        # 锚点必须指向**本**文书：跳过他案引用与商业函件
        if _anchor_points_to_other_matter(sentence, m):
            logger.info("跳过锚点指向他案/函件的相对期限: %s", sentence[:60])
            continue
        results.append((m, days, sent_start, sent_len))
    return results


# 他案/非本院文书的标识：出现在锚点之前时，说明这个「送达/收到之日起 N 日」讲的
# 不是本判决/本裁定的期限，而是正文引述的仲裁裁决、另案判决、商业函件。
_OTHER_MATTER_MARKERS = (
    "仲裁",
    "裁决书",
    "另案",
    "他案",
    "本函",
    "函件",
    "书面通知",
    "告知函",
    "律师函",
    "合同约定",
    "协议约定",
)


def _anchor_points_to_other_matter(sentence: str, match: re.Match[str]) -> bool:
    """该相对期限的锚点是否指向「他案文书/商业函件」而非本文书。

    实测（2026-11-14 全量扫描 119 份 PDF）两类误判：

    1. 判决书正文**引述**仲裁裁决：
       「某仲裁委员会…作出（20XX）某仲裁字第0000号**仲裁裁决书**，裁决：一、某公司于
        本**裁决书**送达之日起十日内向某公司支付检测费…」
       —— 这是别人的裁决义务，本判决实际是「驳回原告诉讼请求」，无任何缴费义务。
       旧逻辑用本判决落款日当锚，凭空造出一条「11-07 前交检测费」的假期限。

    2. 证据材料里引述**商业函件**：
       「…公司在收到本函之日起十个工作日内…」「自收到原告的书面通知之日起…」
       —— 公司法查阅权纠纷的商业往来，不是法院指定的期限。

    判据：锚点之前的紧邻文本里出现他案/函件标识词。本判决自己的期限写的是
    「如不服本判决，可在**判决书送达之日起**…」，前面不含这些标识。
    """
    # 锚点前后都要看：标识词可能在前（「…仲裁裁决书，裁决：一、…于本裁决书送达之日起」）
    # 也可能在后（「收到本函之日起十五日内作出书面答复」里「本函」就在锚点中间）。
    # 仍限制在同一句内（sentence 已按句切分），不会跨句误伤本判决自己的期限。
    window = sentence[max(0, match.start() - 80) : match.end() + 40]
    return any(marker in window for marker in _OTHER_MATTER_MARKERS)


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


def _self_title_keywords(text: str) -> tuple[str, ...]:
    """从文首标题里取本文书自身的文书类型名（判决书/裁定书/调解书/…）。

    用途：锚点归属判定里区分「收到裁定书之日起五日内申请复议」（本份裁定）
    与「裁判文书送达之日起三日内」（尚未产生的那份）。
    """
    from .date_candidate_policy import CARRIER_TITLE_KEYWORDS

    # 只看真正的标题区（文首 24 字，且不含书名号内的内容）：
    # 若扫整段文首，正文里「应自收到《…交费通知书》」会把别份文书的名字
    # 误当成"本文书类型名"，反而把本该丢弃的外来锚点判成自指（实测踩到）。
    head = re.sub(r"\s+", "", (text or "")[:24])
    head = head.split("《", 1)[0]
    return tuple(kw for kw in CARRIER_TITLE_KEYWORDS if kw in head)


def _suppress(
    bucket: list[dict[str, Any]] | None,
    *,
    deadline: datetime,
    event_type: str,
    context: str,
    verdict: AnchorVerdict | None,
    reason: str,
) -> None:
    """把被闸门丢弃的候选记入留痕桶（落库到 task.suppressed_candidates）。

    为什么不硬删：律师问「这份文书里写了期限，为什么没提醒我」时必须答得出；
    后续调参也需要回放。每项只留最小可核查事实：日期、类型、原因、原文片段。
    """
    if bucket is None:
        return
    bucket.append(
        {
            "due_at": deadline.date().isoformat(),
            "reminder_type": event_type,
            "anchor_document": verdict.document.value if verdict else "",
            "anchor_kind": verdict.kind.value if verdict else "",
            "reason": reason,
            "context_text": context[:255],
        }
    )


def _apply_relative_deadline_rules(
    text: str,
    drafts: list[DateCandidateDraft],
    *,
    delivery_date: datetime | None = None,
    role: DocumentRole = DocumentRole.CARRIER,
    sibling_documents: Sequence[str] = (),
    self_titles: Sequence[str] = (),
    suppressed: list[dict[str, Any]] | None = None,
) -> list[DateCandidateDraft]:
    """相对期限推算（确定性规则，不依赖 LLM）。

    「保全费请你方于收到本通知次日起两日内向本院交纳」这类表述不含日期，
    LLM 常就近把落款日当事件日。按「起算当日不计入、自次日起算」推算届满日
    = 锚 + N 天（「次日起两日内」：次日为第 1 天 → 锚 + 2；
    「（之）日起七日内」→ 锚 + 7）。

    **锚点（重要，法律口径）**：

    「如不服本判决，可以在判决书**送达之日起**十五日内上诉」的起算点是**送达日**，
    不是落款日。法院文书落款日普遍早于实际送达（打印/用印/邮寄需要时间），
    用落款日当锚会把届满日算得**过早**，律师按这个日期排期会误以为
    「还剩几天」而实际已过期，或反之白抢时间。

    本系统里 **`CourtSMS.received_at` 就是送达日**（法院短信转发到你手机的
    时刻即收到日；收发双方均按此口径运营），因此管线模式（法院短信入口）
    传入 `delivery_date` 时优先用它；拿不到（记一笔独立上传 / 转发队列延迟）
    才回落落款日——宁可给一个早一点的保守估计，也不凭空编一个日期。

    认领分三轮，避免多期限句互相争抢同一条候选（context 精确匹配优先于
    指纹兜底）：1) 原文表述出现在候选 context → 校正该候选；2) 未认领事件
    按「同类型且日期=锚日」指纹认领；3) 仍未认领（LLM 漏提）→ 补正则候选。

    **三道前置闸门（2026-11-24 事故根治，口径见 date_candidate_policy）**：

    进到这里之前，每一句「收到/送达 X 之日起 N 日内」必须先过：
    1) 锚点归属：X 必须指向**本文书**。指向尚未产生的裁判文书、同批另一份
       文书或他案函件的，一律丢弃——「告知书」里「至迟应在裁判文书送达之日起
       三日内提出」曾被按「收到告知书 + 3 天」编成一个日期，而那份裁判文书
       根本还没产生；
    2) 选择性申请：申请不予公布/延期/证人出庭/鉴定/取证/回避这类「想做才做」
       的条款不进日历（业务口径 2026-11-24）；
    3) 文书角色：通用告知/须知类文书上的相对期限属于通则说明，不是本案期限。
    被丢弃的记入 ``suppressed`` 留痕，不静默消失。
    """
    if not text:
        return drafts

    if delivery_date is not None:
        anchor = datetime.combine(delivery_date.date(), datetime.min.time())
        anchor_kind = AnchorKind.SERVICE_OF_SELF
    else:
        issue = _find_issue_date(text)
        anchor = issue
        anchor_kind = AnchorKind.ISSUE_DATE_OF_SELF
    if anchor is None:
        return drafts

    events: list[dict[str, Any]] = []
    for m, days, sent_start, sent_len in _iter_relative_deadlines(text):
        # 取窗不越过句边界：相邻句的期限动词（如前句的「交纳」）不得污染本句类型判断
        ctx_from = max(sent_start, sent_start + m.start() - 20)
        ctx_to = min(sent_start + sent_len, sent_start + m.end() + 25)
        context = text[ctx_from:ctx_to].strip()
        deadline = anchor + timedelta(days=days)
        event_type = _relative_event_type(context)
        sentence = text[sent_start : sent_start + sent_len]

        # ① 选择性申请类：想做才做的事，法院没给本案指定期限
        optional, optional_reason = is_optional_motion(context)
        if optional:
            logger.info("丢弃选择性申请类期限: %s | %s", deadline.date(), optional_reason)
            _suppress(
                suppressed,
                deadline=deadline,
                event_type=event_type,
                context=context,
                verdict=None,
                reason=optional_reason,
            )
            continue

        # ② 锚点归属：期限句讲的到底是哪一份文书
        verdict = parse_anchor_clause(
            sentence=sentence,
            match_start=m.start(),
            match_end=m.end(),
            sibling_documents=sibling_documents,
            self_titles=self_titles,
        )
        if verdict.document is not AnchorDocument.SELF:
            logger.info(
                "丢弃非自指锚点的期限: %s | 锚=%s | %s",
                deadline.date(),
                verdict.document.value,
                verdict.reason,
            )
            _suppress(
                suppressed,
                deadline=deadline,
                event_type=event_type,
                context=context,
                verdict=verdict,
                reason=verdict.reason or "锚点不在本份文书上",
            )
            continue

        # ③ 文书角色：通用告知类文书里的相对期限是通则说明
        if role is DocumentRole.GENERIC_NOTICE:
            logger.info("丢弃通用告知类文书上的相对期限: %s | %s", deadline.date(), context[:40])
            _suppress(
                suppressed,
                deadline=deadline,
                event_type=event_type,
                context=context,
                verdict=verdict,
                reason="通用告知类文书里的相对期限属于通则说明，不是本案期限",
            )
            continue

        events.append(
            {
                "core": m.group(0)[:18],
                "days": days,
                "deadline": deadline,
                "context": context,
                "event_type": event_type,
                "verdict": verdict,
                "anchor_kind": verdict.kind if verdict.kind is not AnchorKind.UNKNOWN else anchor_kind,
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
        # 被确定性规则校正/认领过的候选：出处字段一律以规则层为准。
        # ``source`` 保持原值（llm/regex/merged）不动——它表达"这条最初从哪来"，
        # 而"日期是怎么算出来的"由 ``derivation`` 表达，两者不要混在一起。
        draft.derivation = "rule_relative"
        draft.anchor_kind = event["anchor_kind"].value
        draft.anchor_document = event["verdict"].document.value
        draft.anchor_at = anchor.date()
        draft.confidence = confidence_for(
            derivation="rule_relative", anchor=event["verdict"], role=role, raw=max(draft.confidence, 0.9)
        )
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
                confidence=confidence_for(derivation="rule_relative", anchor=event["verdict"], role=role, raw=0.9),
                anchor_kind=event["anchor_kind"].value,
                anchor_at=anchor.date(),
                anchor_document=event["verdict"].document.value,
                derivation="rule_relative",
                anchor_note=anchor_note_for(
                    kind=event["anchor_kind"],
                    anchor_at=anchor.date(),
                    delivery_date=delivery_date.date() if delivery_date else None,
                    days=event["days"],
                ),
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
    """合并后的日期候选（落库前的内存形态）。

    ``anchor_*`` / ``derivation`` / ``review_flags`` 是「候选的出处」：这条日期
    依据哪份文书、起算锚是什么、怎么算出来的、要不要人工看。2026-11-24 的事故
    就是因为只有 ``confidence`` 一个数字，无法区分「规则算出来的」与「原文写明的」。
    """

    due_at: datetime
    reminder_type: str
    context_text: str
    source: str  # llm | regex | merged
    confidence: float
    # 起算点人话说明（如「起算点：本份文书送达日 2026-11-24 + 7 天」）。
    anchor_note: str = ""
    # 出处字段（取值域见 date_candidate_policy）
    anchor_kind: str = ""
    anchor_at: date | None = None
    anchor_document: str = ""
    derivation: str = ""
    review_flags: tuple[str, ...] = ()
    default_checked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "due_at": self.due_at.isoformat(),
            "reminder_type": self.reminder_type,
            "context_text": self.context_text,
            "source": self.source,
            "confidence": self.confidence,
            "anchor_note": self.anchor_note,
            "anchor_kind": self.anchor_kind,
            "anchor_at": self.anchor_at.isoformat() if self.anchor_at else None,
            "anchor_document": self.anchor_document,
            "derivation": self.derivation,
            "review_flags": list(self.review_flags),
            "default_checked": self.default_checked,
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


def _verdict_from_draft(draft: DateCandidateDraft) -> AnchorVerdict:
    """从草稿的出处字段还原 AnchorVerdict（供统一裁决）。

    明文绝对日期（llm_absolute / rule_absolute）本来就没有起算锚，
    ``anchor_kind`` 留空 → 归为 UNKNOWN；这不会导致丢弃，因为丢弃只看
    ``anchor_document`` 与「通用文书 + 规则推算」两个条件。
    """
    try:
        document = AnchorDocument(draft.anchor_document or AnchorDocument.SELF.value)
    except ValueError:
        document = AnchorDocument.OTHER_CASE
    try:
        kind = AnchorKind(draft.anchor_kind) if draft.anchor_kind else AnchorKind.UNKNOWN
    except ValueError:
        kind = AnchorKind.UNKNOWN
    return AnchorVerdict(document=document, kind=kind, reason="")


def build_date_candidates(
    text: str,
    analysis: Any | None,
    document_type: DocumentType,
    *,
    regex_extractor: Any | None = None,
    received_at: datetime | None = None,
    sibling_documents: Sequence[str] | None = None,
    our_party_roles: Sequence[str] | None = None,
    suppressed_out: list[dict[str, Any]] | None = None,
) -> list[DateCandidateDraft]:
    """合并 LLM key_events 与正则候选为去重后的候选列表。

    去重键 = (日期时间, 提醒类型)：同值 LLM 优先（source 升级为 merged、
    置信度取 max）；同日不同类型都保留（开庭日与举证截止同日是真实场景）。

    Args:
        received_at: 文书送达/收到时间（法院短信的 ``CourtSMS.received_at``）。
            传入时作为「送达之日起 N 日」类期限的起算锚点（见
            ``_apply_relative_deadline_rules``）；None 则回落到落款日。
        sibling_documents: 同一条短信/同批次的其他文书显示名。用来把
            「应自收到《缴费通知书》之日起七日内」判成"期限归属另一份文书"（丢弃）。
        our_party_roles: 我方在该案的诉讼地位（``CaseParty.legal_status``，只取
            ``Client.is_our_client=True`` 的当事人）。用于「举证期限只在我方是
            被告/被申请人/被上诉人/第三人时才需要跟」这条业务口径；None 表示
            拿不到地位 → 保留候选但标 ``party_role_unknown``、不默认勾。
        suppressed_out: 出参：被闸门丢弃的候选会追加到这里，调用方落库到
            ``task.suppressed_candidates`` 留痕（律师问「为什么没提醒」时能答）。
            用出参而不是改返回值，是为了不打断既有的 list 返回约定与全部现有单测。
    """
    extractor = regex_extractor or _RegexCandidateExtractor()
    default_type = DEFAULT_TYPE_BY_DOCUMENT_TYPE.get(document_type, "other")
    siblings = tuple(sibling_documents or ())
    # 本文书自己的类型名（如「裁定书」）：复议期句子里写的是「收到裁定书之日起五日内」，
    # 指的是本份裁定而非别份，必须让锚点判定知道这件事。
    self_titles = _self_title_keywords(text)
    # 文书角色：这份文书到底承不承载本案期限（内容判据，不看文件名）
    role, role_reason = classify_document_role(text=text)
    logger.info("文书角色判定: %s | %s", role.value, role_reason)

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
        # 无年份日期不采纳：原文若只写「3月26日」，LLM 会按文档里出现的年份自行补全，
        # 猜错一年就让律师跟进错期限（2026-11-14 实测执行裁定书「3月26日冻结一年」
        # 被补成 2026-03-26，算出的到期日提前了整整一年）。宁可少一条，
        # 也不给一个看上去确定、实际可能差一年的假日期。
        if not _has_explicit_year(parsed, context, text):
            logger.warning(
                "跳过无年份的 LLM 日期事件（不猜年份）: %s | context=%s",
                getattr(event, "datetime", None),
                context[:40],
            )
            continue
        # LLM 自报的起算锚归属（anchor_hint）：它说锚在别处（尚未产生的裁判文书/
        # 另一份具名文书）时，本条就是不可算的——直接丢弃并留痕，不信它的日期。
        anchor_hint = str(getattr(event, "anchor_hint", "self") or "self")
        # LLM 说「锚在别份文书」时不直接采信它的日期，但也不直接丢：
        # 模型标错一次的代价是漏掉真期限（如把「本份执行通知书」标成 other_document）。
        # 保留草稿 + 打 flag + 不默认勾，把「到底是不是别份文书的期限」交回确定性层
        # 与律师本人判断（详见 date_candidate_policy 的设计原则 P1/P5）。
        llm_foreign_anchor = anchor_hint in ("future_document", "other_document")
        if llm_foreign_anchor:
            logger.info("LLM 判定锚点在别份文书（%s），保留为待核对候选: %s", anchor_hint, parsed.date())
        drafts[(parsed, event_type)] = DateCandidateDraft(
            due_at=parsed,
            reminder_type=event_type,
            context_text=context,
            source="llm",
            confidence=float(getattr(event, "confidence", 0.7) or 0.7),
            derivation="llm_absolute",
            anchor_document="self",
            anchor_kind=AnchorKind.EFFECTIVE_DATE.value if anchor_hint == "effective" else "",
            review_flags=(FLAG_ANCHOR_FOREIGN_LLM,) if llm_foreign_anchor else (),
        )

    # 2. 正则候选（透出全部，含上下文与类型推断）
    def _merge_regex_candidate(candidate: dict[str, Any]) -> None:
        """把一条正则候选并入草稿表（同日期同类型去重、LLM 优先）。"""
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
                derivation="rule_absolute",
                anchor_document="self",
            )
        else:
            existing.source = "merged"
            existing.confidence = max(existing.confidence, regex_confidence)
            if not existing.context_text:
                existing.context_text = str(candidate.get("context_text", ""))[:255]

    for candidate in extractor.extract_datetime_candidates(text):
        _merge_regex_candidate(candidate)

    # 2.5 纯日期（无时刻）兜底：DATETIME_PATTERNS 全部要求时刻，
    #     「本案举证期限至 2027-01-10 止」这类只有 LLM 能抓；LLM 熔断时就全空。
    #     门槛由 mixin 内的"上下文必须命中期限词"保证，不会成片抓叙事日期。
    for candidate in extractor.extract_date_only_candidates(text):
        _merge_regex_candidate(candidate)

    # 3. 期间结构后处理：起始日剔除、到期日算术校正、相对期限推算、同上下文去重
    drafts_list = _apply_period_rules(text, list(drafts.values()))
    for draft in drafts_list:
        if not draft.derivation:
            draft.derivation = "rule_period"
        if not draft.anchor_document:
            draft.anchor_document = "self"
    # 3.2 期间长度（「举证期限为十五日」）：与「…之日起 N 日内」是两种写法，
    #     前者是法院给本案**指定**的期限长度，必须能算；但法定下限/多档程序不算。
    period_verdict = extract_period_length_verdict(text)
    period_context = period_length_anchor(text) or period_verdict.matched_text
    period_type = period_length_event_type(text)
    anchor_day = received_at.date() if received_at else None
    if anchor_day is None:
        issue = _find_issue_date(text)
        anchor_day = issue.date() if issue else None
    if period_verdict.stated_days is not None and not period_verdict.reason and anchor_day is not None:
        period_due = datetime.combine(anchor_day, datetime.min.time()) + timedelta(days=period_verdict.stated_days)
        drafts_list.append(
            DateCandidateDraft(
                due_at=period_due,
                reminder_type=period_type,
                context_text=(period_context or period_verdict.matched_text)[:255],
                source="regex",
                confidence=0.9,
                anchor_kind=AnchorKind.SERVICE_OF_SELF.value if received_at else AnchorKind.ISSUE_DATE_OF_SELF.value,
                anchor_at=anchor_day,
                anchor_document=AnchorDocument.SELF.value,
                derivation="rule_period",
                anchor_note=anchor_note_for(
                    kind=AnchorKind.SERVICE_OF_SELF if received_at else AnchorKind.ISSUE_DATE_OF_SELF,
                    anchor_at=anchor_day,
                    delivery_date=anchor_day,
                    days=period_verdict.stated_days,
                ),
            )
        )
        logger.info("期间长度推算候选: 届满=%s (%s + %d天)", period_due.date(), anchor_day, period_verdict.stated_days)
    elif period_verdict.reason:
        # 算不出来的要留痕：多档程序 / 法定下限 / 无起算点，都可能在律师追问时被问到
        _suppress(
            suppressed_out,
            deadline=datetime.combine(anchor_day or timezone.localdate(), datetime.min.time()),
            event_type=period_type,
            context=period_context or period_verdict.matched_text,
            verdict=None,
            reason=period_verdict.reason,
        )

    drafts_list = _apply_relative_deadline_rules(
        text,
        drafts_list,
        delivery_date=received_at,
        role=role,
        sibling_documents=siblings,
        self_titles=self_titles,
        suppressed=suppressed_out,
    )

    # 4. 陈旧候选降置信（改判文书可能含历史日期，折叠而非丢弃）
    today = timezone.localdate()
    for draft in drafts_list:
        if (today - draft.due_at.date()).days > STALE_DAYS:
            draft.confidence = min(draft.confidence, 0.3)

    # 4.4 剔除纯历史事实日期：律师要记的是**尚未到来的期限**。
    #
    # 判决书/裁定书正文密集出现已发生的日期：立案日、签约日、对账日、落款日……
    # 它们不是“关键日期”，只是叙事时间线，放进日历没有意义而且会混淆真正的期限。
    # 因此：**已过去且类型为 other** 的候选直接丢弃（不返回、不落库）。
    # 保留例外：
    #   - 未来日期（哪怕类型是 other，也可能是尚未归类的期限）；
    #   - 己过期但类型明确的候选（如上诉期已过、保全到期已过）——
    #     律师需要知道“这个已经过了”，审计/追责时用得上，不能默默隐藏。
    # 保留两个兜底：
    #   a) 已过期 + other → 叙事时间线，丢弃；
    #   b) 超过 FAR_FUTURE_DAYS 的 far-future 日期（>10 年）→ 降置信到 0.3 且标 other，
    #      这类多是别处的长期约定（房贷 30 年到期日、土地租期）被当成本文书期限。
    #      实测（2026-11-14 全量扫描）：一份银行贷款合同给出 2051-04-25。
    #      不直接删——如果律师真的要跟进，行还在，只是不默认勾选。
    kept: list[DateCandidateDraft] = []
    for draft in drafts_list:
        past = draft.due_at.date() < today
        if past and draft.reminder_type == "other":
            continue
        if (draft.due_at.date() - today).days > FAR_FUTURE_DAYS:
            draft.confidence = min(draft.confidence, 0.3)
        kept.append(draft)
    drafts_list = kept

    # 4.55 判决书 / 调解书：只保留救济期限（上诉期、复议期），剔除判项给付义务
    # 与正文引述的合同条款付款期（业务口径：那是当事人自己的事，与律师日历无关）。
    if _is_judgment_document(text):
        before = len(drafts_list)
        drafts_list = [d for d in drafts_list if not _is_party_payment_obligation(d, text)]
        if len(drafts_list) != before:
            logger.info(
                "判决书/调解书剔除当事人给付义务期限: %d → %d 条",
                before,
                len(drafts_list),
            )

    # 4.6 标注「生效之日起算」的履行期限（不丢弃，见 _EFFECTIVE_FIRST_RE 注释）
    #
    # 旧实现把置信度压到**恰好 0.5**，而前端阈值是「>= 0.5 就默认勾」——
    # 「降一档、默认不勾」的意图反向失效（2026-11-24 审计发现）。现在改成
    # 只打锚点标记，由下面的 decide_candidate 统一下调置信度并挂 flag，
    # 默认勾选只看 flags，不再有压线边界。
    for draft in drafts_list:
        if draft.anchor_kind == AnchorKind.EFFECTIVE_DATE.value or _is_effective_first_derived(draft, text):
            draft.anchor_kind = AnchorKind.EFFECTIVE_DATE.value
            draft.anchor_note = EFFECTIVE_FIRST_NOTE

    # 4.7 逐条裁决：该留还是该丢、带哪些复核标记、能不能默认勾。
    # 这里是「provenance 策略」的唯一出口，前端不再按裸分数自己判断。
    decided: list[DateCandidateDraft] = []
    for draft in drafts_list:
        verdict = _verdict_from_draft(draft)
        confidence = confidence_for(
            derivation=draft.derivation or "llm_absolute",
            anchor=verdict,
            role=role,
            raw=draft.confidence,
        )
        party_role_ok, party_role_reason = party_role_verdict(our_party_roles, draft.context_text)
        decision = decide_candidate(
            derivation=draft.derivation or "llm_absolute",
            anchor=verdict,
            role=role,
            confidence=confidence,
            due_at=draft.due_at,
            today=today,
            party_role_ok=party_role_ok,
        )
        if party_role_ok is False:
            decision = CandidateDecision(
                keep=False,
                flags=decision.flags,
                confidence=decision.confidence,
                default_checked=False,
                reason=party_role_reason,
            )
        if not decision.keep:
            logger.info(
                "丢弃候选: %s %s | %s",
                draft.due_at.date(),
                draft.reminder_type,
                decision.reason,
            )
            _suppress(
                suppressed_out,
                deadline=draft.due_at,
                event_type=draft.reminder_type,
                context=draft.context_text,
                verdict=verdict,
                reason=decision.reason,
            )
            continue
        merged_flags: list[str] = list(draft.review_flags)
        for flag in decision.flags:
            if flag not in merged_flags:
                merged_flags.append(flag)
        draft.review_flags = tuple(merged_flags)
        draft.confidence = decision.confidence
        if merged_flags and draft.default_checked:
            draft.default_checked = False
        draft.default_checked = decision.default_checked
        if not draft.anchor_document:
            draft.anchor_document = AnchorDocument.SELF.value
        decided.append(draft)
    drafts_list = decided

    # 5. 名额分配：**未过期候选优先占 MAX_CANDIDATES 名额**。
    # 判决书正文里密布已发生的事实日期（立案/签约/对账/落款），它们不是“提醒”，
    # 却会把真正的期限（如末页的上诉期）挤出名额——实测 7 页判决书里
    # 6 条历史日期与 2 条真期限同为候选，旧逻辑靠类型优先级勉强不死，
    # 一旦历史日期被 LLM 归成 hearing/payment_deadline 就会顶掉真期限。
    # 过期候选仍然保留（折叠到最后，律师仍可看到并手动勾选），只是不占前排。
    ordered = sorted(
        drafts_list,
        key=lambda d: (
            0 if d.due_at.date() >= today else 1,  # 未过期在前
            REMINDER_TYPE_PRIORITY.get(d.reminder_type, 99),
            -d.confidence,
            d.due_at,
        ),
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
            anchor_kind=draft.anchor_kind,
            anchor_at=draft.anchor_at,
            anchor_document=draft.anchor_document,
            derivation=draft.derivation,
            review_flags=list(draft.review_flags),
            default_checked=draft.default_checked,
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


#: 推算方式的权威度（越小越权威）：LLM 读到的原文日期 > 正则明文日期 > 相对期限推算 > 期间推算
_DERIVATION_AUTHORITY: dict[str, int] = {
    "llm_absolute": 0,
    "rule_absolute": 1,
    "rule_relative": 2,
    "rule_period": 3,
}


def reconcile_source_candidates(source_court_sms_id: int) -> int:
    """批内去重：一条法院短信的多份文书常报出同一天同一类型的期限。

    真实场景（2026-11-24）：《诉讼费退费缴费须知》与《诉讼费用交费通知书》
    都指向「12-01 前交受理费」——须知里的那句只是复述交费通知书的规则，
    真期限由交费通知书自己报。两条都留在确认弹窗里，律师无法判断该勾哪一条。

    口径（业务 2026-11-24 拍板）：
    - **只收敛"完全相同键"**：同一案件 + 同一天 + 同一提醒类型；
    - **同类型但日期不同、同日不同类型一律都留**——不做冲突裁决，因为
      冲突本身（两份文书各说一个日期）就是律师必须立刻知道的信息；
    - 权威度排序：非通用文书 > 通用文书；llm_absolute > rule_absolute >
      rule_relative > rule_period；同类取 context 更长者；再不行取小 id。

    幂等：只动 ``pending`` 行，已确认/已忽略的一律不碰；可反复调用。

    Returns:
        本次被折叠掉的行数。
    """
    from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionTask

    tasks = list(
        DocumentRecognitionTask.objects.filter(source_court_sms_id=source_court_sms_id).prefetch_related(
            "date_candidates"
        )
    )
    if not tasks:
        return 0

    # 复活孤儿：被折叠过的行若权威行已被删（duplicate_of SET_NULL），它不该永远消失
    for task in tasks:
        for row in task.date_candidates.all():
            if (
                row.status == DateCandidateStatus.SKIPPED
                and row.duplicate_of_id is None
                and FLAG_DUPLICATE in (row.review_flags or [])
            ):
                row.status = DateCandidateStatus.PENDING
                row.review_flags = [f for f in (row.review_flags or []) if f != FLAG_DUPLICATE]
                row.save(update_fields=["status", "review_flags", "updated_at"])
                logger.info("恢复孤儿候选: candidate=%s（权威行已不存在）", row.id)

    groups: dict[tuple[Any, Any, str], list[tuple[Any, Any]]] = {}
    for task in tasks:
        for row in task.date_candidates.all():
            if row.status != DateCandidateStatus.PENDING or row.duplicate_of_id:
                continue
            key = (task.case_id, row.due_at.date(), row.reminder_type)
            groups.setdefault(key, []).append((task, row))

    folded = 0
    touched: set[int] = set()
    for items in groups.values():
        if len(items) < 2:
            continue
        # 只折**跨任务**的重复：同一份文书里两条同类型同日期（如交费通知书把受理费与
        # 保全费都写成"七日内"）是两条不同的义务，折掉一条就等于漏一条。
        task_ids = {task.id for task, _row in items}
        if len(task_ids) < 2:
            continue
        items.sort(
            key=lambda pair: (
                1 if FLAG_GENERIC_BOILERPLATE in (pair[1].review_flags or []) else 0,
                _DERIVATION_AUTHORITY.get(pair[1].derivation, 9),
                -len(pair[1].context_text or ""),
                pair[1].id,
            )
        )
        winner_task, winner = items[0]
        for task, row in items[1:]:
            row.duplicate_of = winner
            row.status = DateCandidateStatus.SKIPPED
            flags = list(row.review_flags or [])
            if FLAG_DUPLICATE not in flags:
                flags.append(FLAG_DUPLICATE)
            row.review_flags = flags
            row.default_checked = False
            row.save(update_fields=["duplicate_of", "status", "review_flags", "default_checked", "updated_at"])
            folded += 1
            touched.add(task.id)
            logger.info(
                "批内去重折叠: task=%s candidate=%s (%s) → 权威 candidate=%s (task=%s)",
                task.id,
                row.id,
                row.due_at.date(),
                winner.id,
                winner_task.id,
            )

    for task in tasks:
        if task.id in touched:
            refresh_task_confirmation_status(task)
    return folded


def list_candidates(task: Any) -> list[dict[str, Any]]:
    """候选行序列化（API/admin 共用）。

    除了日期与类型，必须把**出处**一并透出：律师要靠「来源 + 起算点」判断
    这条日期靠不靠得住；旧实现算好了 anchor_note 却在落库前丢掉，前端从来没显示过。
    """
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
            "anchor_kind": row.anchor_kind,
            "anchor_at": row.anchor_at.isoformat() if row.anchor_at else None,
            "anchor_document": row.anchor_document,
            "derivation": row.derivation,
            "derivation_label": DERIVATION_LABELS.get(row.derivation, ""),
            "review_flags": list(row.review_flags or []),
            "default_checked": bool(row.default_checked),
            "anchor_note": _anchor_note_for_row(row),
            "duplicate_of_id": row.duplicate_of_id,
        }
        for row in task.date_candidates.select_related("reminder").order_by("due_at", "id")
    ]


def _anchor_note_for_row(row: Any) -> str:
    """按行上存的锚类型即时渲染「起算点」文案（不在库里存冗余文案）。"""
    try:
        kind = AnchorKind(row.anchor_kind) if row.anchor_kind else AnchorKind.UNKNOWN
    except ValueError:
        return ""
    if kind is AnchorKind.UNKNOWN and row.derivation in ("llm_absolute", "rule_absolute"):
        return "原文写明，无需推算"
    anchor_at = row.anchor_at
    days = (row.due_at.date() - anchor_at).days if anchor_at else None
    return anchor_note_for(kind=kind, anchor_at=anchor_at, delivery_date=None, days=days)


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
                user=user,
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
    user: Any | None = None,
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
            **_reminder_binding_kwargs(task),
            reminder_type=reminder_type,
            content=_build_reminder_content(reminder_type, row.context_text),
            due_at=aware_due_at,
            metadata={
                "source": REMINDER_SOURCE,
                "source_id": f"task:{task.id}:candidate:{row.id}",
                "task_id": task.id,
            },
            # 安全审计 M-1：记录创建人（该提醒关联案件日志，写权限由案件 ACL
            # 决定；created_by 仅为可追溯性补全，不改变权限口径）
            created_by=user,
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
        "日期候选已确认: task_id=%s, candidate_id=%s, reminder_id=%s, case_log_id=%s, case_id=%s, standalone=%s",
        task.id,
        candidate_id,
        reminder.id,
        task.case_log_id,
        task.case_id,
        task.case_log_id is None and task.case_id is None,
    )
    return {
        "candidate_id": candidate_id,
        "status": "confirmed",
        "reminder_id": reminder.id,
        "message": message,
        "error_code": None,
    }


def _reminder_binding_kwargs(task: Any) -> dict[str, Any]:
    """确认写提醒时的关联锚点，按优先级回落（Reminder 三者最多绑一个，故只能选一个）。

    只认 case_log_id 会让「案件已绑定、日志尚未落库」的任务（识别完成到日志创建
    之间确认日期就是这种时序）产出三个关联字段全空的孤立提醒，日历上显示
    「未关联案件」且无补救入口。任务已绑定案件时退一步挂案件本身是正确归属。
    两者都无才是真正的独立提醒（快捕获场景，不强制选案）。
    """
    if task.case_log_id is not None:
        return {"case_log_id": task.case_log_id}
    if task.case_id is not None:
        return {"case_id": task.case_id}
    return {"case_log_id": None}


def _find_existing_reminder(reminder_service: Any, task: Any, aware_due_at: datetime) -> Any | None:
    """按 (case_log_id, due_at) 查重复用（含无 source 的旧自动提醒）；独立提醒无查重域。

    查重域刻意不扩到 case_id（属语义变更，会改变「同一时间点是否复用既有提醒」）：
    该域回收的是「存量自动写入的旧提醒」（按案件日志时间比对），而 case_id 域里
    混着任务自己确认过的及其它模块建的整案级提醒。放宽后确认日期可能复用一条
    同刻但来源/语义不同的提醒，候选行会指向不是本功能创建的 reminder（撤销时被
    NOT_REVOKABLE 拦住，用户无从清理）；且 case_id 级提醒覆盖整案多个时间点，
    同刻命中概率远高于 case_log。宁可多一条挂在案件上的提醒，也不改语义。
    """
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
