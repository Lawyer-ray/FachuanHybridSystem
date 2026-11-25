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

## 频次法抓不到的：当事人姓名与证件号（实体感知判据）

频次悬殊法只认「高频正确 + 低频错字」这一种形态。真实 164 页银行档案实测：
借款人在「户名」字段下有 **5 种写法、各出现 1-2 页**，最大/最小频次比只有 2.0——
既过不了 ``min_count``（3 次），也过不了 ``PERSON_NAME_MIN_RATIO``（4 倍）。
于是全卷只检出 2 条银行经办人变体（73 次 vs 3 次），**法律上最关键的当事人姓名一条没报**。

所以补两条不依赖频次悬殊的判据，都只在**角色字段值**这个原子位置上做：

- ``entity_cluster``：同一角色字段下，同长度、同「姓+名首字」前缀的人名形态串聚成一簇。
  簇里 **>=3 种写法**且**跨 >=2 页**才提示。为什么是 3 种：2 种写法同前缀差一字，
  正是下面「必须避开的误判」里那两个自然人（`张三丰`/`张四丰`）的形态；要求 3 种
  是因为「三个同姓同名首字的兄弟姐妹恰好都落在同一个角色字段里」远比「一个人名被
  OCR 认成三种样子」少见。**输出是候选不是结论**：canonical 只是簇里出现页数最多的
  参照写法，不判定哪个对，confidence 给 medium。
- ``id_malformed``：同一证件号字段下，**结构非法**的写法（18 位证前 17 位出现了字母）
  与它至多差 2 位的**唯一**合法写法配对。结构合法性是硬证据，不需要频次；容忍 2 位
  是因为损坏侧根本不可能是真证件号，问题变成「这个字段里的哪个合法号码被认坏了」。
  候选不唯一就**不报**（同字段可能并列借款人 + 配偶）。两侧都合法但差几位的不报——
  那可能是相邻发号的两个自然人。

两条判据一律 medium：前端 ``draft/engine-suggest.ts`` 只信 high 才给「建议改成 X」，
所以 medium 天然落在「只提示、不自动改正文」这一侧，无需前端配合即安全。

**局限（必须知道）**：后端拿不到当事人名单（``detectParties`` 只在前端草稿里回填），
所以判据只能靠「角色字段 + 人名形态 + 前缀聚类」。姓名若**不出现在任何角色字段值里**
（只在合同正文或段名中），本判据仍然抓不到——不对正文滑窗是刻意的，那是 1340 条噪声的来源。

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
from itertools import combinations

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

#: 判据种类。``frequency`` 是原有的「频次悬殊」判据（confidence 恒 high）。
#: 后两种是**实体感知**判据，一律给 medium：前端 ``draft/engine-suggest.ts`` 只信
#: high 才给「建议改成 X」，所以 medium 天然落在「只提示、不自动改正文」这一侧。
#: 当事人姓名的多种写法频次接近（各 1-2 次），根本没有「哪个是高频正确写法」的证据，
#: 给 high 会让前端把两个真人合并成一个——比漏报坏得多。
KIND_FREQUENCY = "frequency"
KIND_ENTITY_CLUSTER = "entity_cluster"
KIND_ID_MALFORMED = "id_malformed"
KIND_CASE_NUMBER = "case_number_variant"
KIND_AMOUNT = "amount_variant"

# ────────── 案号 / 金额：同一条事实写成了两个版本 ──────────
#
# 为什么单开一类：前面三类都在比「文字写法」，而法律文书里**数字写错一位就是另一件事**。
# 实测（617 卷宗）OCRing 会在不同页把同一个数写成两版：应补税额 `6529346.56元` 在 p23/p27/p28
# 一致、到 p32 变成 `6592946.56元`；案号 `（20XX）粤XX民终XXXX号` 在 p13/p34 对、p18 掉了
# 一位成 `621号`。这两处**都不是「错字」**，前面的判据（差 1 个汉字 + 频次悬殊）看不见。
#
# 两道门都是 medium：只提示、不自动改正文（改数字比改错字危险得多）。

#: 案号：`（20XX）粤XX民终XXXX号` 形态。分四段捕获，用于「同法院 + 同年份 + 同案件类型」
#: 分桶——只有这三项都相同时，号码不同才可能是同一个案件被写错。
_CASE_NUMBER_RE = re.compile(
    r"[（(]\s*(?P<year>20\d{2})\s*[)）]\s*(?P<court>[\u4e00-\u9fff]{1,3}\d{0,4})"
    r"\s*(?P<kind>[\u4e00-\u9fff]{1,3})\s*(?P<num>\d{1,6})\s*号",
)

