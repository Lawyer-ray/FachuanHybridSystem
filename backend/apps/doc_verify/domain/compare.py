"""比对引擎：把两份文书跑成一份可复核的失败清单（纯函数，无 IO、无 Django）。

## 判定顺序是硬的

1. **字节相同就停**：`sha256` 相等时一条断言都不算。数字件原样回传是最常见的入库
   路径，对它跑全文比对既慢、又只可能产出噪声。
2. **包级 → 页级 → 字段级 → 段落级 → 覆盖度**：粗粒度先拦，细粒度再列。页级只比
   指纹，字段级/段落级只比正文。

状态不在这里拍：`derive_state` 从 findings 与 coverage 推导（见 `states.py`）。

## 三条「不许瞎报」的硬约束

- **两侧都没指纹的页跳过**：没有证据的页不能算「变了」；
- **字段与段落只比「两侧都有文本」的页**：入站是扫描件、或某页没文本层时，拿基线
  那一页的正文去比空气，只会把整页内容报成「少了一句」——这是本模块最容易造假
  告警的地方，必须在拼比对文本时就剔除；
- **tier 0 不报 gray**：免费层的盲区（扫描件没文本层）由状态（`no_difference_detected`）
  和 `coverage` 如实表达，不用 gray 把清单淹没；tier ≥ 1 才是「尝试过了仍取不到」，
  这时才报 `PAGE_NO_TEXT`，状态落到 `unverifiable`。

## 页指纹口径

与 `apps/cases/services/material/scan_archive_naming.py` 的 `signature_distance` /
`SAME_PAGE_MAX_DISTANCE` 逐位同结果（单测对比两条实现）。各自持有一份而不互相 import：
那个模块服务归档命名，本模块要能作为纯函数被 domain 层直接 import，跨模块拉依赖会把
cases 的模型/服务链拖进来。
"""

from __future__ import annotations

import difflib
import logging
import re
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any, NamedTuple

from apps.doc_verify.domain.contracts import AssertionKind, Baseline, Finding, Inbound, Report, Severity
from apps.doc_verify.domain.normalize import normalize_text, similarity, split_pages, split_paragraphs

logger = logging.getLogger(__name__)

# ── 页指纹阈值 ──────────────────────────────────────────────────────────────

#: 同一页允许的指纹平均绝对差。0.03 的来历见 `scan_archive_naming.SAME_PAGE_MAX_DISTANCE`
#: 的注释（真副本 0.008~0.0243、不同文书 ≥0.044）。
SAME_PAGE_MAX_DISTANCE = 0.03

# ── 段落对齐阈值 ────────────────────────────────────────────────────────────

#: 相似度 ≥ 此值视为「同一段」（换行/标点/个别错字的差异），不报。
_PARAGRAPH_SAME_SIMILARITY = 0.92

#: 相似度 ≥ 此值才配成「同一句的两种写法」（报「改了一句」）；更低就当作一删一增。
_PARAGRAPH_PAIR_FLOOR = 0.5

#: 一个替换块内逐对比较的预算（左行数 × 右行数）。超出就退化成按位配对：
#: 两份毫不相干的文书会形成一个巨大的替换块，逐对算相似度是 O(n·m) 次序列比对。
_PARAGRAPH_PAIR_BUDGET = 400

#: expected / actual 的截断长度。律师要看的是「这一句大概在说什么」，不是整段。
_EXCERPT_MAX_CHARS = 120

# ── 字段抽取（在归一化后的正文上跑） ────────────────────────────────────────

#: 金额：带单位才认（`998,702.06 元` / `12万元`）。
_AMOUNT_UNIT_RE = re.compile(r"\d[\d,]*\.?\d*\s*(?:万元|元)")

#: 「合计/共计/标的额」邻域里不带单位的裸数字。金额写漏单位时仍要能抓到。
_AMOUNT_KEYWORD_RE = re.compile(r"(?:合计|共计|标的额)[^。\n]{0,20}?(\d[\d,]*\.?\d*)")

#: 日期：`2026年11月25日`（允许字间空白：文本层常在数字与汉字之间插空格）。
_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

#: 案号：`（2026）粤0604民初1234号`（虚构样例）。归一化已把全角括号折成半角，这里写半角。 privacy-allow
_CASE_NO_RE = re.compile(r"\(\d{4}\)[^)]{1,20}号")

#: 诉请项：行首编号（归一化已把 `、` 折成 `,`，两种都收）。
_CLAIM_ITEM_RE = re.compile(r"^\s*\d+[.,]")

