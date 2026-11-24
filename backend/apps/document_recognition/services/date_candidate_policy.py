"""关键日期候选的判定闸门（纯函数，无 IO、不依赖 Django）。

## 为什么要有这个模块

2026-11-24 的真实事故：法院短信（一诉 8 份送达文书）里，《诉讼权利义务告知书》和
《诉讼费退费缴费须知》两份**不含本案期限**的通用文书各自被报出一条"关键日期"，
还带着「规则 85%」并**默认勾选**，律师一键就能把假日期写进案件日历。

根因不是 AI 不准（那两份文书 LLM 一条日期都没报），而是确定性正则层：

- 「至迟应在**裁判文书**送达之日起三日内提出」→ 按「收到告知书 + 3 天」编出日期。
  可那份裁判文书**还没产生**，起算点根本不存在；
- 「应自收到**《缴费通知书》**之日起七日内交纳」→ 锚点是另一份文书，而且这句是
  通用须知里的规则说明，不是本案期限。

于是所有语义判断最后都塌缩成一个 ``confidence`` 数字。本模块把判断拆成三件事，
全部是**可单测的纯函数**：

1. ``classify_document_role`` —— 这份文书到底承不承载本案期限（内容判据，不看文件名）；
2. ``parse_anchor_clause`` —— 期限句的起算锚指向谁（本份 / 同批另一份 / 尚未产生的文书 / 他案）；
3. ``decide_candidate`` —— 该留还是该丢、带哪些复核标记、能不能默认勾。

口径与设计依据：``docs/analysis/date-candidate-provenance-2026-11-24/SUMMARY.md``
§3（设计原则）、§5（五道闸门）、§6（置信度语义）。业务口径（2026-11-24 拍板）：
选择性申请类期限**不进日历**；通用文书里的**明文绝对日期仍保留**（不默认勾）；
批内只按"完全相同键"去重，同日不同日期两条都留。

## 分层

本模块**只依赖 stdlib**，禁止 import Django / apps.*——判定逻辑必须能脱离框架直接
单测。调用方（``date_candidate_service``）负责编排与落库。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

logger = logging.getLogger("apps.document_recognition")

# ---------------------------------------------------------------------------
# 取值域（与模型字段 help_text、API schema 的 description 逐字对应，不得单独改一处）
# ---------------------------------------------------------------------------


class DocumentRole(str, Enum):
    """文书角色：是否承载本案期限。"""

    CARRIER = "carrier"  # 期限载体：传票、通知书、判决/裁定/调解书、有落款的通知…
    GENERIC_NOTICE = "generic_notice"  # 通用告知/须知类：正文是通则，不含本案专属期限


class AnchorDocument(str, Enum):
    """期限句的起算锚指向哪一份文书。"""

    SELF = "self"  # 本份文书（含原文省略主语，如「收到次日起」）
    OTHER_IN_BATCH = "other_in_batch"  # 同一条短信里另一份文书
    FUTURE_DOCUMENT = "future_document"  # 尚未产生的文书（裁判文书/判决书）
    OTHER_CASE = "other_case"  # 他案文书 / 商业函件 / 合同约定


class AnchorKind(str, Enum):
    """起算锚本身的语义。"""

    SERVICE_OF_SELF = "service_of_self"  # 本份文书的送达日
    ISSUE_DATE_OF_SELF = "issue_date_of_self"  # 本份文书的落款/打印日
    EFFECTIVE_DATE = "effective_date"  # 判决/裁定发生法律效力之日
    FOREIGN_DOCUMENT = "foreign_document"  # 锚点在别的文书上
    UNKNOWN = "unknown"


FLAG_ANCHOR_EFFECTIVE = "anchor_effective"
FLAG_GENERIC_BOILERPLATE = "generic_boilerplate"
FLAG_LOW_CONFIDENCE = "low_confidence"
FLAG_FAR_FUTURE = "far_future"
FLAG_DUPLICATE = "duplicate"
FLAG_DISCARDED = "discarded_by_gate"

#: 复核标记 → 给律师看的人话（前端直接展示；后端是单一来源）
FLAG_LABELS: dict[str, str] = {
    FLAG_ANCHOR_EFFECTIVE: "起算点为判决生效日，请与书记员确认",
    FLAG_GENERIC_BOILERPLATE: "出自通用告知类文书，非本案专属期限",
    FLAG_LOW_CONFIDENCE: "提取置信度偏低，请核对",
    FLAG_FAR_FUTURE: "远期日期（超过 10 年）",
    FLAG_DUPLICATE: "同批已有一条更权威的同日期候选",
    FLAG_DISCARDED: "已被规则过滤（不进日历）",
}

#: 推算方式 → 中文标签（前端"来源"那一行直接显示，避免前后端各写一份口径）
DERIVATION_LABELS: dict[str, str] = {
    "llm_absolute": "原文写明",
    "rule_absolute": "原文日期 + 规则",
    "rule_period": "期间结构推算",
    "rule_relative": "规则推算",
}

#: 起算点为判决生效日时的提示文案（业务口径 2026-11-14：这类履行期限要记，
#: 但起算点取决于对方是否上诉，只有书记员能确认，所以给保守日期 + 明示待确认）
EFFECTIVE_FIRST_NOTE = (
    "起算点为判决生效之日（送达后 15 日内无人上诉才生效），此处按送达日给的保守日期，请与书记员确认生效日后改期"
)

#: 超过这个天数的未来日期视为长期约定（房贷 30 年到期日/土地租期），降置信 + 不默认勾
FAR_FUTURE_DAYS = 365 * 10

#: 置信度低于此值打 low_confidence（注意：默认勾选**只认 flags**，不认分数）
LOW_CONFIDENCE_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# 文书角色判据
# ---------------------------------------------------------------------------

#: 硬性期限载体（文首标题名）。这些文书即便 OCR 吃掉了落款日期，也一定是本案文书。
_CARRIER_TITLE_KEYWORDS: tuple[str, ...] = (
    "传票",
    "开庭通知",
    "应诉通知书",
    "受理案件通知书",
    "举证通知书",
    "交费通知书",
    "交纳诉讼费用通知书",
    "诉讼费用交费通知书",
    "缴费通知书",
    "执行通知书",
    "判决书",
    "裁定书",
    "调解书",
    "决定书",
    "送达回证",
)

#: 通用告知/须知类（正文是通则说明，通常不含本案专属期限）
_GENERIC_TITLE_KEYWORDS: tuple[str, ...] = (
    "须知",
    "告知书",
    "权利义务告知",
    "风险提示",
    "监督卡",
    "送达地址确认",
    "授权委托书",
    "评价表",
    "回访表",
)

#: 案号形态（（20XX）粤0000民初0000号）——有案号说明是本案专属文本
_CASE_NUMBER_RE = re.compile(r"[（(]\s*\d{4}\s*[）)]")

#: 落款日期：阿拉伯数字与中文数字两种写法（法院用中文数字落款的比例很高）
_ISSUE_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_ISSUE_DATE_CN_RE = re.compile(
    r"([〇零一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月([一二三四五六七八九十]{1,3})日"
)
_CN_YEAR_DIGITS: dict[str, int] = {ch: i for i, ch in enumerate("〇一二三四五六七八九")}
_CN_DIGIT_MAP: dict[str, int] = {"〇": 0, "零": 0, **{ch: i for i, ch in enumerate("一二三四五六七八九", start=1)}}

#: 有效年份区间（与旧实现一致：OCR 乱码年份一律不认）
_MIN_ISSUE_YEAR = 2020
_MAX_ISSUE_YEAR = 2030


def _parse_cn_year(value: str) -> int | None:
    """「二〇二五」→ 2025（四位中文数字逐年拼接）。"""
    if len(value) != 4 or any(ch not in _CN_YEAR_DIGITS for ch in value):
        return None
    return int("".join(str(_CN_YEAR_DIGITS[ch]) for ch in value))


def _parse_cn_day_month(value: str) -> int | None:
    """「十一」→ 11、「二十」→ 20、「三」→ 3（1~31 的月/日）。"""
    if not value:
        return None
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        if (left and left not in _CN_DIGIT_MAP) or (right and right not in _CN_DIGIT_MAP):
            return None
        tens = _CN_DIGIT_MAP.get(left, 1) if left else 1
        ones = _CN_DIGIT_MAP.get(right, 0) if right else 0
        return tens * 10 + ones
    if len(value) == 1:
        return _CN_DIGIT_MAP.get(value)
    return None


def find_issue_date(text: str) -> datetime | None:
    """文书签发/落款日期：取全文**位置最后**的一个「YYYY年M月D日」（阿拉伯或中文数字）。

    为什么取最后一个：落款惯例在文末（「打印日期：二〇二五年十一月十一日」），
    取最后一个可避开正文里的业务日期（开庭日、举证截止日等）。

    为什么它是"本案专属"信号：通用告知/须知类是法院统一印发的模板，文末的
    「年月日」通常是**空白**（实际样本：诉讼权利义务告知书、退费须知、举证通则、
    廉政监督卡、诉讼参加人须知的结尾都是裸「年月日」）；而针对本案出具的文书
    一定带具体落款日期（如「二〇二六年十一月二十四日」）。
    """
    if not text:
        return None
    found: list[tuple[int, datetime]] = []
    for m in _ISSUE_DATE_RE.finditer(text):
        try:
            found.append((m.start(), datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
        except ValueError:
            continue
    for m in _ISSUE_DATE_CN_RE.finditer(text):
        year = _parse_cn_year(m.group(1))
        month = _parse_cn_day_month(m.group(2))
        day = _parse_cn_day_month(m.group(3))
        if year is None or month is None or day is None:
            continue
        try:
            found.append((m.start(), datetime(year, month, day)))
        except ValueError:
            continue
    valid = [(pos, dt) for pos, dt in found if _MIN_ISSUE_YEAR <= dt.year <= _MAX_ISSUE_YEAR]
    if not valid:
        return None
    return max(valid, key=lambda item: item[0])[1]


def has_concrete_issue_date(text: str) -> bool:
    """文中有具体落款日期（= 本案专属锚存在）。裸「年月日」占位不算。"""
    return find_issue_date(text) is not None


def classify_document_role(*, text: str, filename: str = "") -> tuple[DocumentRole, str]:
    """判定文书角色：这份文书到底承不承载本案期限。

    判据顺序（命中即返回，**内容优先、文件名只作兜底**——法院把文件名写成
    「告知书（…）.pdf」这种事每天都在发生，文件名不可控）：

    1. 文首 600 字含硬性载体类型名 → CARRIER；
    2. 文中有具体落款日期 → CARRIER（有本案专属落款 = 本案文书）；
    3. 无落款日期 且（命中通用告知类词表 或 全文无案号）→ GENERIC_NOTICE；
    4. 其余 → CARRIER（保守放行：宁可多送一条，也不用启发式丢掉真期限）。

    为什么不按文件名精确匹配就够了：``document_template_filter`` 的清单里确实有
    「诉讼权利义务告知书」，但那次归档名就是「告知书（…）_20261124收.pdf」，
    子串匹配不到；而且该过滤只作用于短信旁线，手工上传完全绕过。
    """
    body = text or ""
    # 标题区只取文首 80 字：取 600 字会把**正文**里的「调解书」「财产保全」当成标题命中
    # （实测：诉讼权利义务告知书正文有「有申请财产保全、证据保全的权利」，被误判成期限载体）。
    head = re.sub(r"\s+", "", body[:80])
    tail_hint = filename or ""

    for keyword in _CARRIER_TITLE_KEYWORDS:
        if keyword in head:
            return DocumentRole.CARRIER, f"文首命中期限载体类型名「{keyword}」"

    issue = find_issue_date(body)
    if issue is not None:
        return DocumentRole.CARRIER, f"文中有具体落款日期 {issue.date().isoformat()}（本案专属）"

    generic_hit = next((kw for kw in _GENERIC_TITLE_KEYWORDS if kw in head or kw in tail_hint), "")
    if generic_hit:
        return DocumentRole.GENERIC_NOTICE, f"无落款日期且命中通用告知类型名「{generic_hit}」"
    if not _CASE_NUMBER_RE.search(body):
        return DocumentRole.GENERIC_NOTICE, "无落款日期且全文无案号（判断为非本案专用文本）"
    return DocumentRole.CARRIER, "保守放行：有案号但未命中通用告知类型名"


# ---------------------------------------------------------------------------
# 锚点归属判据（治本的那道闸）
# ---------------------------------------------------------------------------

#: 抽「收到/送达 + <被送达物> + 之日起/次日起/后」里的被送达物。
#: 旧实现（``_RELATIVE_ANCHOR_RE``）用 ``[^，。；;\n]{0,14}?`` 把这 14 个字**吞掉**，
#: 于是「本通知」「裁判文书」「《缴费通知书》」三种完全不同的语义在下游等价——
#: 这正是假日期的直接来源。
#: 文书名词（用于识别「<文书>送达之日起」这种名词在动词**前面**的语序）
_DOC_NOUN = (
    r"(?:裁判文书|生效裁判|判决书|裁定书|调解书|决定书|通知书|告知书|裁决书"
    r"|本通知|本判决|本裁定|本调解书|本决定书|本告知书|本函)"
)
#: 语序一：<文书>送达/签收之日起（如「裁判文书送达之日起三日内」）
_ANCHOR_PRE_RE = re.compile(rf"(?P<subject>《[^》]{{1,30}}》|{_DOC_NOUN})\s*(?:送达|签收)")
#: 语序二：收到/签收 + <文书> + 之日起（如「收到《缴费通知书》之日起七日内」）
_ANCHOR_POST_RE = re.compile(r"(?:收到|接到|收悉|签收)(?P<subject>[^，。；;\n]{0,14}?)(?:之|次)?(?:日起?|后)")

#: 自指词：锚点就是本份文书（原文常省略主语，如「收到次日起七日内」）
_SELF_MARKERS: tuple[str, ...] = (
    "本通知",
    "本通知书",
    "本告知书",
    "本决定书",
    "本判决",
    "本裁定",
    "本调解书",
    "本文书",
    "本规则",
    "本须知",
    "本书",
)

#: 生效起算（业务口径：保留候选但标待确认，见 EFFECTIVE_FIRST_NOTE）
_EFFECTIVE_RE = re.compile(r"生效|发生法律效力|确定法律效力")

#: 具名文书（有书名号或无，都当"另一份文书"处理）
_NAMED_DOC_RE = re.compile(r"通知书|决定书|判决书|裁定书|调解书|告知书|裁决书")

#: 本文书自己可能就是这类文书（判决书里「判决书送达之日起十五日内上诉」、
#: 裁定书里「收到裁定书之日起五日内申请复议」——锚点都是本份，不是别份）。
#: 同句内出现「本判决/本裁定/本调解书」时即认定自指；否则交给调用方传 self_titles。
_SELF_DOC_NOUN_RE = re.compile(r"判决书|裁定书|调解书")
_QUOTED_RE = re.compile(r"《([^》]{1,30})》")

#: 尚未产生的文书（无"本"字修饰时）
_FUTURE_DOC_RE = re.compile(r"裁判文书|判决书|裁定书|调解书|生效裁判")

#: 他案/非本院文书标识（旧 ``_OTHER_MATTER_MARKERS`` 收编于此，不再另立一套）
_OTHER_CASE_MARKERS: tuple[str, ...] = (
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

#: 被送达物在日志/审计里的截断长度
_SUBJECT_CLIP = 20


@dataclass(frozen=True)
class AnchorVerdict:
    """期限句起算锚的归属判定结果。"""

    document: AnchorDocument
    kind: AnchorKind
    reason: str = ""
    subject: str = ""


def _clip(value: str) -> str:
    return (value or "").strip()[:_SUBJECT_CLIP]


def parse_anchor_clause(
    *,
    sentence: str,
    match_start: int,
    match_end: int,
    sibling_documents: Sequence[str] = (),
    self_titles: Sequence[str] = (),
) -> AnchorVerdict:
    """判定一个相对期限句的起算锚指向哪一份文书。

    Args:
        sentence: 已按句切分的原文（调用方保证不跨句，避免相邻句的动词互相污染）。
        match_start / match_end: 期限匹配（"收到…之日起 N 日内"）在 sentence 内的区间。
        sibling_documents: 同一条短信/同一批次里的其他文书显示名。用于把
            「收到《缴费通知书》之日起」判成 ``OTHER_IN_BATCH``（交给那份文书自己算）
            而不是 ``FUTURE_DOCUMENT``。手工上传场景为空。
        self_titles: 本文书自己的类型名（如 ("裁定书",)）。「收到裁定书之日起五日内
            申请复议」讲的就是本份裁定的救济期限，不能当成"别份文书"丢掉。

    Returns:
        AnchorVerdict；``document != SELF`` 且 ``kind != effective_date`` 的期限一律丢弃。
    """
    body = sentence or ""
    start = max(0, match_start)
    end = max(start, min(len(body), match_end))
    # 往前取 30 字：要能覆盖「本判决发生法律效力之日起」这类无「收到/送达」动词的锚点
    window = body[max(0, start - 30) : end]
    # 两种语序都要认：「裁判文书送达之日起」（名词在前）与「收到《缴费通知书》之日起」（名词在后）。
    # 旧实现只认后一种，而且用通符把被送达物吞掉，于是三种完全不同的语义在下游等价。
    matched = _ANCHOR_PRE_RE.search(window) or _ANCHOR_POST_RE.search(window)
    subject = (matched.group("subject") or "").strip() if matched else ""
    clipped = _clip(subject)
    wide = body[max(0, start - 40) : end + 40]

    # a) 他案 / 商业函件 / 合同约定：锚点讲的不是本判决本裁定，先摘出去
    for marker in _OTHER_CASE_MARKERS:
        if marker in subject or marker in wide:
            return AnchorVerdict(
                AnchorDocument.OTHER_CASE,
                AnchorKind.FOREIGN_DOCUMENT,
                f"锚点指向他案/函件（命中「{marker}」）",
                clipped,
            )

    # b) 以「发生法律效力」起算：保留（业务口径），但必须标待确认。
    # 判据取整个前窗而非只看 subject：原文可能写成「本判决发生法律效力之日起十日内」，
    # 这种句式根本没有「收到/送达」动词，subject 抽出来是空的。
    if _EFFECTIVE_RE.search(subject) or _EFFECTIVE_RE.search(window):
        return AnchorVerdict(
            AnchorDocument.SELF,
            AnchorKind.EFFECTIVE_DATE,
            "锚点为本判决/裁定发生法律效力之日",
            clipped,
        )

    # c) 自指（含原文省略主语的情形）
    if not subject or any(marker in subject for marker in _SELF_MARKERS):
        return AnchorVerdict(
            AnchorDocument.SELF,
            AnchorKind.SERVICE_OF_SELF,
            "锚点指向本份文书（或原文省略主语）",
            clipped,
        )

    # d) 本文书自身类型名（判决书里的「判决书送达之日起十五日」、裁定书里的
    #    「收到裁定书之日起五日内申请复议」）——同句有「本判决/本裁定」或
    #    subject 命中调用方传进来的 self_titles，就认自指。
    if _SELF_DOC_NOUN_RE.search(subject) and any(marker in body for marker in _SELF_MARKERS):
        return AnchorVerdict(
            AnchorDocument.SELF,
            AnchorKind.SERVICE_OF_SELF,
            "锚点指向本份文书（同句出现「本判决/本裁定」类自指表述）",
            clipped,
        )
    for title in self_titles:
        if title and title in subject:
            return AnchorVerdict(
                AnchorDocument.SELF,
                AnchorKind.SERVICE_OF_SELF,
                f"锚点命中本文书类型名「{title}」",
                clipped,
            )

    # e) 具名他文书（《缴费通知书》/执行通知书…）：本批有 → 交给那份文书；没有 → 等它送达
    quoted = _QUOTED_RE.search(subject)
    if quoted or _NAMED_DOC_RE.search(subject):
        name = quoted.group(1) if quoted else subject
        hit = next((s for s in sibling_documents if name and (name in s or s in name)), "")
        if hit:
            return AnchorVerdict(
                AnchorDocument.OTHER_IN_BATCH,
                AnchorKind.FOREIGN_DOCUMENT,
                f"锚点是同批另一份文书「{_clip(name)}」的送达日，期限归属那份文书",
                clipped,
            )
        return AnchorVerdict(
            AnchorDocument.FUTURE_DOCUMENT,
            AnchorKind.FOREIGN_DOCUMENT,
            f"锚点指向另一份文书「{_clip(name)}」（本批未见），现在算不出真日期",
            clipped,
        )

    # e) 尚未产生的裁判文书（本告知书里"裁判文书送达之日"就是典型）
    if _FUTURE_DOC_RE.search(subject):
        return AnchorVerdict(
            AnchorDocument.FUTURE_DOCUMENT,
            AnchorKind.FOREIGN_DOCUMENT,
            "锚点指向尚未产生的裁判文书，现在算不出真日期",
            clipped,
        )

    # f) 判断不出 → 不采信
    return AnchorVerdict(
        AnchorDocument.OTHER_CASE,
        AnchorKind.UNKNOWN,
        "无法判断锚点归属，按不可信处理",
        clipped,
    )


# ---------------------------------------------------------------------------
# 选择性申请闸（业务口径 2026-11-24：不进日历）
# ---------------------------------------------------------------------------

#: 选择性申请类条款：想不想做由当事人/律师决定，法院没给本案指定期限。
#: 实测样本：「申请对裁判文书中的有关内容进行技术处理或者申请不予公布的，
#: 至迟应在裁判文书送达之日起三日内以书面形式提出」——正是这条被当成"补正期限"。
_OPTIONAL_MOTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("申请不予公布/技术处理", re.compile(r"申请(?:对[^，。；;\n]{0,12})?(?:不予公布|不公开|技术处理)")),
    ("申请延期/延长/顺延", re.compile(r"申请(?:延期|延长|顺延)")),
    ("申请证人出庭", re.compile(r"申请[^，。；;\n]{0,6}出庭")),
    ("申请鉴定", re.compile(r"申请[^，。；;\n]{0,6}鉴定")),
    ("申请调查收集证据", re.compile(r"申请[^，。；;\n]{0,8}调查[^，。；;\n]{0,6}证据")),
    ("申请证据保全", re.compile(r"申请证据保全")),
    ("申请回避", re.compile(r"申请[^，。；;\n]{0,4}回避")),
)

#: 保留词：这些是律师真正要跟的救济/程序期限，即使句中有"申请"也不得丢弃。
#: 「复议」尤其关键——裁定书「五日内申请复议」是律师唯一的救济窗口。
_OPTIONAL_KEEP_WORDS: tuple[str, ...] = ("复议", "上诉", "答辩", "管辖", "举证期限")


def is_optional_motion(sentence: str) -> tuple[bool, str]:
    """这句话是不是"选择性申请类"条款（申请不予公布/延期/证人出庭/鉴定/调查取证/回避）。

    Returns:
        (True, 人话原因) 表示应整条丢弃；(False, "") 表示不是这类条款。
    """
    text = sentence or ""
    for keep in _OPTIONAL_KEEP_WORDS:
        if keep in text:
            return False, ""
    for label, pattern in _OPTIONAL_MOTION_PATTERNS:
        matched = pattern.search(text)
        if matched is not None:
            return True, f"选择性申请类条款（{label}，命中「{matched.group(0)}」），按口径不进日历"
    return False, ""


# ---------------------------------------------------------------------------
# 置信度与默认勾选
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateDecision:
    """一条候选的最终裁决。"""

    keep: bool
    flags: tuple[str, ...]
    confidence: float
    default_checked: bool
    reason: str = ""


def confidence_for(*, derivation: str, anchor: AnchorVerdict, role: DocumentRole, raw: float) -> float:
    """按『来源 + 锚点 + 文书角色』给置信度。

    数字只表达**提取可靠度**，可不可信由 flags 表达（见 ``decide_candidate``）。
    这样做的原因：旧实现里 0.85 既是"规则算出来的"又当成"很可信"，还踩过
    「压到恰好 0.5 仍默认勾」的边界，律师分不清哪个数字该信。
    """
    if role is DocumentRole.GENERIC_NOTICE:
        return min(float(raw), 0.40)
    if derivation == "rule_relative":
        return 0.45 if anchor.kind is AnchorKind.EFFECTIVE_DATE else 0.90
    if derivation == "rule_absolute":
        return 0.85
    return float(raw)


def decide_candidate(
    *,
    derivation: str,
    anchor: AnchorVerdict,
    role: DocumentRole,
    confidence: float,
    due_at: datetime,
    today: date,
) -> CandidateDecision:
    """该留还是该丢；留下时带哪些复核标记、能不能默认勾选。

    丢弃规则（三条，都是阻塞式）：

    1. 锚点不在本份文书上（同批另一份 / 尚未产生的文书 / 他案）→ 丢。理由：
       期限归属那份文书，由它自己的识别产出；现在算只会算出一个假日期。
    2. 通用告知类文书上的**规则推算**候选 → 丢（那两句"N 日内"是通则说明）。
       但 LLM 读到的**明文绝对日期**仍保留，只是打 generic_boilerplate、不默认勾。
    3. 选择性申请类条款在编排层就会被 ``is_optional_motion`` 丢掉，这里不重复判断。

    默认勾选**只认 flags**：``default_checked = keep and not flags``——彻底消灭
    "分数恰好压线仍默认勾"这类边界事故。
    """
    flags: list[str] = []
    if anchor.kind is AnchorKind.EFFECTIVE_DATE:
        flags.append(FLAG_ANCHOR_EFFECTIVE)
    if role is DocumentRole.GENERIC_NOTICE:
        flags.append(FLAG_GENERIC_BOILERPLATE)
    if (due_at.date() - today).days > FAR_FUTURE_DAYS:
        flags.append(FLAG_FAR_FUTURE)
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        flags.append(FLAG_LOW_CONFIDENCE)

    reason = ""
    keep = True
    if anchor.document is not AnchorDocument.SELF:
        keep = False
        reason = anchor.reason or "锚点不在本份文书上，期限归属别处"
    elif role is DocumentRole.GENERIC_NOTICE and derivation == "rule_relative":
        keep = False
        reason = "通用告知类文书里的相对期限属于通则说明，不是本案期限"

    return CandidateDecision(
        keep=keep,
        flags=tuple(flags),
        confidence=confidence,
        default_checked=keep and not flags,
        reason=reason,
    )


def anchor_note_for(
    *,
    kind: AnchorKind,
    anchor_at: date | None,
    delivery_date: date | None,
    days: int | None = None,
) -> str:
    """把锚点渲染成给律师看的一句话（确认弹窗第三行）。

    律师判断"这条日期靠不靠得住"的唯一线索就是这个：锚是谁、加了多少天。
    旧实现算好了 ``anchor_note`` 却在落库前丢掉，前端从来没显示过。
    """
    if kind is AnchorKind.EFFECTIVE_DATE:
        return EFFECTIVE_FIRST_NOTE
    if kind is AnchorKind.SERVICE_OF_SELF:
        base = delivery_date or anchor_at
        if base is None:
            return "起算点：本份文书送达日"
        note = f"起算点：本份文书送达日 {base.isoformat()}"
        return f"{note} + {days} 天" if days else note
    if kind is AnchorKind.ISSUE_DATE_OF_SELF:
        if anchor_at is None:
            return "起算点：文书落款日"
        note = f"起算点：文书落款日 {anchor_at.isoformat()}"
        return f"{note} + {days} 天" if days else note
    return ""
