"""日期候选的纯规则层（从 ``date_candidate_service`` 拆分出来，2026-11-27）。

只放**无 ORM、无 io** 的确定性规则：

- 常量与正则规则表（类型优先级、期间/相对期限、判决书给付义务剔除）；
- 期间结构（``_apply_period_rules``）、相对期限推算（``_apply_relative_deadline_rules``）、
  年份追溯（``_has_explicit_year``）等纯函数；
- 候选草稿 ``DateCandidateDraft`` 与两个纯解析入口
  （``parse_candidate_datetime`` / ``_verdict_from_draft``）。

依赖方向单向：``date_candidate_service`` → 本模块 → ``date_candidate_policy``。
本模块**不得** import ``date_candidate_service``（会成环）。非纯依赖只有枚举/常量：
``apps.reminders.models.ReminderType``（提醒类型取值域）、
``DatetimeExtractionMixin``（正则提取的纯函数能力）。行为与原模块逐字一致。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from apps.reminders.models import ReminderType

from ._datetime_extraction_mixin import DatetimeExtractionMixin
from .data_classes import DocumentType
from .date_candidate_policy import EFFECTIVE_FIRST_NOTE as _policy_effective_first_note
from .date_candidate_policy import (
    AnchorDocument,
    AnchorKind,
    AnchorVerdict,
    DocumentRole,
    anchor_note_for,
    confidence_for,
)
from .date_candidate_policy import find_issue_date as _policy_find_issue_date
from .date_candidate_policy import is_optional_motion, parse_anchor_clause

logger = logging.getLogger("apps.document_recognition")

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

# 注：本文件不再自带「签发日期」正则。同名常量在 date_candidate_policy.py:161-162
# 里有一份更宽松的（带 `\s*`）并实际在用；这两份重复定义在本文件内从未被引用，
# 属拆分时留下的死代码（CodeQL #7238/#7239，2026-11-24 note 棘轮上线后首次捕获）。

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


# 提醒类型的中文标签：确认写提醒（``_build_reminder_content``）与候选序列化
# （``date_candidate_repository.list_candidates``）两处都要，故留在纯规则层做单一来源。
def _reminder_type_label(reminder_type: str) -> str:
    try:
        return str(ReminderType(reminder_type).label)
    except ValueError:
        return reminder_type