#: 「诉讼请求」段起点。
_CLAIM_SECTION_RE = re.compile(r"诉讼请求")

#: 「诉讼请求」段结束：中文序号标题、下一个法定段落名，或落款。
_SECTION_BREAK_RE = re.compile(r"^(?:[一二三四五六七八九十]+、|事实与理由|此致|答辩事项|证据清单)")


def page_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """两个页指纹的平均绝对差（0–1）。长度不一致视为完全不同（返回 1.0）。"""
    if not a or not b or len(a) != len(b):
        return 1.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def compare_documents(baseline: Baseline, inbound: Inbound, *, tier: int = 0) -> Report:
    """把出站基线与被核对件跑成一份失败清单。`tier` 只影响覆盖度断言的严格程度。"""
    if baseline.sha256 and baseline.sha256 == inbound.sha256:
        logger.debug("回传件与基线字节相同，跳过全部断言：%s", baseline.doc_type)
        return Report(findings=[], coverage=_identical_coverage(baseline), tier=tier)

    text = _text_comparison(baseline, inbound)
    fields = _field_findings(text)
    findings: list[Finding] = []
    findings.extend(_package_findings(baseline, inbound))
    findings.extend(_page_findings(baseline, inbound))
    findings.extend(fields.findings)
    findings.extend(_paragraph_findings(text))
    findings.extend(_coverage_findings(text, tier=tier))
    return Report(findings=findings, coverage=_coverage(text, fields), tier=tier)


# ── 包级 / 页级 ─────────────────────────────────────────────────────────────


def _package_findings(baseline: Baseline, inbound: Inbound) -> list[Finding]:
    """包级：页数不等就是红线——少一页可能是抽掉了整页附件。"""
    if baseline.page_count == inbound.page_count:
        return []
    return [
        Finding(
            kind=AssertionKind.PACKAGE,
            code="PAGE_COUNT_MISMATCH",
            title="页数不一致",
            severity=Severity.RED,
            detail="出站件与回传件的页数不同，可能有整页缺失或夹带",
            expected=str(baseline.page_count),
            actual=str(inbound.page_count),
        )
    ]


def _page_findings(baseline: Baseline, inbound: Inbound) -> list[Finding]:
    """页级：逐页比指纹，超阈值的页给一条「疑似改动」。

    两侧都没指纹的页跳过：那不是「变了」，是「没测」——报出来只会逼人逐页翻。
    """
    findings: list[Finding] = []
    for index, (left, right) in enumerate(zip(baseline.page_signatures, inbound.page_signatures)):
        if not left and not right:
            continue
        distance = page_distance(left, right)
        if distance <= SAME_PAGE_MAX_DISTANCE:
            continue
        findings.append(
            Finding(
                kind=AssertionKind.PAGE,
                code="PAGE_CHANGED",
                title=f"第 {index + 1} 页疑似改动",
                detail=f"页指纹距离 {distance:.4f} 超过阈值 {SAME_PAGE_MAX_DISTANCE}（可能是签章/噪点，也可能是改了字）",
                page=index + 1,
            )
        )
    return findings


# ── 正文覆盖度（拼接比对用的文本） ──────────────────────────────────────────


class _TextComparison(NamedTuple):
    """标题上「比得了哪几页」的结论，供字段/段落/覆盖度三层共用。"""

    baseline_text: str
    inbound_text: str
    pages_total: int
    pages_with_text: int
    pages_no_text: int
    pages_without_text: tuple[int, ...]


def _text_comparison(baseline: Baseline, inbound: Inbound) -> _TextComparison:
    """逐页配对比对文本：只有**两侧都有文本**的页进比对，其余页只计覆盖度。"""
    baseline_pages = [normalize_text(page) for page in split_pages(baseline.text)]
    inbound_pages = [normalize_text(page) for page in split_pages(inbound.text)]
    pages_total = max(baseline.page_count, inbound.page_count, len(baseline_pages), len(inbound_pages))
    compared_baseline: list[str] = []
    compared_inbound: list[str] = []
    without_text: list[int] = []
    for index in range(pages_total):
        left = baseline_pages[index] if index < len(baseline_pages) else ""
        right = inbound_pages[index] if index < len(inbound_pages) else ""
        if left and right:
            compared_baseline.append(left)
            compared_inbound.append(right)
            continue
        without_text.append(index + 1)
    return _TextComparison(
        baseline_text="\n".join(compared_baseline),
        inbound_text="\n".join(compared_inbound),
        pages_total=pages_total,
        pages_with_text=pages_total - len(without_text),
        pages_no_text=len(without_text),
        pages_without_text=tuple(without_text),
    )


