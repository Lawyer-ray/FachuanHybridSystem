"""跨页文本一致性校对：用「同一段文字在多页重复出现时的写法差异」揪 OCR 错字。

## 要解决的问题

印章、落款、抬头、表头这类文字在一本卷宗里会重复出现几十上百次。OCR 对同一次
出现不会错得一样——多数识别对了，少数错了几个字。于是同一段文字就有了多种写法，
**低频写法里几乎一定藏着错字**，而高频写法就是「本卷宗实际印的是什么」。

一份 164 页卷宗里，同一枚经办人章高频出现的是正确写法、少数几页被认错一个字；
流水表表头里 `交易卡号` 出现 179 次，其中 15 次被认成 `交易方号`。两处错字都由本
模块自动揪出。这是**零成本、零模型**的检测：不要 OCR 置信度，也不要语言模型，只用
「同一份卷宗里同一段文字应该只有一种写法」这一条事实。

## 只比对「原子语义单元」，不对正文滑窗

判据的全部风险都在「什么算同一个词的两种写法」。对正文任意位置做 3..6 字全滑窗会
因为**滑窗 × 一字差**变成噪声发生器：`支付宝支付` 与 `财付通支付` 都是真词，它们的
窗口必然在一字差处相交；`资料相符` / `原件相符` 同理。实测在 157 页真实卷宗上这样
跑出 **1340 条**命中，人工核过有效的只有几条。调高 ``min_count`` 也没用（提到 10 仍有
几百条）——噪声本身就是高频的。

所以片段只从两处抽，都是**天然原子**的位置：

- **字段值**：`经办人：张某某 罗某某` 这类「已知字段名 + 冒号」后面的一段。字段名是
  闭集（见 ``_FIELD_NAMES``）——OCR 会把句子粘在值后面，也会把前文粘在字段名上，只有
  按真字段名锚定才能两头都挡住。值里允许空格，归一去空白后与不带空格是同一个值。
- **表头单元格**：被空白隔开的整段中文（`… 当前余额 交易卡号 20170201 …`）。真实 OCR
  把表格吐成**空格分隔的行内散排**，一个 `|` 都没有。表头的结构证据是「一组表头词类
  相邻出现」（见 ``_HEADER_WORD_CLASSES``），`交易卡号` / `交易方号` 就出自这里。

两条路覆盖了本判据能可靠处理的全部场景，且不以「正文任意片段」为输入，所以
`的利率`、`抵押权利` 这类句子碎片根本进不来。

## 判据

1. **只比同长度片段**。长度不同不比较——`张三` vs `张三丰` 是两个人，不是漏字。
2. **至多 1 个字不同**。差 1 字正是形近字/漏笔/多笔的形态；差 2 字以上无从判断是
   同一个词写错了还是本来就是两个词。
3. **频次悬殊才算**：低频写法必须是高频写法的零头。门槛按「像不像人名」分两档
   （``TERM_MIN_RATIO`` / ``PERSON_NAME_MIN_RATIO``），不够悬殊的根本不进结果。

## 必须避开的误判

- **真不同的人名**：``张某某`(21) vs `张某某2`(15) 是两个自然人——两个人各自被写了
  十几次。人名门槛比业务术语高就是为了挡住这类：共有人 / 保证人 / 配偶本来就是「同姓、
  差一个字」的形态。宁可漏报，不可把两个人的名字混成一个——那会让律师以为卷宗里只有
  一个人，而且误报一次就没人再信这个功能。
- **只差空白的写法不算**：`张某某罗某某` 与 `张某某 罗某某` 是排版差异，OCR 没认错字。
- **`交易卡号` vs `交易方号` 这类要抓到**：179 vs 15，频次悬殊、差 1 字，是真错字。
- **签字栏的单字错要抓到**：`丙某某`(16) 在正文、`丙某甲`(3) 只在签字栏——5.3 倍，刚好
  越过人名门槛。门槛定高了这条就没了，定低了人名误报就回来了。

## 输出不是结论，是线索

`Inconsistency` 只说明「同一处有两种写法，其中一种很可能是错的」，**不判断到底哪个字
对**。真实存在的两种写法（签名习惯、盖章盖反）也会命中，所以要人看列表决定采信与否。
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

#: 参与比对的片段长度区间（按归一化后的字符数计）。
MIN_FRAGMENT_LEN = 3
MAX_FRAGMENT_LEN = 6

#: 字段名：卷宗里固定出现的那几个，后接冒号。值必须按**已知字段名**锚定，不能「任意
#: 中文 + 冒号」——OCR 会把句子粘在值后面（`经办人: 张某某 罗某某已核对…`），也会把
#: 前文粘在字段名上（`通借记卡主活期账户交易明细表: 易日期…`）。白名单挡得住两头。
_FIELD_NAMES = "经办人 受办人 负责人 复核人 签字 签章 户名 账户名 客户姓名 共有人 保证人 借款人 抵押人 姓名".split()  # noqa: SIM905

#: 字段值：已知字段名 + 冒号，后面取一段中文（可含空格），再由 ``max_len`` 截断。
_FIELD_VALUE_RE = re.compile(
    "(?:%s)[：:][ \\t]*([\\u4e00-\\u9fa5][\\u4e00-\\u9fa5 \\t]*)" % "|".join(_FIELD_NAMES),
)

#: 表头单元格：被空白 / 换行 / `|` 隔开的整段中文。OCR 出来的表头是**空格分隔的行内
#: 散排**（`… 当前余额 交易卡号 20170201 …`），真实卷宗里一个 `|` 都没有。
_TABLE_CELL_RE = re.compile(r"(?:^|[\s\n|｜])([\u4e00-\u9fa5]+)(?=[\s\n|｜]|$)")

#: 表头词类：判据是「一组相邻的表头词类」——表头行里这些词连着出现好几个，数据行里的
#: 正文词（`财付通支付`）不会。与词类一字差的写法（`交易方号` / `易日期`）正是要揪的错字。
_HEADER_WORD_CLASSES = frozenset(
    "交易卡号 交易日期 对方账号 摘要 发生额 当前余额 余额 户名 账号 金额 利率 期限 地址 电话 备注 证件类型 证件号码 客户姓名 开户银行".split()  # noqa: SIM905
)

#: 一行里至少这么多个表头词类（含一字差）相邻，才认定为表头行。
_HEADER_RUN_MIN = 2

#: 频次悬殊门槛：低频写法必须是高频写法的零头才报。业务术语 3 倍就够；人名要 4 倍——
#: 同姓差一字的两个人（共有人 / 保证人 / 配偶）太常见，1.4 倍的 `曾妙铭`(21) vs
#: `曾妙瑜`(15) 就是两个自然人。
TERM_MIN_RATIO = 3.0
PERSON_NAME_MIN_RATIO = 4.0

#: 人名里不会出现的字。反过来判「像人名」不可靠——`交易卡号` 也是 3-4 个纯中文字。
_BUSINESS_CHARS = frozenset(
    "合同协议银行日期金额利率账号编号司支行余额额本利息抵押担保借贷凭证细据表种类期号码卡户款项费税账存款交易明单份书证书计算报告案审诉讼机关公司企业务"
)


@dataclass(frozen=True)
class Inconsistency:
    """一处「同一段文字有两种写法」的疑似 OCR 错字。

    ``canonical`` 是高频写法（推荐的正确写法），``variant`` 是低频变体（疑似错字），
    ``pages`` 是变体出现过的页号（升序、去重）——律师要靠它翻回原页核对。
    ``confidence`` 当前恒为 ``"high"``：频次不够悬殊的根本不返回（宁可漏报，不可误报）。
    """

    canonical: str
    variant: str
    canonical_count: int
    variant_count: int
    pages: list[int]
    confidence: str


def _normalize(text: str) -> str:
    """去掉全部空白：同一段文字的排版差异不应制造假变体。"""
    return re.sub(r"\s+", "", text)


def _is_header_word(value: str) -> bool:
    """这个词是否与某个表头词类差 1 个字（含长度差 1 的漏字/多字），或本来就在词类里。

    必须容纳长度差：`易日期`（3）是 `交易日期`（4）漏了一个字的写法，`交易方号`
    也是 `交易卡号` 换了一个字。只比同长度会把真错字挡在门外。
    """
    return any(_char_edit_distance(value, word) <= 1 for word in _HEADER_WORD_CLASSES)


def _char_edit_distance(left: str, right: str) -> int:
    """两个词的编辑距离，只需分得清「<=1」与「>1」（插入/删除/替换代价均为 1）。"""
    if left == right:
        return 0
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right, strict=True))
    if abs(len(left) - len(right)) > 1:
        return 2
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    dropped = [longer[:index] + longer[index + 1 :] for index in range(len(longer))]
    return 1 if shorter in dropped else 2


def _iter_header_words(text: str) -> list[str]:
    """抽出一页表头行里的单元格。

    表头的结构证据是「相邻的表头词类成串」：一行里命中的单元格（含一字差变体）
    连着出现 >= ``_HEADER_RUN_MIN`` 个，这些单元格才算表头。数据行里夹杂的中文
    （`财付通支付`、`联动收费手续费`）不命中词类，也就不会成串。
    """
    headers: list[str] = []
    # 先抹掉字段值：值里有空格（`张某某 罗某某`），不抹会被空白切成两个「表头单元格」
    for line in _FIELD_VALUE_RE.sub("：", text or "").splitlines():
        run: list[str] = []
        for word in [*(_normalize(cell) for cell in _TABLE_CELL_RE.findall(line)), ""]:
            if word and _is_header_word(word):
                run.append(word)
                continue
            if len(run) >= _HEADER_RUN_MIN:
                headers.extend(run)
            run = []
    return headers


def _count_text_occurrences(text: str, words: set[str]) -> Counter[str]:
    """统计候选词在一页里的出现次数。

    必须**按出现次数**而不是按「这页有没有」：一本 164 页卷宗里错字可能 15 次全落在
    同一份 15 页复印件的每页表头上，只按页计就只剩 1 页，永远过不了 ``min_count``。
    而且要在**空白归一**的文本上数——`张某某 罗某某` 与 `张某某罗某某` 是同一段文字，
    归一前 canonical 频次会拦腰砍半。
    """
    normalized = _normalize(text)
    return Counter({word: normalized.count(word) for word in words})


def _iter_candidates(text: str, *, max_len: int) -> list[str]:
    """抽出一页里所有可参与比对的原子片段（字段值 + 表头单元格）。

    两路都必须是**整段中文**再按长度过滤，不能从长句中滑窗——滑窗会切出 `的利率`、
    `款合同` 这类句子碎片，它们与别的碎片一字差相交后就是纯噪声。

    字段值还要**按空白再切一次**：一个字段可能并列多个值，`经办人：张某某 罗某某`
    是两个人而不是一个六字词，不切开的话「张某某」永远不会作为独立候选出现。
    """
    candidates: list[str] = []
    for match in _FIELD_VALUE_RE.finditer(text or ""):
        raw = match.group(1)
        candidates.extend(_normalize(piece)[:max_len] for piece in re.split(r"[ \t]+", raw.strip()))
        # 粘连形态（无空格）另存一份整体：OCR 常把两个人名连写，它本身也是一种合法写法
        candidates.append(_normalize(raw)[:max_len])
    candidates.extend(_iter_header_words(text))
    return [value for value in candidates if MIN_FRAGMENT_LEN <= len(value) <= max_len]


def _pages_for(fragment: str, pages_text: dict[int, str]) -> list[int]:
    """片段出现过的页号（去重、升序）。按空白归一的文本比对，与计数口径一致。"""
    return sorted(int(page) for page, text in pages_text.items() if fragment in _normalize(text))


def _one_char_diff(left: str, right: str) -> bool:
    """两个等长字符串是否恰好差 1 个字符。"""
    return sum(a != b for a, b in zip(left, right, strict=True)) == 1


def _pick_canonical(left: str, right: str, counts: Counter[str]) -> tuple[str, str]:
    """频次高者为 canonical；频次相同时按字典序定序，保证输出稳定。"""
    if counts[left] > counts[right]:
        return left, right
    if counts[right] > counts[left]:
        return right, left
    return (left, right) if left < right else (right, left)


def _looks_like_person_name(word: str) -> bool:
    """像不像一个人名：3-4 字，且一个业务字都没有。

    这条只用来**收紧**门槛：把业务术语误判成人名，只是门槛从 3 倍升到 4 倍（略漏报）；
    把人名误判成业务术语，才会让它按 3 倍报出去（误报）。两种代价不对称，所以宁可
    多判成人名。
    """
    return 3 <= len(word) <= 4 and not (set(word) & _BUSINESS_CHARS)


def _min_ratio(canonical: str, variant: str) -> float:
    """这一对写法的频次门槛：人名更严，业务术语放宽。"""
    return (
        PERSON_NAME_MIN_RATIO
        if _looks_like_person_name(canonical) or _looks_like_person_name(variant)
        else TERM_MIN_RATIO
    )


def _is_close_frequency(counts: Counter[str], canonical: str, variant: str) -> bool:
    """两种写法频次接近——各自被写了十几次，更像两个不同的人，而不是错字（门槛见
    ``_min_ratio``）。"""

    return counts[canonical] < counts[variant] * _min_ratio(canonical, variant)


def find_inconsistencies(
    pages_text: dict[int, str],
    *,
    min_count: int = 3,
    max_len: int = MAX_FRAGMENT_LEN,
) -> list[Inconsistency]:
    """找出全卷里疑似 OCR 错字的低频写法变体。

    Args:
        pages_text: ``{页码: 该页文本}``。
        min_count: 片段至少出现多少次才参与比较。低频噪声（OCR 偶发怪字符）
            不参与，也就不会制造假变体。
        max_len: 片段长度上限，默认 6（人名 2-4 字 + 术语 4-6 字）。

    Returns:
        按 ``variant_count`` 降序排列（先看证据最多的），同频次按 canonical / variant
        字典序。
    """
    if not pages_text or min_count < 2 or max_len < MIN_FRAGMENT_LEN:
        return []

    candidates = {value for text in pages_text.values() for value in _iter_candidates(text, max_len=max_len)}
    # 频次按出现次数算：同一页里重复出现的表头/字段值不能只算一次
    counts: Counter[str] = Counter()
    for text in pages_text.values():
        counts.update(_count_text_occurrences(text, candidates))

    frequent = {fragment for fragment, count in counts.items() if count >= min_count}
    # 只有同长度才比较——「张三」vs「张三丰」是长度差异，不是漏字
    by_length: dict[int, list[str]] = defaultdict(list)
    for fragment in sorted(frequent):
        by_length[len(fragment)].append(fragment)

    hits: list[Inconsistency] = []
    for fragments in by_length.values():
        for left_index, left in enumerate(fragments):
            for right in fragments[left_index + 1 :]:
                if not _one_char_diff(left, right):
                    continue
                canonical, variant = _pick_canonical(left, right, counts)
                if _is_close_frequency(counts, canonical, variant):
                    # 频次接近的两种写法各自被写了十几次：更像两个不同的人
                    # （``张某某`(21) vs `张某某2`(15)），不是同一个词写错了
                    continue
                hits.append(
                    Inconsistency(
                        canonical=canonical,
                        variant=variant,
                        canonical_count=counts[canonical],
                        variant_count=counts[variant],
                        pages=_pages_for(variant, pages_text),
                        confidence="high",
                    )
                )

    return sorted(hits, key=lambda item: (-item.variant_count, item.canonical, item.variant))
