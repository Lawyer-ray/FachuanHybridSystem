"""页级取字退化检测：判断「这一页的字是不是废的」。

## 为什么需要独立一层

取字链路里「成功」的判据一直是「有没有字」。但云端视觉模型有两种**有字却不可用**的
输出形态，它们都能骗过「有字 = 成功」：

1. **复读循环**：同一段话重复到输出上限（实测 617 卷宗 p1、p8、p33 都是这样，
   一页吐出 13653–17327 字，其中 98% 是同一句话）。
2. **空返回**：`finish_reason=stop` 但正文是空串（实测 164 页银行档案里一次出现 11 页）。

两种都会让这一页的正文变成垃圾或空白，而任务状态是成功的、分段可能还给了高置信度。
所以必须有一层显式判据，把「有字」与「可用」分开——`OCRPageResult.ocr_failed` 只覆盖
「一个字都没有」，覆盖不到复读。

## 判据与它们的实测依据

三份真实扫描卷宗（37 / 93 / 164 页）上校准，**只有下面三条**：

| 判据 | 依据 |
|---|---|
| 正文为空 | 空串无可争辩 |
| 同一行重复 ≥ 5 次（行长 ≥ 8） | 复读的最小形态；5 次在真实表格页里不会出现（银行流水最多同一行 3 次） |
| **窗口去重比 < 0.25**（只看含 ≥12 汉字的 40 字窗口） | 抓到「整页只有一行、行内反复吐同一句话」的形态（617 的 p8 就是这样：13653 字只有 1 行）。只看行重复抓不到它 |
| `finish_reason != "stop"` **且** 唯一行比例 < 0.5 | 被输出上限截断 + 内容大半重复 = 循环；只截断不重复的正文仍然可用，不能判死 |

**刻意没有「字数太多 = 坏页」这条。** 曾经用过 `len(text) > 5000`，在 164 页银行流水上
把 4 页**完全正常**的交易明细（6300–7500 字、唯一行比例 1.00）全判成坏，由此得出
「退化率 42%」的错误结论；换成上面三条后真实首跑退化率是 20.7%。密度高的表格页本来
就字多，字数不是证据。

## 两类失败的可修复性不同（决定了修补策略）

- **空返回是瞬时的**：164 页上 11 页空返回，同一请求重试一次 **11/11 全部恢复**。
- **复读是半瞬时**：可能重试就好，也可能三次都坏。实测单页换 purpose 重试能救
  65%–71% 的残余。

所以上层修补顺序应当是：先重试（便宜），再换 purpose（有效），最后换引擎（兜底）。
本模块只回答「这页坏不坏」，不决定怎么修。

## 为什么不用「唯一行比例」一条兜到底

表格页天然重复（`</td><td>` 之类），用整页唯一行比例会把正常表格判死。所以行重复
判据要求**同一条非短行**重复，而不是看整体比例；`finish_reason` 那条也只在被截断时才
启用比例判据。两条都收窄到「除了循环没有别的解释」为止。
"""

from __future__ import annotations

import re

__all__ = [
    "degeneracy_reason",
    "has_usable_text",
    "is_degenerate",
    "strip_cloud_markers",
]

#: 云端视觉模型（DeepSeek `rich_layout_recognition`）在正文里夹的标记：
#: ``〈｜ref｜〉〈｜box｜〉[[x1,y1,x2,y2]]〈｜/box｜〉〈｜/ref｜〉``。
#:
#: 分隔符是**全角竖线 U+FF5C**，不是 ASCII `|`——按文档里的半角写法写正则会一条都匹配
#: 不到。标签之间还夹着块类型词（`image` / `text` / `title` …），它们不是正文：
#: 剥掉标签后会残留成「有 5 个字」，让「整页就是一张图」的页被误判成有正文
#: （实测 617 的 EMS 面单页就是这样漏过修补的）。
_MARKER_TAG_RE = re.compile(r"<[^>]*>")
_COORD_RE = re.compile(r"\[\[\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*\]\]")
_BLOCK_TYPE_WORD_RE = re.compile(
    r"\b(?:image|figure|text|title|table|header|footer|page_number|caption|equation|list|ref|box)\b",
    re.IGNORECASE,
)

#: 判定「有可用正文」的最小有效字符数。1–3 个字符在真实卷宗里只会是页码/水印残渣。
_USABLE_MIN_CHARS = 4

#: 同一行重复到这个次数就算复读。5 是实测下限：真实银行流水同一行最多出现 3 次。
_SAME_LINE_REPEAT_MIN = 5

#: 参与重复判据的最短行长。太短的行（`1` / `---` / `|`）在表格页里天然高频。
_SAME_LINE_MIN_LEN = 8

#: 被输出上限截断时，唯一行比例低于这个值才认定是循环。
#: 0.5 的依据：确认是循环的实测样本唯一行比例在 0.00–0.31，正常表格页在 0.98–1.00。
_LOOP_UNIQUE_LINE_RATIO = 0.5