#: 金额：`1,234,567.89元`。**必须有 `元` 收尾**——没有单位的数字（页码、账号、
#: 流水号）一旦进来，噪声会盖掉真信号。
_AMOUNT_RE = re.compile(r"(?P<value>\d[\d,]{3,}(?:\.\d{1,2})?)\s*元")

#: 金额的角色标签白名单。只在**金额前 40 字内**出现这些词时才算「有角色」，
#: 否则这个金额不参与比对——“无角色的数字”根本不构成「同一条事实」。
_AMOUNT_LABEL_WINDOW = 40
_AMOUNT_LABELS = [
    "应补税额",
    "应补缴",
    "应补",
    "核定",
    "计税依据",
    "合同价",
    "交易价",
    "转让价",
    "合计金额",
    "合计",
    "本金",
    "利息",
    "罚息",
    "税额",
    "金额",
    "收入",
    "成本",
    "扣除",
    "余额",
    "补缴",
    "缴纳",
    "价款",
    "罚款",
    "滞纳金",
    "诉讼费",
]

#: 案号变体的判据：**短号码是长号码删掉 1–2 位得到的**（只认删除）。
#:
#: 只凭「同法院 + 同年 + 同类型」就两两报不行：同一法院同年的两个真实不同案件
#: （`民终6121号` 与 `民终6122号`）也会落进同一桶。实测的错法是**漏了一位**（`6121` → `621`），
#: 删除关系能把它与「替换一位」分开：6121/6122 不命中。
_CASE_SUFFIX_LEN_DIFF = 2

#: 金额变体的数值容差：同一长度的数字串最多差 2 位。
#: 一位之差是 OCR 最典型形态；2 位容下 `6529346` vs `6592946`（抄位 + 错位共 3 处，
#: 编辑距离 2）。再宽就会把「本来就是两个数」（一次交易的不同项）并进来。
_AMOUNT_MAX_EDIT_DISTANCE = 2

#: 多数派至少要出现这么多次。**这条是必需的，不是调优**：
#: 去掉它以后，那份 164 页银行催收卷宗会出 4 条假阳性
#: （`100000` vs `1310000`、`10020` vs `100000`、`11700` vs `11530`——全是两个真实存在
#: 的不同金额）。加上以后 4 条全滤掉，而 617 的真错仍在。
_AMOUNT_MAJORITY_MIN = 2

#: 姓名聚类的前缀长度（姓 + 名首字）。只同姓太松（同姓的人满卷都是），
#: 同姓又同名首字才像「同一个人的多种 OCR 写法」。
_NAME_PREFIX_LEN = 2

#: 一个前缀簇至少要有这么多种**不同写法**才提示。
#:
#: 2 种不行：`张三丰`(21) vs `张四丰`(15) 正是本模块开头警告的两个自然人，
#: 它们同角色、同长度、同前缀，只差最后一个字。要求 >=3 种写法，是因为
#: 「三个同姓同名首字的兄弟姐妹恰好都出现在同一个角色字段里」远比
#: 「一个人名被 OCR 认成三种样子」少见。真实卷宗里借款人正是 5 种写法各 1-2 页。
_CLUSTER_MIN_WRITINGS = 3

#: 一个前缀簇至少要跨这么多页才提示。同一页里同角色出现两个名字，
#: 更可能是「共有人/保证人并列」这两个真人，而不是跨页 OCR 变体。
_CLUSTER_MIN_PAGES = 2

#: 证件号字段名。与 ``_FIELD_NAMES`` 分开：证件号的值是数字串，不走中文片段判据。
#: 长名在前，避免 ``证件号`` 先匹配上 ``证件号码`` 的前缀再靠回溯纠正。
_ID_FIELD_NAMES = "公民身份号码 身份证号码 证件号码 身份证号 证件号".split()  # noqa: SIM905