# ── 字段级 ──────────────────────────────────────────────────────────────────


class _FieldComparison(NamedTuple):
    findings: list[Finding]
    checked: int
    skipped: int


def _field_findings(text: _TextComparison) -> _FieldComparison:
    """字段级（red，零容忍）：按多重集合比金额/日期/案号/诉请项数。

    多重集合而不是集合：同一份合同里 998702.06 出现两处、回传只剩一处，是改了，
    集合会把它当成「一样」。
    """
    if not text.baseline_text or not text.inbound_text:
        logger.debug("有一侧整篇取不到文本，字段级比对跳过（%d 项）", len(_FIELD_CHECKS))
        return _FieldComparison(findings=[], checked=0, skipped=len(_FIELD_CHECKS))

    findings: list[Finding] = []
    checked = 0
    skipped = 0
    for code, title, extract in _FIELD_CHECKS:
        expected = extract(text.baseline_text)
        actual = extract(text.inbound_text)
        if expected is None or actual is None:
            skipped += 1
            logger.debug("字段 %s 至少一侧取不到，跳过比对", code)
            continue
        checked += 1
        finding = _field_mismatch(code, title, expected, actual)
        if finding is not None:
            findings.append(finding)
    return _FieldComparison(findings=findings, checked=checked, skipped=skipped)


def _field_mismatch(code: str, title: str, expected: list[str], actual: list[str]) -> Finding | None:
    missing, extra = _multiset_diff(expected, actual)
    if not missing and not extra:
        return None
    return Finding(
        kind=AssertionKind.FIELD,
        code=code,
        title=title,
        severity=Severity.RED,
        detail=f"基线出现 {len(expected)} 处、回传出现 {len(actual)} 处",
        expected="；".join(missing),
        actual="；".join(extra),
    )


def _multiset_diff(expected: list[str], actual: list[str]) -> tuple[list[str], list[str]]:
    """返回（基线多出来的、回传多出来的），重复次数参与比较。"""
    expected_counter = Counter(expected)
    actual_counter = Counter(actual)
    missing = sorted((expected_counter - actual_counter).elements())
    extra = sorted((actual_counter - expected_counter).elements())
    return missing, extra


def _amount_values(text: str) -> list[str]:
    """金额的**多重集合**（去千分位与空白后）。

    两路抽取合并：带单位的金额；以及「合计/共计/标的额」后 20 字内的裸数字。两路会
    命中同一处（`合计 998,702.06 元`），所以按字符位置去重——否则一侧写了「合计」、
    另一侧只写金额时，重复计数本身会变成一条假红线。
    """
    spans: list[tuple[int, int, str]] = []
    for match in _AMOUNT_UNIT_RE.finditer(text):
        spans.append((match.start(), match.end(), _canonical_amount(match.group(0))))
    for match in _AMOUNT_KEYWORD_RE.finditer(text):
        spans.append((match.start(1), match.end(1), _canonical_amount(match.group(1))))
    values: list[str] = []
    last_end = 0
    for start, end, value in sorted(spans, key=lambda span: (span[0], -span[1])):
        if start < last_end:
            continue
        values.append(value)
        last_end = end
    return values


def _canonical_amount(token: str) -> str:
    """去掉千分位与空白：`998,702.06 元` 与 `998702.06元` 是同一笔钱。"""
    return re.sub(r"[\s,]", "", token)


def _date_values(text: str) -> list[str]:
    """日期的多重集合（补零不敏感：`2026年11月5日` 与 `2026年11月05日` 是同一天）。"""
    return [f"{int(m.group(1))}年{int(m.group(2))}月{int(m.group(3))}日" for m in _DATE_RE.finditer(text)]


def _case_no_values(text: str) -> list[str]:
    """案号的多重集合。全角括号已在归一化里折成半角，两侧写法差异不会误报。"""
    return [re.sub(r"\s+", "", match.group(0)) for match in _CASE_NO_RE.finditer(text)]


def _claim_counts(text: str) -> list[str] | None:
    """「诉讼请求」段内的编号行数（`1.` / `2、`）；整篇没有这一段时返回 `None`。"""
    lines = text.split("\n")
    start = next((index for index, line in enumerate(lines) if _CLAIM_SECTION_RE.search(line)), None)
    if start is None:
        return None
    count = 0
    for line in lines[start + 1 :]:
        if _SECTION_BREAK_RE.match(line):
            break
        if _CLAIM_ITEM_RE.match(line):
            count += 1
    return [str(count)]


