"""页面质量画像的**聚合**：逐页 `assess_page_quality` → summary 里那一块字典。

判据本身不在这里（在 `page_quality.py`）：本模块只做编排——把每页调一遍、
按 kind 分桶、把 ``reason`` 原样搬进 ``details``。这样判据怎么改都只影响一张表，
接入层不跟着动。

## 为什么不阻塞流程

页面质量只写进 summary，**不拦任务、不改分段、不打回重跑**：

- 判据是启发式（字数 + 有没有成句中文 + 有没有 image 块）。被判成 graphic 的页
  大多数确实是图纸/印章/照片，但证件页、短通知页也会落进 sparse。拿它拦流程，
  律师会遇到「明明 164 页都读出来了，任务却说失败」。
- 律师要的是「这一页别只看我给的 Markdown，去翻原图」。这是个**提示**，不是结论，
  更不是校验门禁。提示必须在结果里看得见，而不是把结果扣住。
- 误报的代价不对称：漏报 → 律师照常读、没被提醒；误拦 → 整份卷宗用不成了。
  所以只提示、不阻断。

## 两阶段链路怎么带过去

`summary["page_quality"]` 在**取字阶段**算出来，`quality_flags` 却要在**分段阶段**
写到段上——两个阶段是两个 Django-Q 任务，中间只靠 job 目录里的文件传递。
所以聚合结果必须落盘（`PdfSplitStorage.page_quality_json_path`），分段阶段读回来用。
只写 DB summary 的话，分段阶段拿不到，`quality_flags` 会永远是空的。
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .doc_type import missing_expected_fields
from .page_quality import PageQuality, assess_page_quality

#: 逐页判定的 kind → summary 里的分桶键。两者同名，但**显式列出来**：
#: 判据层将来加 kind 时，这里没跟上的话会直接在下面 KeyError，而不是静默丢页。
_KIND_BUCKETS = ("graphic", "sparse", "blank")


def build_page_quality_summary(pages: list[Any]) -> dict[str, Any]:
    """逐页判定 → summary 区块。

    Args:
        pages: ``PageDescriptor`` 列表（也可传 ``{page_no, text, layout}`` 形式的有
            ``layout`` 属性的对象）。

    Returns:
        ``{"graphic_pages": [...], "sparse_pages": [...], "blank_pages": [...],
        "details": {"147": "疑似图形页（图纸/印章/照片），请核对原图"},
        "doc_hints": {"23": "id_card"}}``

        ``details`` 只收 ``needs_visual_review`` 为真的页——那是「这一页 Markdown
        不足以自证内容，请翻原图」的页。正常文本页不写进 details，否则 164 页
        全被列一遍，等于没提示。

        ``doc_hints`` 比 ``details`` 宽一档：凡是认得出材料类型的页都列（含 sparse），
        给前端一个**可选**的「这页是身份证」标签。判据层已经保证只有 sparse / graphic
        会带 ``doc_hint``，所以这里不必再按 kind 过滤。
    """
    buckets: dict[str, list[int]] = {kind: [] for kind in _KIND_BUCKETS}
    details: dict[str, str] = {}
    doc_hints: dict[str, str] = {}
    doc_missing: dict[str, dict[str, Any]] = {}

    for page in pages:
        page_no = int(getattr(page, "page_no", 0))
        if page_no <= 0:
            continue
        quality = assess_page_quality(
            page_no=page_no,
            text=str(getattr(page, "text", "") or ""),
            layout=getattr(page, "layout", None),
        )
        if quality.kind in buckets:
            buckets[quality.kind].append(page_no)
        if quality.needs_visual_review:
            # 文案直接用判据层给的 reason，接入层不再造一套说法
            details[str(page_no)] = quality.reason
        if quality.doc_hint:
            doc_hints[str(page_no)] = quality.doc_hint
            # 结构化透出「该有但没有」的字段名，供前端列「待补录清单」。
            #
            # 为什么不复用 details 里那句自然语言：前端要按字段名呈现成列
            # （「缺：姓名 / 身份证号 / 住址」），从中文句子里正则切字段名
            # 是脆的 —— 后端改一个字前端就瞎。所以这里给结构化数据。
            #
            # missing 为空数组也照样出现：类型认出来了但字段都在时，律师
            # 仍值得知道「这页是身份证」（p42 那种满是乱码的情况尤其如此）。
            doc_missing[str(page_no)] = {
                "doc": quality.doc_hint,
                "missing": missing_expected_fields(quality.doc_hint, str(getattr(page, "text", "") or "")),
            }

    return {
        "graphic_pages": sorted(buckets["graphic"]),
        "sparse_pages": sorted(buckets["sparse"]),
        "blank_pages": sorted(buckets["blank"]),
        "details": details,
        "doc_hints": doc_hints,
        "doc_missing": doc_missing,
    }


def qualities_by_page(pages: list[Any]) -> dict[int, PageQuality]:
    """``{页号: PageQuality}``：分段阶段给每段贴 flag 时按页号查。

    与 :func:`build_page_quality_summary` 复用同一个判据入口，但保留完整对象
    （分段阶段要 kind 和 reason，不只是页号分桶）。
    """
    result: dict[int, PageQuality] = {}
    for page in pages:
        page_no = int(getattr(page, "page_no", 0))
        if page_no <= 0:
            continue
        result[page_no] = assess_page_quality(
            page_no=page_no,
            text=str(getattr(page, "text", "") or ""),
            layout=getattr(page, "layout", None),
        )
    return result


def serialize_quality(
    *,
    summary: dict[str, Any],
    qualities: dict[int, PageQuality],
) -> dict[str, Any]:
    """落盘载荷：summary 区块 + 逐页画像（分段阶段据此贴 flag）。

    两者一起存而不是分成两个文件：``details`` 的文案就是逐页 ``reason``，
    分开存迟早会对不上（segments_md.json 的正文与 positioned 同源同文件，
    也是同一个理由）。
    """
    return {
        **summary,
        "pages": {str(page_no): asdict(quality) for page_no, quality in sorted(qualities.items())},
    }