#: 证件号取值。分隔符允许**缺失**：真实 OCR 常把冒号丢掉或换成空格
#: （实测同一卷宗里 `证件号码 440…` 与 `证件号码：440…` 两种形态都有）。
#: 尾部 ``(?![0-9Xx])`` 挡住「从更长的账号串里截前 18 位当证件号」。
#:
#: 角色名单独捕获：分隔符可缺失，所以**不能**像 ``_FIELD_VALUE_RE`` 那样按首个冒号
#: 切角色名——无冒号时会把整段「角色+号码」当成角色，每个号码各自一桶，永远配不上对。
_ID_VALUE_RE = re.compile(
    "(?P<role>%s)[：: \\t]*(?P<value>[0-9Xx]{15,18})(?![0-9Xx])" % "|".join(_ID_FIELD_NAMES),
)

#: 18 位身份证：前 17 位必须是数字，只有末位可以是 X。15 位旧证：全数字。
_ID_CARD_18_RE = re.compile(r"\d{17}[\dXx]")
_ID_CARD_15_RE = re.compile(r"\d{15}")


@dataclass(frozen=True)
class Inconsistency:
    """一处「同一段文字有两种写法」的疑似 OCR 错字。

    ``canonical`` 是高频写法（推荐的正确写法），``variant`` 是低频变体（疑似错字），
    ``pages`` 是变体出现过的页号（升序、去重）——律师要靠它翻回原页核对。
    ``confidence`` 在 ``kind=frequency`` 下恒为 ``"high"``：频次不够悬殊的根本不返回
    （宁可漏报，不可误报）。

    ``kind`` 区分判据来源，**只影响提示文案与置信度，不影响 canonical/variant 语义**：
    ``entity_cluster`` 的 canonical 只是「簇里出现页数最多的那种写法」，是**参照**
    而不是「判定为正确」——所以它给 medium，前端不会拿它自动改正文。
    """

    canonical: str
    variant: str
    canonical_count: int
    variant_count: int
    pages: list[int]
    confidence: str
    kind: str = KIND_FREQUENCY


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


def _field_role_of(match: re.Match[str]) -> str:
    """``_FIELD_VALUE_RE`` 匹配对应的角色名（冒号前那一段）。

    **前提：该正则的冒号是必需的**，所以首个冒号之前必然恰好是角色名。
    分隔符可缺失的正则（如 ``_ID_VALUE_RE``）不能用本函数，必须自己捕获角色名。

    不改 ``_FIELD_VALUE_RE`` 的分组结构：``_iter_candidates`` 依赖 ``group(1)`` 是值，
    把角色名改成捕获组会让它整体错位。
    """
    return re.split(r"[：:]", match.group(0), maxsplit=1)[0]


def _record_page_names(out: dict[str, dict[str, set[int]]], text: str, page_no: int, *, max_len: int) -> None:
    """把一页里所有角色字段值中的人名形态串记进 ``{角色: {值: 页号集合}}``。"""
    for match in _FIELD_VALUE_RE.finditer(text or ""):
        bucket = out.setdefault(_field_role_of(match), {})
        for piece in re.split(r"[ \t]+", match.group(1).strip()):
            value = _normalize(piece)[:max_len]
            if _looks_like_person_name(value):
                bucket.setdefault(value, set()).add(page_no)


def _role_name_pages(pages_text: dict[int, str], *, max_len: int) -> dict[str, dict[str, set[int]]]:
    """``{角色名: {人名形态值: 出现过的页号集合}}``。

    只收**角色字段值**里的人名形态串，不对正文滑窗——正文滑窗正是本模块开头
    记录的 1340 条噪声的来源。角色字段是闭集，天然把「这句话里恰好有个三字词」挡在外面。
    """
    out: dict[str, dict[str, set[int]]] = {}
    for page_no, text in pages_text.items():
        _record_page_names(out, text, int(page_no), max_len=max_len)
    return out


def _cluster_reference(group: list[str], value_pages: dict[str, set[int]], counts: Counter[str]) -> str:
    """簇里的**参照写法**：出现页数最多者，同页数按出现次数、再按字典序定序。

    叫参照而不叫 canonical 是因为这里没有「哪个对」的证据——簇里各写法频次接近，
    选它只是为了让输出稳定、让律师有个对照起点。
    """
    return min(group, key=lambda value: (-len(value_pages[value]), -counts[value], value))