#: 字段检查表：`(机器码, 人看的标题, 抽取函数)`。抽取函数返回 `None` 表示「本侧没有这个字段」。
_FIELD_CHECKS: tuple[tuple[str, str, Callable[[str], list[str] | None]], ...] = (
    ("AMOUNT_MISMATCH", "金额不一致", _amount_values),
    ("DATE_MISMATCH", "日期不一致", _date_values),
    ("CASE_NO_MISMATCH", "案号不一致", _case_no_values),
    ("CLAIM_COUNT_MISMATCH", "诉讼请求项数不一致", _claim_counts),
)


# ── 段落级 ──────────────────────────────────────────────────────────────────


class _ParagraphPairs(NamedTuple):
    """段下标配对与未配上的下标（返回下标而不是文本：比对用去空格后的键，摘录要原文）。"""

    pairs: list[tuple[int, int, float]]
    missing: list[int]
    added: list[int]


def _paragraph_key(line: str) -> str:
    """段落比对键：去掉字间空格。

    中文正文里的空格是排版，不是内容：OCR 在汉字与数字之间插不插空格、表格单元格
    之间留几个空格，都不改变这句话的意思。带着空格比，一串纯排版差异就会报成
    「改了一句」——这是本模块最容易造出黄条的地方。
    """
    return line.replace(" ", "")


def _paragraph_findings(text: _TextComparison) -> list[Finding]:
    """段落级（yellow）：按段对齐后报「少了一句 / 多了一句 / 改了一句」。

    先用 difflib 在段落序列上找完全相同的段，再把替换块内部的段按相似度配对：
    ≥0.92 视为同一段（不报），0.5~0.92 报「改了一句」，配不上的报少/多。
    对齐与相似度都跑在 `_paragraph_key` 上，摘录用原文。
    """
    if not text.baseline_text or not text.inbound_text:
        return []
    baseline_paragraphs = split_paragraphs(text.baseline_text)
    inbound_paragraphs = split_paragraphs(text.inbound_text)
    baseline_keys = [_paragraph_key(line) for line in baseline_paragraphs]
    inbound_keys = [_paragraph_key(line) for line in inbound_paragraphs]
    matcher = difflib.SequenceMatcher(None, baseline_keys, inbound_keys, autojunk=False)
    findings: list[Finding] = []
    for tag, baseline_start, baseline_end, inbound_start, inbound_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            findings.extend(
                _paragraph_finding("PARAGRAPH_MISSING", "少了一句", expected=line)
                for line in baseline_paragraphs[baseline_start:baseline_end]
            )
            continue
        if tag == "insert":
            findings.extend(
                _paragraph_finding("PARAGRAPH_ADDED", "多了一句", actual=line)
                for line in inbound_paragraphs[inbound_start:inbound_end]
            )
            continue
        findings.extend(
            _replace_findings(
                baseline_paragraphs[baseline_start:baseline_end],
                inbound_paragraphs[inbound_start:inbound_end],
            )
        )
    return findings


def _replace_findings(baseline_block: list[str], inbound_block: list[str]) -> list[Finding]:
    pairs = _pair_paragraphs(baseline_block, inbound_block)
    findings: list[Finding] = []
    for baseline_index, inbound_index, score in pairs.pairs:
        if score >= _PARAGRAPH_SAME_SIMILARITY:
            continue
        findings.append(
            _paragraph_finding(
                "PARAGRAPH_CHANGED",
                "改了一句",
                expected=baseline_block[baseline_index],
                actual=inbound_block[inbound_index],
            )
        )
    findings.extend(
        _paragraph_finding("PARAGRAPH_MISSING", "少了一句", expected=baseline_block[i]) for i in pairs.missing
    )
    findings.extend(_paragraph_finding("PARAGRAPH_ADDED", "多了一句", actual=inbound_block[j]) for j in pairs.added)
    return findings


def _pair_paragraphs(baseline_block: list[str], inbound_block: list[str]) -> _ParagraphPairs:
    baseline_keys = [_paragraph_key(line) for line in baseline_block]
    inbound_keys = [_paragraph_key(line) for line in inbound_block]
    if len(baseline_keys) * len(inbound_keys) > _PARAGRAPH_PAIR_BUDGET:
        pairs = _pair_positionally(baseline_keys, inbound_keys)
    else:
        pairs = _pair_by_similarity(baseline_keys, inbound_keys)
    used_baseline = {i for i, _, _ in pairs}
    used_inbound = {j for _, j, _ in pairs}
    return _ParagraphPairs(
        pairs=sorted(pairs),
        missing=[index for index in range(len(baseline_block)) if index not in used_baseline],
        added=[index for index in range(len(inbound_block)) if index not in used_inbound],
    )


