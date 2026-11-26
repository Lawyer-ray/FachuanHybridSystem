"""模型正文字段洁净度：把「思维链/元话语」挡在成稿之外，并对异常数值给出提示。

## 为什么在取值出口做确定性闸，而不是继续加强 prompt

真机（2026-11-26，案卷 489）实跑里，模型把整段自我推演当成「事实与理由」交了回来：
`我们需要起草……只能使用给定事实……558: 乙方（受让方）：受让人甲`，整篇 docx 律师一个字都用不了。
prompt 里已经写了「只写本节正文」，但这个泄漏是概率性的（同一语料换成合同全文就复现不了）。
律师要签字的文书不能赌模型的自觉，所以在 LLM → 槽位这个唯一出口上再设一道确定性规则：
**宁可这一段转未决，也不把半截推演写进成稿。**

## 为什么阈值是「>=2 个不同特征」而不是「命中一个就丢」

`注意：`、`规则：` 这类词在正常法律正文里也会偶发（「注意事项：」「裁判规则：」），
一命中就整段丢弃会把好正文误杀，而模型自述往往成片出现。用「不同特征计数」既保住
偶发单点，又能识别整段推演；`558: xxx` 这种伪条目单独计数（>=3 条），因为纯正文里
不会连续出现「行首编号 + 冒号 + 空格」的 OCR 行号格式。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

#: 真机泄漏样本里的元话语特征。长的写在前面只是阅读顺序，判定时会压掉被长特征完全覆盖的短特征
#: （否则「只能使用给定事实」会被同时算成两条，阈值就失去意义）。
METADATA_MARKERS: tuple[str, ...] = (
    "我们需要",
    "给出事实",
    "给定事实",
    "只能使用给定事实",
    "应当写",
    "能推出来吗",
    # 真机样本里模型写成「能推出吗？」（少一个「来」），两种写法都算同一类自问自答
    "能推出吗",
    "注意：",
    "下面我",
    "规则：",
    # 第二轮真机（同一案卷，换结构化输出前）泄漏换了一身皮：模型用「需要按时间顺序：」
    # 「所以管辖？可以提」「需要不重复小标题」这类**规划句**，而不是第一轮的「我们需要」。
    # 只按第一轮的表收特征，第二轮的成稿就一路绿灯——这也是为什么还要有下面的密度口径。
    "需要",
    "需要按",
    "需要不",
    "需要先",
    "需要把",
    "可以写",
    "可以提",
    "通常包括",
    "本节",
    "小标题",
    "不能编造",
    "推断不出",
    "所以",
    "let's",
    "we need",
    "i need",
    "parse",
)

#: 命中的**不同**特征数达到这个值才判成推演：单个「注意：」在正文里是正常措辞。
_MIN_FEATURES = 2
#: 伪条目（行首 OCR 行号）达到这个数才判成推演：单条可能是正文里的正常编号列表。
_MIN_PSEUDO_ENTRIES = 3
#: 可当作正文返回的连续块最小长度：太短的「干净块」多半是推演里夹着的一句半成品。
_MIN_BODY_BLOCK_CHARS = 20

_PSEUDO_ENTRY_RE = re.compile(r"^\s*\d{1,4}\s*[:：]\s+(?P<payload>\S.*)$")
_DAILY_PERCENT_RE = re.compile(r"每日\s*(?P<rate>\d+(?:\.\d+)?)\s*[%％]")
_AMOUNT_RE = re.compile(r"(?<![\d.])(?P<amount>\d[\d,，]*(?:\.\d+)?)\s*元")
_TOTAL_RE = re.compile(r"(?:合计|共计|总计)\s*[：:]?\s*(?:为|人民币)?\s*(?P<amount>\d[\d,，]*(?:\.\d+)?)\s*元")
_SENTENCE_BREAKS = "。；;！!？?\n"

#: 日利率安全上限：真机里「每日 3‰」被 OCR 成「每日 3%」，年化 1095% 一眼反常。
#: 0.5%/日的口径来自报告 D3（月息约 15%，已明显越过民间借贷常见区间）。
_DAILY_PERCENT_LIMIT = Decimal("0.5")


#: 元话语密度上限（每 100 字命中次数）。法律正文里「本节」「注意」偶发一次就到顶，
#: 而模型自述会成片出现；阈值取 1.2 是拿第一轮（27k 字泄漏）与干净成稿（1.5k 字）实测
#: 两侧都留了余量后的取值。
_METADATA_DENSITY_LIMIT = 1.2
#: 密度口径只对足够长的文本生效（短句里一个「注意」就能把密度顶到 7）。
_DENSITY_MIN_CHARS = 200
#: 夹花回收的最低占比：干净句要占到全文 35% 以上才值得回收，否则整段转未决。
_SALVAGE_RATIO = 0.35
_ENGLISH_SENTENCE_RE = re.compile(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}\s+[A-Za-z]{2,}")


def looks_like_reasoning(text: str, *, material: str = "") -> bool:
    """这段模型输出是不是自我推演（应当整段丢弃），而不是可交付的正文。

    Args:
        text: 模型交回的原文。
        material: 喂给模型的材料原文；伪条目只有在**行内容不在材料里**时才可疑——
            模型复述材料原句（哪怕带行号）不算自述，不能据此丢掉正文。
    """
    body = (text or "").strip()
    if not body:
        return False
    features = _metadata_features(body)
    if len(features) >= _MIN_FEATURES:
        return True
    # 密度口径：单一特征反复出现（「需要按…需要把…需要先…」）也算推演
    hits = sum(body.count(marker) for marker in METADATA_MARKERS)
    # 短句不适用密度口径：一句「注意：……」在 14 个字里密度天然很高，但它是正常正文。
    if len(body) >= _DENSITY_MIN_CHARS and hits and hits * 100 / len(body) >= _METADATA_DENSITY_LIMIT:
        return True
    if _ENGLISH_SENTENCE_RE.search(body):
        return True
    pseudo_entries = sum(1 for line in body.splitlines() if _is_pseudo_entry(line, material))
    return pseudo_entries >= _MIN_PSEUDO_ENTRIES


def strip_reasoning(text: str, *, material: str = "") -> str:
    """从模型输出里取出可交付的正文；整篇都是推演时返回空串（让上游转未决）。

    只在 `looks_like_reasoning` 命中时才裁剪：正常正文原样返回，避免把偶发一个
    「注意：」的段落截断。命中后只认**第一个**不含任何元话语/伪条目的连续块，
    且块长要达到 `_MIN_BODY_BLOCK_CHARS`——找不到就返回空串，绝不把半截推演塞进文书。
    """
    body = (text or "").strip()
    if not body:
        return ""
    if not looks_like_reasoning(body, material=material):
        return body
    # 逐句剔除，而不是「只取第一段干净块」：真机的泄漏是**夹花**的——干净的法律陈述
    # 与规划句交替出现（「需要按时间顺序：1. 2026 年 5 月 8 日签订…所以管辖？可以提」）。
    # 只取第一块会把后面所有可用的正文一起丢掉，律师仍然拿不到成稿。
    kept = [
        sentence.strip()
        for sentence in _sentences(body)
        if sentence.strip()
        and not _has_metadata(sentence, material)
        and "？" not in sentence
        and "?" not in sentence
        and not _ENGLISH_SENTENCE_RE.search(sentence)
    ]
    cleaned = "\n".join(kept)
    minimum = max(_MIN_BODY_BLOCK_CHARS, int(len(body) * _SALVAGE_RATIO))
    return cleaned if len(cleaned) >= minimum else ""


def _sentences(text: str) -> list[str]:
    """按中文句读切句，**保留分隔符**：剔除单句时不能把下一句的句号一起吃掉。"""
    parts: list[str] = []
    buffer = ""
    for char in text:
        buffer += char
        if char in "。；！？\n":
            parts.append(buffer)
            buffer = ""
    if buffer.strip():
        parts.append(buffer)
    return parts


def check_numeric_sanity(text: str) -> list[str]:
    """对正文里的比率/金额做确定性核对，返回给人看的 warning（不修改正文）。

    这里只做「一眼反常」的算术核对，不替律师判断约定是否合法：异常比率与合计不符
    都有可能是 OCR 或模型抄错，落到成稿前必须让人看一眼。
    """
    body = (text or "").strip()
    if not body:
        return []
    warnings = _daily_rate_warnings(body)
    warnings.extend(_mixed_ratio_warnings(body))
    warnings.extend(_total_mismatch_warnings(body))
    return warnings


def sanitize_llm_body(text: str, *, material: str = "") -> tuple[str, list[str]]:
    """LLM 正文洁净度总闸：先剥离推演，再核对数值，返回 `(正文, warnings)`。

    正文为空表示「模型没写出可交付的正文」，调用方应与模型失败同路处理（转未决），
    而不是把空串当正常结果写进成稿。
    """
    body = strip_reasoning(text, material=material)
    return body, check_numeric_sanity(body)


def _metadata_features(text: str) -> set[str]:
    """命中的元话语特征集合；被更长特征完全覆盖的出现不算独立特征。"""
    claimed: list[tuple[int, int]] = []
    features: set[str] = set()
    for marker in sorted(METADATA_MARKERS, key=len, reverse=True):
        for start in _occurrences(text, marker):
            end = start + len(marker)
            if any(begin <= start and end <= finish for begin, finish in claimed):
                continue
            features.add(marker)
            claimed.append((start, end))
    return features


def _occurrences(text: str, marker: str) -> list[int]:
    positions: list[int] = []
    start = text.find(marker)
    while start != -1:
        positions.append(start)
        start = text.find(marker, start + len(marker))
    return positions


def _is_pseudo_entry(line: str, material: str) -> bool:
    """行首「数字 + 冒号 + 空格」的伪条目：行内容不在材料里才判可疑。"""
    match = _PSEUDO_ENTRY_RE.match(line)
    if match is None:
        return False
    payload = match.group("payload").strip()
    if not payload:
        return False
    return not _in_material(payload, material)


def _in_material(payload: str, material: str) -> bool:
    """材料原文是否包含这一行（OCR 会插空格，所以按去空白后的文本再比一次）。"""
    if not material:
        return False
    if payload in material:
        return True
    return _squash(payload) in _squash(material)


def _squash(text: str) -> str:
    return "".join(text.split())


def _blocks(text: str) -> list[str]:
    """按空行切出的连续段落块（本链路的模型输出「每段一行」，空行是唯一的分块信号）。"""
    blocks: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line:
            current.append(line)
            continue
        if current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def _has_metadata(block: str, material: str) -> bool:
    if _metadata_features(block):
        return True
    return any(_is_pseudo_entry(line, material) for line in block.splitlines())


def _daily_rate_warnings(text: str) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for match in _DAILY_PERCENT_RE.finditer(text):
        raw_rate = match.group("rate")
        rate = _decimal(raw_rate)
        if rate is None or rate <= _DAILY_PERCENT_LIMIT or raw_rate in seen:
            continue
        seen.add(raw_rate)
        warnings.append(
            f"每日 {raw_rate}% 的比率反常（年化约 {rate * 365:.0f}%），疑似 OCR 识别或数值错误，请核对合同原文"
        )
    return warnings


def _mixed_ratio_warnings(text: str) -> list[str]:
    """同一段（本链路「每段一行」）混用 ‰ 与 %：两个符号混排几乎都意味着漏抄或抄错。"""
    for line in text.splitlines():
        if "‰" in line and "%" in line:
            return ["同一段落同时出现千分号（‰）与百分号（%），请核对约定比率与折算口径"]
    return []


def _total_mismatch_warnings(text: str) -> list[str]:
    """分项金额相加与「合计」不符：只在同一句里出现 >=2 个分项时才判（避免单笔被误算成和）。"""
    warnings: list[str] = []
    for line in text.splitlines():
        for total_match in _TOTAL_RE.finditer(line):
            claimed = _decimal(total_match.group("amount"))
            if claimed is None:
                continue
            segment = line[_sentence_start(line, total_match.start()) : total_match.start()]
            items = [amount for match in _AMOUNT_RE.finditer(segment) if (amount := _decimal(match.group("amount")))]
            if len(items) < 2:
                continue
            subtotal = sum(items, Decimal("0"))
            if subtotal == claimed:
                continue
            warnings.append(f"金额分项合计 {subtotal:.2f} 元与文中声称的合计 {claimed:.2f} 元不一致，请核对分项或合计")
    return warnings


def _sentence_start(line: str, end: int) -> int:
    """合计所在句子的起点：分项只可能在同一个句子里被「合计」汇总。"""
    head = line[:end]
    cut = max(head.rfind(break_char) for break_char in _SENTENCE_BREAKS)
    return cut + 1


def _decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "").replace("，", ""))
    except (InvalidOperation, ValueError):
        return None


__all__ = [
    "METADATA_MARKERS",
    "check_numeric_sanity",
    "looks_like_reasoning",
    "sanitize_llm_body",
    "strip_reasoning",
]