def _cluster_group_hits(
    group: list[str],
    value_pages: dict[str, set[int]],
    counts: Counter[str],
    reported: set[tuple[str, str]],
) -> list[Inconsistency]:
    """一个前缀簇 → 参照写法与其余每种写法各一条候选提示。"""
    reference = _cluster_reference(group, value_pages, counts)
    hits: list[Inconsistency] = []
    for variant in group:
        if variant == reference or (reference, variant) in reported:
            continue
        hits.append(
            Inconsistency(
                canonical=reference,
                variant=variant,
                canonical_count=counts[reference],
                variant_count=counts[variant],
                pages=sorted(value_pages[variant]),
                confidence="medium",
                kind=KIND_ENTITY_CLUSTER,
            )
        )
    return hits


def _entity_cluster_hits(
    role_names: dict[str, dict[str, set[int]]],
    counts: Counter[str],
    reported: set[tuple[str, str]],
) -> list[Inconsistency]:
    """同一角色字段下，同一人的多种 OCR 写法 → 候选提示（不判对错）。

    补的是频次悬殊法的**结构性盲区**：借款人姓名在真实卷宗里有 5 种写法、各出现
    1-2 页，最大/最小频次比只有 2.0，永远过不了 ``PERSON_NAME_MIN_RATIO``（4 倍），
    也过不了 ``min_count``（3 次）。频次法只能抓到「高频正确 + 低频错字」这一种形态，
    而当事人姓名恰恰是「每种写法都很少」——法律上最关键，却最容易被漏掉。
    """
    hits: list[Inconsistency] = []
    for value_pages in role_names.values():
        # 预索引：同长度 + 同前缀才可能是一个人的多种写法，避免全量两两线性比对
        buckets: dict[tuple[int, str], list[str]] = defaultdict(list)
        for value in sorted(value_pages):
            buckets[(len(value), value[:_NAME_PREFIX_LEN])].append(value)
        for group in buckets.values():
            if len(group) < _CLUSTER_MIN_WRITINGS:
                continue
            covered = {page for value in group for page in value_pages[value]}
            if len(covered) < _CLUSTER_MIN_PAGES:
                continue
            hits.extend(_cluster_group_hits(group, value_pages, counts, reported))
    return hits


def _is_valid_id_card(value: str) -> bool:
    """证件号是否**结构合法**（只查形态，不查校验位）。

    18 位证的前 17 位必须是数字，只有末位可以是 X；15 位旧证全数字。
    OCR 把某一位数字认成字母（``4x0…``）时结构就坏了——这是不依赖频次的硬证据。
    """
    if len(value) == 18:
        return bool(_ID_CARD_18_RE.fullmatch(value))
    if len(value) == 15:
        return bool(_ID_CARD_15_RE.fullmatch(value))
    return False


def _two_drop_index(values: list[str]) -> dict[tuple[int, int, str], list[str]]:
    """``{(挖掉的两个位号, 剩余串): [原值]}``，用于 O(1) 找「至多差两位」的对方。

    同长度的两个值至多差 2 位 ⇔ 存在某两个位号，挖掉后两串完全相同。
    **位号必须进键**：只按剩余串建索引会让 `abcd` 与 `cdab` 撞上同一个键（实际差 4 位）。
    挖 2 位的索引天然覆盖「只差 1 位」（再随便挖一个相同位号即可），不必另建一份。
    """
    index: dict[tuple[int, int, str], list[str]] = defaultdict(list)
    for value in values:
        for left, right in combinations(range(len(value)), 2):
            index[(left, right, value[:left] + value[left + 1 : right] + value[right + 1 :])].append(value)
    return index


def _id_bucket_hits(
    bucket_pages: dict[str, set[int]],
    bucket_counts: Counter[str],
    reported: set[tuple[str, str]],
) -> list[Inconsistency]:
    """同一角色同一长度下，结构损坏的证件号 → 与它至多差 2 位的**唯一**合法证件号。

    为什么容忍 2 位而不是人名那样的 1 位：证件号有**结构合法性**这个硬证据
    （18 位证前 17 位必须是数字），损坏侧根本不可能是真证件号。问题不是「这两个写法
    是不是同一个人」，而是「OCR 把这个字段里的哪个合法号码认坏了」。实测 579 包那条
    损坏证件号与正确号差 2 位（一位数字被认成字母、另一位数字认错），1 位判据会漏掉它。

    为什么要求**唯一**候选：同一角色字段下可能并列多个自然人（借款人 + 配偶）。
    损坏号若与两个合法号都接近，就没有证据指认是哪一个——不猜，直接不报。
    """
    valid = sorted(value for value in bucket_pages if _is_valid_id_card(value))
    broken = sorted(value for value in bucket_pages if not _is_valid_id_card(value))
    index = _two_drop_index(valid)
    hits: list[Inconsistency] = []
    for bad in broken:
        candidates = {
            good
            for left, right in combinations(range(len(bad)), 2)
            for good in index.get((left, right, bad[:left] + bad[left + 1 : right] + bad[right + 1 :]), [])
        }
        # 0 个 = 无证据；>1 个 = 歧义。两种都不报。
        if len(candidates) != 1:
            continue
        good = candidates.pop()
        if (good, bad) in reported:
            continue
        hits.append(
            Inconsistency(
                canonical=good,
                variant=bad,
                canonical_count=bucket_counts[good],
                variant_count=bucket_counts[bad],
                pages=sorted(bucket_pages[bad]),
                confidence="medium",
                kind=KIND_ID_MALFORMED,
            )
        )
    return hits