#: 行内复读检测：不重叠切 40 字窗口，看「去重后的窗口 / 总窗口」这个比值。
#:
#: 为什么需要它：617 的 p8 是**一整行 13653 字**反复吐同一句话——行重复判据失效
#: （只有 1 行）、唯一行比例也失效（=1.00）。不补这条就会漏掉真实复读。
#:
#: 为什么不数「某个窗口出现几次」：那样会把**合法银行流水**判死。实测某 93 页卷宗的 p80/p81
#: 是 8550/9039 字的真实交易明细，但 `<td>账号</td><td>银联无卡快捷业务联机待清</td>`
#: 这段结构串在每行都出现，单个窗口数到 18 次就误判。改看去重比后：该页 0.89–0.97，
#: 真循环页 0.01–0.15，分离度很大。
_REPEAT_WINDOW = 40
#: 只统计含这么多汉字的窗口：排掉纯标记/纯数字串/点号引导线（目录页）
#: ——它们天然重复，与复读无关。
_REPEAT_WINDOW_MIN_CJK = 12
#: 符合条件的窗口少于这么多个就不判（银行流水页汉字少，本来就不该用这条判）。
_REPEAT_WINDOW_MIN_COUNT = 10
#: 去重比低于这个值判循环。真循环实测 0.01–0.15，正常页 0.89–1.00。
_REPEAT_RATIO_MAX = 0.25

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def strip_cloud_markers(text: str | None) -> str:
    """剥掉云端标记 / 坐标 / HTML 标签与块类型词，只留正文。

    不剥 HTML 标签的后果：表格页的 `<td>` 会被当成正文，让空表也算「有字」。
    """
    body = _COORD_RE.sub(" ", _MARKER_TAG_RE.sub(" ", text or ""))
    return _BLOCK_TYPE_WORD_RE.sub(" ", body)


def has_usable_text(text: str | None) -> bool:
    """这一页剥掉标记后是否还有像正文的东西。

    用于「整页就是一张图」这种形态：云端会返回「整页一个 image 块 + 全页坐标」，
    有字（是标记）但没有任何正文。
    """
    body = re.sub(r"[\s\W_]+", "", strip_cloud_markers(text))
    return len(body) >= _USABLE_MIN_CHARS


def degeneracy_reason(text: str | None, finish_reason: str | None = None) -> str:
    """判断这一页的取字结果是否不可用。

    Args:
        text: 该页正文（云端原样输出，不必清洗）。
        finish_reason: 云端给的结束原因；非 ``"stop"`` 表示被输出上限截断。
            不传 / None 时只按文本判据——其它引擎没有这个字段，行为不受影响。

    Returns:
        空串表示可用；否则是**给人看的原因**（会进日志与 summary，所以写成中文短语）。
    """
    body = text or ""
    if not body.strip():
        return "空返回"

    lines = [line.strip() for line in body.splitlines() if line.strip()]
    repeated = 0
    if lines:
        counts: dict[str, int] = {}
        for line in lines:
            if len(line) < _SAME_LINE_MIN_LEN:
                continue
            counts[line] = counts.get(line, 0) + 1
        repeated = max(counts.values(), default=0)
    if repeated >= _SAME_LINE_REPEAT_MIN:
        return f"同一行重复 {repeated} 次"

    window_ratio = _window_dedupe_ratio(body)
    if window_ratio is not None and window_ratio < _REPEAT_RATIO_MAX:
        return f"同一段话反复重复（窗口去重比 {window_ratio:.0%}）"

    if finish_reason and finish_reason != "stop":
        unique_ratio = len(set(lines)) / len(lines) if lines else 0.0
        if unique_ratio < _LOOP_UNIQUE_LINE_RATIO:
            return f"被截断且内容重复（唯一行 {unique_ratio:.0%}）"
        # 只是撞了输出上限、内容并不重复：正文可用，不判死。
        return ""

    if not has_usable_text(body):
        return "只有标记没有正文"
    return ""


def _window_dedupe_ratio(text: str) -> float | None:
    """含足够汉字的 40 字窗口的去重比；窗口太少时返回 ``None``（= 不判）。

    不重叠切窗而不是滑窗：滑窗会把「一个重复片段」摊成几百个相邻窗口，
    让比值失去区分度，还变成 O(n²)。
    """
    windows = [
        text[start : start + _REPEAT_WINDOW] for start in range(0, max(0, len(text) - _REPEAT_WINDOW), _REPEAT_WINDOW)
    ]
    windows = [w for w in windows if len(_CJK_RE.findall(w)) >= _REPEAT_WINDOW_MIN_CJK]
    if len(windows) < _REPEAT_WINDOW_MIN_COUNT:
        return None
    return len(set(windows)) / len(windows)


def is_degenerate(text: str | None, finish_reason: str | None = None) -> bool:
    """``degeneracy_reason`` 的布尔形态（调用方不关心原因时用）。"""
    return bool(degeneracy_reason(text, finish_reason))