def _pair_by_similarity(baseline_keys: list[str], inbound_keys: list[str]) -> list[tuple[int, int, float]]:
    """贪心配对：相似度从高到低取，每段只用一次。块大小已由预算约束。"""
    scored = sorted(
        (
            (similarity(left, right), i, j)
            for i, left in enumerate(baseline_keys)
            for j, right in enumerate(inbound_keys)
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    used_baseline: set[int] = set()
    used_inbound: set[int] = set()
    pairs: list[tuple[int, int, float]] = []
    for score, i, j in scored:
        if score < _PARAGRAPH_PAIR_FLOOR:
            break
        if i in used_baseline or j in used_inbound:
            continue
        used_baseline.add(i)
        used_inbound.add(j)
        pairs.append((i, j, score))
    return pairs


def _pair_positionally(baseline_keys: list[str], inbound_keys: list[str]) -> list[tuple[int, int, float]]:
    """预算超支时的退化配对：按位置一对一，相似度不够就各算一删一增。

    两份毫不相干的文书会走进这里。此时「谁改成谁」本来就无从判断，按位配对至少
    保证报告规模与页数同阶，不会因为 n×m 次序列比对把一次核对拖成几分钟。
    """
    pairs: list[tuple[int, int, float]] = []
    for index in range(min(len(baseline_keys), len(inbound_keys))):
        score = similarity(baseline_keys[index], inbound_keys[index])
        if score < _PARAGRAPH_PAIR_FLOOR:
            continue
        pairs.append((index, index, score))
    return pairs


def _paragraph_finding(code: str, title: str, *, expected: str = "", actual: str = "") -> Finding:
    return Finding(
        kind=AssertionKind.PARAGRAPH,
        code=code,
        title=title,
        severity=Severity.YELLOW,
        expected=_clip(expected),
        actual=_clip(actual),
    )


def _clip(text: str) -> str:
    if len(text) <= _EXCERPT_MAX_CHARS:
        return text
    return text[:_EXCERPT_MAX_CHARS] + "…"


# ── 覆盖度 ──────────────────────────────────────────────────────────────────


def _coverage_findings(text: _TextComparison, *, tier: int) -> list[Finding]:
    """覆盖度（gray）：尝试过仍取不到文本的页。

    tier 0 不报：免费层本来就没有 OCR，扫描件没文本层是**已知且可解释**的盲区，
    用状态（no_difference_detected）与 coverage 表达即可；把它逐页报成 gray，清单会
    被「无法核对」淹没，真正的红线反而没人看。tier ≥ 1 是「已经花钱 OCR 过了，
    这页还是没字」，那才是无法核对。
    """
    if tier < 1:
        return []
    return [
        Finding(
            kind=AssertionKind.COVERAGE,
            code="PAGE_NO_TEXT",
            title=f"第 {page} 页取不到文本",
            severity=Severity.GRAY,
            detail="该页至少一侧没有文本层，正文无法核对",
            page=page,
        )
        for page in text.pages_without_text
    ]


def _coverage(text: _TextComparison, fields: _FieldComparison) -> dict[str, Any]:
    return {
        "pages_total": text.pages_total,
        "pages_with_text": text.pages_with_text,
        "pages_no_text": text.pages_no_text,
        "fields_checked": fields.checked,
        "fields_skipped": fields.skipped,
        # 正文级比对是否真的跑过：derive_state 判 verified_clean 的唯一依据之一。
        "text_compared": bool(text.baseline_text and text.inbound_text),
        "bytes_identical": False,
    }


def _identical_coverage(baseline: Baseline) -> dict[str, Any]:
    """字节相同时的覆盖度：没有任何一页「无法核对」，但也没跑过正文比对。

    `pages_with_text` 记 0 而不是页数：那一路没读文本，「有文本的页」这个数无从谈起，
    写了就是把没测的东西当成测过（`bytes_identical` 才是这一路的结论）。
    """
    return {
        "pages_total": baseline.page_count,
        "pages_with_text": 0,
        "pages_no_text": 0,
        "fields_checked": 0,
        "fields_skipped": 0,
        "text_compared": False,
        "bytes_identical": True,
    }