def _id_card_hits(pages_text: dict[int, str], reported: set[tuple[str, str]]) -> list[Inconsistency]:
    """同一证件号字段下，结构损坏的写法 vs 结构合法的写法（差 1 位）→ 提示。

    **只报「一侧结构非法」**，不报「两侧都合法但差一位」：后者可能是两个自然人
    （证件号相邻发号）或校验位歧义，没有硬证据就不猜。同理不做编辑距离 >1 的匹配。
    """
    pages_by: dict[tuple[str, int], dict[str, set[int]]] = defaultdict(dict)
    counts_by: dict[tuple[str, int], Counter[str]] = defaultdict(Counter)
    for page_no, text in pages_text.items():
        for match in _ID_VALUE_RE.finditer(text or ""):
            value = match.group("value")
            key = (match.group("role"), len(value))
            pages_by[key].setdefault(value, set()).add(int(page_no))
            counts_by[key][value] += 1

    hits: list[Inconsistency] = []
    for key, bucket_pages in pages_by.items():
        hits.extend(_id_bucket_hits(bucket_pages, counts_by[key], reported))
    return hits


def _is_case_number_deletion(reference: str, variant: str) -> bool:
    """短号码是不是长号码**删掉 1–2 位数字**得到的（只认删除，不认替换）。

    `6121` vs `621` 命中（掉的是中间那位）；`6121` vs `6122` 不命中
    （同年同类的两个真实案件，形态是替换而不是删除）。

    只认删除是刻意的：OCR 把一位数字**漏掉**是实测到的唯一形态，而替换一位
    恰恰是两个相邻案件号最自然的差异（`…6121号` / `…6122号`）。放进来就再也分不开。
    """
    longer, shorter = (reference, variant) if len(reference) >= len(variant) else (variant, reference)
    if not (1 <= len(longer) - len(shorter) <= _CASE_SUFFIX_LEN_DIFF):
        return False
    cursor = 0
    for digit in longer:
        if cursor < len(shorter) and digit == shorter[cursor]:
            cursor += 1
    return cursor == len(shorter)


def _case_number_hits(pages_text: dict[int, str], reported: set[tuple[str, str]]) -> list[Inconsistency]:
    """同一「法院 + 年份 + 案件类型」下短号码是长号码删除 1–2 位的产物 → 提示。

    分两层收窄：先用「法院 + 年份 + 案件类型」分桶（同一法院同年的不同案件不上同桶），
    桶内再要求「删除关系」（`6121` → `621` 是漏了一位，这是实测到的错法形态）。
    只凭分桶两两报不行——`民终6121号` 与 `民终6122号` 是同年同类的两个真实案件。
    """
    buckets: dict[tuple[str, str, str], dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    display: dict[str, str] = {}
    for page_no, text in pages_text.items():
        for match in _CASE_NUMBER_RE.finditer(text or ""):
            key = (match.group("year"), match.group("court"), match.group("kind"))
            num = match.group("num")
            buckets[key][num].add(int(page_no))
            display[num] = match.group(0).strip()

    hits: list[Inconsistency] = []
    for (year, court, kind), by_num in buckets.items():
        if len(by_num) < 2:
            continue
        ordered = sorted(by_num, key=lambda n: (-len(by_num[n]), n))
        reference = ordered[0]
        ref_name = display[reference]
        for variant in ordered[1:]:
            if not _is_case_number_deletion(reference, variant):
                continue
            var_name = display[variant]
            if (ref_name, var_name) in reported:
                continue
            hits.append(
                Inconsistency(
                    canonical=ref_name,
                    variant=var_name,
                    canonical_count=len(by_num[reference]),
                    variant_count=len(by_num[variant]),
                    pages=sorted(by_num[variant]),
                    confidence="medium",
                    kind=KIND_CASE_NUMBER,
                )
            )
    return hits


def _amount_label_of(text: str, start: int) -> str:
    """金额前 40 字内最靠近的角色标签；没有则空串。"""
    context = text[max(0, start - _AMOUNT_LABEL_WINDOW) : start]
    label, best = "", -1
    for candidate in _AMOUNT_LABELS:
        pos = context.rfind(candidate)
        if pos > best:
            label, best = candidate, pos
    return label


def _digits(value: str) -> str:
    return re.sub(r"[,\s]", "", value)


def _amount_hits(pages_text: dict[int, str], reported: set[tuple[str, str]]) -> list[Inconsistency]:
    """同一角色标签下，数值只差几位 → 提示（不判哪个对）。

    两道阀门：同标签（金额所属的法律含义相同）+ 多数派出现 ≥2 次（真有一个「一致写法」
    存在）。只剩一道都不行：只要标签会把「一笔交易的不同项」塞进同一桶；
    只要多数派会让两个各出现一次的真不同金额两两相撞。
    """
    buckets: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    display: dict[str, str] = {}
    for page_no, text in pages_text.items():
        body = text or ""
        for match in _AMOUNT_RE.finditer(body):
            label = _amount_label_of(body, match.start())
            if not label:
                continue
            value = _digits(match.group("value"))
            buckets[label][value].add(int(page_no))
            display.setdefault(value, f"{match.group('value').strip()}元")

    hits: list[Inconsistency] = []
    for _label, by_value in buckets.items():
        if len(by_value) < 2:
            continue
        for canonical, variant in _amount_pairs(by_value):
            ref_name, var_name = display[canonical], display[variant]
            if (ref_name, var_name) in reported:
                continue
            hits.append(
                Inconsistency(
                    canonical=ref_name,
                    variant=var_name,
                    canonical_count=len(by_value[canonical]),
                    variant_count=len(by_value[variant]),
                    pages=sorted(by_value[variant]),
                    confidence="medium",
                    kind=KIND_AMOUNT,
                )
            )
    return hits


def _amount_pairs(by_value: dict[str, set[int]]) -> list[tuple[str, str]]:
    """一个标签桶里所有「多数派 vs 少数派」的近似数值对。"""
    ordered = sorted(by_value, key=lambda v: (-len(by_value[v]), len(v), v))
    pairs: list[tuple[str, str]] = []
    for index, canonical in enumerate(ordered):
        if len(by_value[canonical]) < _AMOUNT_MAJORITY_MIN:
            continue
        for variant in ordered[index + 1 :]:
            if len(variant) != len(canonical):
                continue
            if _digit_edit_distance(canonical, variant) <= _AMOUNT_MAX_EDIT_DISTANCE:
                pairs.append((canonical, variant))
    return pairs


def _digit_edit_distance(left: str, right: str) -> int:
    """两个同长度数字串的编辑距离（保留小数点，使 `.56` 与 `.65` 也算差异）。"""
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, 1):
        current = [i]
        for j, char_right in enumerate(right, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (char_left != char_right),
                )
            )
        previous = current
    return previous[-1]


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
        字典序。含三种 ``kind``：``frequency``（high）与实体感知的
        ``entity_cluster`` / ``id_malformed``（medium，只提示不判对错）。
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

    # 实体感知判据：补频次法的结构性盲区（当事人姓名各写法都很少、证件号结构损坏）。
    # 跳过频次法已报过的同一对写法，避免同一处刷两条。
    reported = {(item.canonical, item.variant) for item in hits}
    role_names = _role_name_pages(pages_text, max_len=max_len)
    hits.extend(_entity_cluster_hits(role_names, counts, reported))
    hits.extend(_id_card_hits(pages_text, reported))
    # 数字类：案号与金额写成了两个版本。前面三类都比「文字写法」，看不见数字错位。
    for hit in _case_number_hits(pages_text, reported) + _amount_hits(pages_text, reported):
        reported.add((hit.canonical, hit.variant))
        hits.append(hit)

    return sorted(hits, key=lambda item: (-item.variant_count, item.canonical, item.variant))
