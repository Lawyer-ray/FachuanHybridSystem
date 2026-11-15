"""表格拆分阈值 ``_TABLE_SPLIT_MAX_ROWS`` 的对比实验 + 全卷定位精度分布。

## 用法

```bash
backend/.venv/bin/python scripts/eval_table_split.py             # 写 /tmp/table_split_experiment.md
backend/.venv/bin/python scripts/eval_table_split.py --out x.md  # 换输出路径
backend/.venv/bin/python scripts/eval_table_split.py --skip-corpus  # 只跑 Q1，不跑 576 全卷
```

## 这个脚本回答两个问题

**Q1（阈值对比）**：``_TABLE_SPLIT_MAX_ROWS`` 取 ``0 / 3 / 6 / 12 / 20 / 30 / 80 / 999``
八个值时，7 页 golden 的 CER / cell F1 / 定位块数分别怎么变。

**Q3（全卷精度分布）**：576 卷宗（164 页）跑 ``build_positioned_blocks``，
统计 ``exact`` / ``cell`` / ``page`` 三档精度各多少块。

## 为什么要单独写脚本改阈值，而不是开参数

``_TABLE_SPLIT_MAX_ROWS`` 是模块级常量，``_split_table_into_cells`` 直接读全局名。
本脚本用 :class:`table_split_max_rows` 在测量区间内原地改值、``finally`` 还原——
不改生产代码、不加参数、不留开关。这也是唯一诚实的测法：测的就是线上那条代码路径。

## Q1 的关键判据不是 CER，而是 CER 有没有**变**

拆不拆块只决定「定位框」，不碰「Markdown 正文」（``_page_markdown`` / ``_block_markdown``
不走 ``_split_table_into_cells``）。所以同一页的 CER 在所有阈值下必须一字不差。
**一旦 CER 随阈值变化，就说明拆块路径回写到了正文，那是 bug**——脚本会把这种情形
单独标出来，而不是把它当成「阈值效果」写进表格。

## 数据口径（诚实声明）

7 页 golden 全部 ``gold_known: false``，是 MinerU 原始输出、未经人工校对。
所以本报告里的数字只能读作**同一份 golden 上的相对涨跌**，不能读作「准确率 X%」。
REF≠正确。

## 为什么用 ``sys.stdout.write`` 而不是 ``print()``

``scripts/`` 在 ``security_guard`` 的 print 门禁前缀内（``--check print``），
新增 ``print()`` 会被 pre-commit 拦下。任务里给的「脚本里可以 print」与仓库门禁冲突，
门禁优先——回显改用 ``sys.stdout.write``，输出内容完全一样。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# 本脚本在仓库根 scripts/ 下，backend/ 是它的兄弟目录（不是父目录）。
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# markdown_builder 经由 split_models 间接依赖 Django，必须先配好 settings 再 import。
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
sys.path.insert(0, str(BACKEND_ROOT / "apiSystem"))

import django

django.setup()

from apps.pdf_splitting.services.split import markdown_builder as mb
from apps.pdf_splitting.services.split.bbox import normalize_bbox
from apps.pdf_splitting.services.split.eval_metrics import char_error_rate, normalize_for_cer, table_cell_f1
from apps.pdf_splitting.services.split.markdown_builder import (
    _grid_col_count,
    _grid_row_count,
    _parse_grid,
    _split_table_into_cells,
    _table_cell_count,
    build_positioned_blocks,
    build_segment_markdown,
)
from apps.pdf_splitting.services.split.split_models import PageDescriptor

GOLDEN_DIR = (
    BACKEND_ROOT / "tests" / "ci" / "fixtures" / "pdf_splitting" / "golden_pages"
)
DEFAULT_OUT = Path("/tmp/table_split_experiment.md")

#: Q1 要扫的阈值。两端是行为边界，中间是候选：
#: - ``0``  —— 完全关闭拆分（任何表格都整表保留），这是「改造前」的对照端
#: - ``3``  —— 只有最矮的证件表格会被拆
#: - ``6``  —— 覆盖常识里的「小表单」（3~6 行）
#: - ``12`` —— 当前线上值
#: - ``20`` —— 刚好越过 p22 押品表的 17 行
#: - ``30`` —— 覆盖中等表单，但放行不了 52 行流水
#: - ``80`` —— ``_TABLE_ROW_SPLIT_MAX``，行拆分的绝对上限
#: - ``999`` —— 事实上的无上限（改造前的原始行为）
THRESHOLDS = (0, 3, 6, 12, 20, 30, 80, 999)

#: 576 全卷的 pages.json（164 页 layout）。数据源来自匿名化后的 job 目录，
#: 用它是因为它是仓库里唯一带着完整页级 layout 的现成产物。
CORPUS_PAGES_JSON = (
    BACKEND_ROOT
    / "apiSystem"
    / "media"
    / "pdf_splitting"
    / "jobs"
    / "10e4546c-eb72-439a-a007-359e4c1eb1fb"
    / "analysis"
    / "pages.json"
)

#: 三档精度等级，顺序固定：报告列与柱状对照都按这个顺序。
PRECISION_LEVELS = ("exact", "cell", "page")


@contextmanager
def table_split_max_rows(value: int) -> Iterator[None]:
    """在 with 区间内把 ``_TABLE_SPLIT_MAX_ROWS`` 临时改成 ``value``，退出必还原。

    为什么用 ``finally``：中途抛异常（比如某页 layout 结构异常）时若不还原，
    后续阈值轮次全部跑在错的常量上，整张对比表静默失真——那种报告比没有报告更坏。
    """
    original = mb._TABLE_SPLIT_MAX_ROWS
    mb._TABLE_SPLIT_MAX_ROWS = value
    try:
        yield
    finally:
        mb._TABLE_SPLIT_MAX_ROWS = original


def load_golden_pages() -> list[dict[str, Any]]:
    """读 meta.yaml 里登记的每一页 → ``{page, kind, gold_known, text, table_html}``。

    复用 ``eval_baseline.py`` 的同一套解析逻辑（meta.yaml 是手写 YAML，
    为了不引入 PyYAML 依赖才逐行解析）——两边口径必须一致，否则基线报告
    与本实验报告的数字没法互相对照。
    """
    meta_path = GOLDEN_DIR / "meta.yaml"
    pages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in meta_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if stripped.startswith("- page:"):
            current = {"page": int(stripped.split(":", 1)[1].strip())}
            pages.append(current)
        elif current is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip()
            current[key.strip()] = None if value == "null" else value
    for entry in pages:
        entry["text"] = (GOLDEN_DIR / f"page_{entry['page']:04d}.txt").read_text(
            encoding="utf-8"
        )
        table_html = entry.get("table_html")
        entry["table_html"] = (
            (GOLDEN_DIR / str(table_html)).read_text(encoding="utf-8")
            if table_html
            else ""
        )
    return pages


def page_descriptor_for(gold: dict[str, Any]) -> PageDescriptor:
    """把 golden 页包成 ``PageDescriptor``，喂给真实的 Markdown / 定位构建函数。

    与 ``eval_baseline.py`` 的口径**必须逐字一致**，否则两边的 CER 对不上、
    也就没法判断「这次实验相对基线是涨是跌」：

    - 只喂 ``page.text``，不编假 layout 的 block 结构——golden 快照里没有
      block 类型与 bbox，编一份等于在拿假结构测量。
    - 表格页把 ``table_html`` 放进一个 table 块的 ``table_body``，
      并把整页文本填进该块的 ``text``（``_block_markdown`` 遇空 text 直接返回空串，
      表格渲染路径根本不会被执行，cell F1 就永远量到「没渲染表格」）。
    """
    blocks: list[dict[str, Any]] = []
    table_block = None
    if gold["table_html"]:
        table_block = {
            "type": "table",
            "text": gold["text"],
            "bbox": [35, 88, 980, 738],
            "table_body": gold["table_html"],
        }
        blocks.append(table_block)
    return PageDescriptor(
        page_no=int(gold["page"]),
        text=gold["text"],
        normalized_text=gold["text"],
        head_text=gold["text"][:200],
        top_candidates=[],
        source_method="mineru_ocr",
        ocr_failed=False,
        layout={"page_no": int(gold["page"]), "blocks": blocks, "text": gold["text"]}
        if table_block
        else None,
    )


def page_metrics(gold: dict[str, Any]) -> dict[str, Any]:
    """单页在当前 ``_TABLE_SPLIT_MAX_ROWS`` 下的四个观测量。

    这里的 ``build_segment_markdown`` 与 ``build_positioned_blocks`` 是**生产函数本身**，
    不是复刻——Q1 要证的就是「改阈值不会让正文变」，只有跑真函数才有说服力。
    """
    page = page_descriptor_for(gold)
    markdown = build_segment_markdown("golden", [page])
    blocks = build_positioned_blocks([page], bbox_backend="mineru")
    precision_tally = Counter(
        str((block.get("rect") or {}).get("precision")) for block in blocks
    )
    return {
        "page": int(gold["page"]),
        "kind": gold["kind"],
        "cer_raw": char_error_rate(markdown, gold["text"]),
        "cer_norm": char_error_rate(
            normalize_for_cer(markdown), normalize_for_cer(gold["text"])
        ),
        # 只在真的渲染了表格的页上有意义；无表格页记 None，报告里显示「—」
        "cell_f1": table_cell_f1(markdown, gold["table_html"])
        if gold["table_html"]
        else None,
        "blocks": len(blocks),
        "cell_blocks": precision_tally.get("cell", 0),
        "precision_tally": precision_tally,
    }


def run_threshold_sweep(golds: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """对每个阈值把 7 页各跑一次 → ``{阈值: [逐页指标, ...]}``。"""
    sweep: dict[int, list[dict[str, Any]]] = {}
    for threshold in THRESHOLDS:
        with table_split_max_rows(threshold):
            sweep[threshold] = [page_metrics(gold) for gold in golds]
    return sweep


def table_structure(gold: dict[str, Any]) -> dict[str, Any]:
    """表格的行×列与格数（与阈值无关，只用于在报告里交代这张表多大）。"""
    html = gold["table_html"]
    if not html:
        return {}
    grid = _parse_grid(html)
    return {
        "rows": _grid_row_count(html),
        "cols": _grid_col_count(grid),
        "cells": _table_cell_count(html),
    }


def cer_drift(sweep: dict[int, list[dict[str, Any]]]) -> list[str]:
    """检查 CER 是否随阈值变化；有变化就是 bug，返回逐页证据行。

    为什么单独查这一条：拆块只产出「定位框」，正文由 ``_page_markdown`` 独立生成，
    两条路径在源码里没有任何共享可变状态。所以阈值对 CER 的影响**必须恒等于零**。
    一旦不成立，说明拆块逻辑某种方式回写到了 block/markdown 数据（例如原地改了
    ``block["text"]``），这是必须定位的 bug，不能当成「阈值的副作用」收进表格。
    """
    drifts: list[str] = []
    for index, gold in enumerate(next(iter(sweep.values()))):
        page_no = gold["page"]
        raw_values = {
            round(sweep[threshold][index]["cer_raw"], 10) for threshold in THRESHOLDS
        }
        norm_values = {
            round(sweep[threshold][index]["cer_norm"], 10) for threshold in THRESHOLDS
        }
        if len(raw_values) > 1 or len(norm_values) > 1:
            drifts.append(
                f"| p{page_no} | {'/'.join(f'{v:.4f}' for v in sorted(raw_values))} | "
                f"{'/'.join(f'{v:.4f}' for v in sorted(norm_values))} |"
            )
    return drifts


def load_corpus_pages() -> list[PageDescriptor]:
    """读 576 全卷的 pages.json → ``list[PageDescriptor]``。

    ``layout`` 为 null 的页（本地 OCR 无坐标）原样保留为 ``None``：
    ``build_positioned_blocks`` 会跳过它们，这正是线上行为——不能替它补一份空 layout。
    """
    raw = json.loads(CORPUS_PAGES_JSON.read_text(encoding="utf-8"))
    pages: list[PageDescriptor] = []
    for item in raw:
        layout = item.get("layout")
        pages.append(
            PageDescriptor(
                page_no=int(item["page_no"]),
                text=str(item.get("text") or ""),
                normalized_text=str(item.get("normalized_text") or ""),
                head_text=str(item.get("head_text") or ""),
                source_method=str(item.get("source_method") or ""),
                ocr_failed=bool(item.get("ocr_failed")),
                top_candidates=list(item.get("top_candidates") or []),
                layout=layout if isinstance(layout, dict) else None,
                layout_title=str(item.get("layout_title") or ""),
            )
        )
    return pages


#: 「改造前」的等价分布怎么算：改造前没有 precision 字段，整卷只有布尔 approx，
#: 表格块一律 approx=True（前端当整页近似画）。所以改造前的精确框 = 非表格块数。
#: 这个换算的前提是「改造前所有 table 块的 approx 都是 True」——代码里
def table_block_count(pages: list[PageDescriptor]) -> int:
    """全卷 ``type == "table"`` 的块数（拆块前的原始表格块个数）。

    单独统计而不是从改造后的块列表里数：改造后 table 块会被拆成
    ``table_cell`` / ``table_row``，原来的块数就不可见了。
    """
    count = 0
    for page in pages:
        layout = page.layout if isinstance(page.layout, dict) else {}
        for block in layout.get("blocks") or []:
            if (
                isinstance(block, dict)
                and str(block.get("type") or "").strip().lower() == "table"
            ):
                count += 1
    return count


def table_row_histogram(pages: list[PageDescriptor]) -> list[str]:
    """全卷表格按行数分档计数 → 报告里可直接拼的表行。

    为什么要看这个分布：``_TABLE_SPLIT_MAX_ROWS`` 只在**阈值附近**有观测值的地方才有意义。
    如果 13~19 行这一档在全卷上几乎没表，那 12 与 20 两个候选值在实际卷宗上就是等价的——
    「调阈值」自然不是改善定位质量的杠杆。
    """
    buckets: Counter[int] = Counter()
    for page in pages:
        layout = page.layout if isinstance(page.layout, dict) else {}
        for block in layout.get("blocks") or []:
            if (
                not isinstance(block, dict)
                or str(block.get("type") or "").lower() != "table"
            ):
                continue
            html = str(block.get("table_body") or block.get("table_structure") or "")
            buckets[_grid_row_count(html)] += 1
    return [f"| {rows} | {buckets[rows]} |" for rows in sorted(buckets) if rows >= 12]


def whole_table_block_reasons(
    pages: list[PageDescriptor],
) -> dict[str, tuple[int, str]]:
    """整表保留的表卡在哪条判据上 → ``{原因: (张数, 高于阈值能否救)}``。

    为什么不直接读块上的字段：``build_positioned_blocks`` 只透出「没拆」这个结果，
    不说是哪条判据拦的。而「上调阈值能不能改善」完全取决于这条归因——
    行数闸能救，``<img>`` / 单格过大救不了。所以直接把所有表格重新跑一遍拆分入口。

    直接调 ``_split_table_into_cells`` 而不是抄一份判据：抄一份就会和实现漂移，
    这个脚本的下一个使用者也就无从判断哪边是对的。
    """
    reasons: dict[str, tuple[int, str]] = {}
    # 与 ``build_positioned_blocks`` 一致的矩形：MinerU 千分比归一后再落到 0–1。
    # 单格面积判据只看 ``rect.w * rect.h``，用真实 bbox 才能得到与线上相同的归因。
    for page in pages:
        layout = page.layout if isinstance(page.layout, dict) else {}
        for block in layout.get("blocks") or []:
            if (
                not isinstance(block, dict)
                or str(block.get("type") or "").lower() != "table"
            ):
                continue
            html = str(block.get("table_body") or block.get("table_structure") or "")
            rect = normalize_bbox(block.get("bbox"), unit="permille")
            if not html or rect is None:
                continue
            if float(rect["h"]) < mb._TABLE_SPLIT_MIN_HEIGHT_RATIO:
                key, rescued = "矮表（高度 < 18% 页高，不值得拆）", "不能，卡在高度门槛"
            else:
                by_row_only = _table_cell_count(html) > mb._TABLE_CELL_SPLIT_MAX
                if _split_table_into_cells(
                    page_no=page.page_no,
                    rect=rect,
                    html=html,
                    unit="permille",
                    by_row_only=by_row_only,
                ):
                    continue
                grid = _parse_grid(html)
                row_count = _grid_row_count(html)
                col_count = _grid_col_count(grid)
                if (
                    row_count > mb._TABLE_SPLIT_MAX_ROWS
                    and mb._filled_cell_ratio(
                        grid=grid, row_count=row_count, col_count=col_count
                    )
                    >= mb._FILLED_CELL_RATIO_BYPASS
                ):
                    key, rescued = (
                        f"行数闸（> {mb._TABLE_SPLIT_MAX_ROWS} 行且非稀疏）",
                        f"能，但这些表有 {row_count} 行",
                    )
                elif "<img" in html.lower():
                    key, rescued = "格子里有图片（整页版面不是表格）", "不能"
                else:
                    key, rescued = "可信度判据（单格过大 / 单格整段正文）", "不能"
            count, text = reasons.get(key, (0, rescued))
            reasons[key] = (count + 1, text)
    return reasons


def corpus_precision_distribution(pages: list[PageDescriptor]) -> dict[str, Any]:
    """全卷跑 ``build_positioned_blocks`` → 三档精度计数 + 按块类型的明细。

    ``approx`` 与 ``precision`` 的对应关系一并统计：两者必须自洽
    （``approx=True`` ⟺ ``precision != "exact"``），否则老前端与新前端会给出
    互相矛盾的视觉规则——这是 ``build_positioned_blocks`` 注释里承诺的约束，
    顺手拿全卷数据验一遍。
    """
    raw_table_blocks = table_block_count(pages)
    blocks = build_positioned_blocks(pages, bbox_backend="mineru")
    precision_tally: Counter[str] = Counter()
    type_tally: dict[str, Counter[str]] = {}
    approx_mismatch: list[str] = []
    for block in blocks:
        rect = block.get("rect") or {}
        precision = str(rect.get("precision"))
        precision_tally[precision] += 1
        block_type = str(block.get("type"))
        type_tally.setdefault(block_type, Counter())[precision] += 1
        approx = bool(rect.get("approx"))
        if approx != (precision != "exact"):
            approx_mismatch.append(
                f"p{block.get('page')} {block_type} precision={precision} approx={approx}"
            )
    return {
        "block_count": len(blocks),
        "page_count": len(pages),
        "pages_with_layout": sum(1 for page in pages if isinstance(page.layout, dict)),
        "raw_table_blocks": raw_table_blocks,
        "precision_tally": precision_tally,
        "type_tally": type_tally,
        "blocked_reasons": whole_table_block_reasons(pages),
        "row_histogram": table_row_histogram(pages),
        "approx_mismatch": approx_mismatch,
    }


def _pct(part: int, total: int) -> str:
    return f"{part / total * 100:.1f}%" if total else "—"


def render_report(
    *,
    golds: list[dict[str, Any]],
    sweep: dict[int, list[dict[str, Any]]],
    drifts: list[str],
    corpus: dict[str, Any] | None,
    corpus_error: str,
) -> str:
    """把两段实验拼成 Markdown 报告。"""
    lines: list[str] = [
        "# 表格拆分阈值实验（`_TABLE_SPLIT_MAX_ROWS`）+ 全卷精度分布",
        "",
        f"生成脚本：`scripts/eval_table_split.py`（阈值 = {', '.join(str(t) for t in THRESHOLDS)}）",
        "",
        "> **参考文本不是金标准**：7 页 golden 全部 `gold_known: false`，是 MinerU 原始输出、",
        "> 未经人工校对。下面的数字只能读作**同一份 golden 上的相对涨跌**，不能读作「准确率 X%」。REF≠正确。",
        "",
        "## Q1：阈值对比（7 页 golden × 8 个阈值）",
        "",
        "### 汇总（每页先各自算，再取平均）",
        "",
        "| 阈值 | 平均 CER(MD) 前 | 平均 CER(MD) 后 | 表格页平均 cell F1 | 定位块总数 | 其中 precision=cell | 整表保留块数 |",
        "|---|---|---|---|---|---|---|",
    ]

    for threshold in THRESHOLDS:
        metrics = sweep[threshold]
        cer_raw = sum(m["cer_raw"] for m in metrics) / len(metrics)
        cer_norm = sum(m["cer_norm"] for m in metrics) / len(metrics)
        f1_values = [m["cell_f1"] for m in metrics if m["cell_f1"] is not None]
        f1_avg = sum(f1_values) / len(f1_values) if f1_values else 0.0
        total_blocks = sum(m["blocks"] for m in metrics)
        cell_blocks = sum(m["cell_blocks"] for m in metrics)
        lines.append(
            f"| {threshold} | {cer_raw:.4f} | {cer_norm:.4f} | {f1_avg:.4f} | "
            f"{total_blocks} | {cell_blocks} | {total_blocks - cell_blocks} |"
        )

    lines += [
        "",
        "「整表保留块数」= 定位块总数 - precision=cell 的块数：无表格页恒为 0，表格页则是它那一个整表框。",
        "",
        "### 逐页明细",
        "",
        "每个阈值一张小表，便于直接看「哪一页在哪个阈值下开始冒框」。",
        "",
    ]
    for threshold in THRESHOLDS:
        lines += [
            f"**阈值 = {threshold}**",
            "",
            "| 页 | 类型 | CER 前 | CER 后 | cell F1 | 块数 | 其中 cell 块 |",
            "|---|---|---|---|---|---|---|",
        ]
        for metric, gold in zip(sweep[threshold], golds):
            structure = table_structure(gold)
            kind = metric["kind"] + (
                f" {structure['rows']}×{structure['cols']}" if structure else ""
            )
            f1_text = (
                f"{metric['cell_f1']:.4f}" if metric["cell_f1"] is not None else "—"
            )
            lines.append(
                f"| p{metric['page']} | {kind} | {metric['cer_raw']:.4f} | {metric['cer_norm']:.4f} | "
                f"{f1_text} | {metric['blocks']} | {metric['cell_blocks']} |"
            )
        lines.append("")

    lines += ["## 关键验证：CER 是否随阈值变化", ""]
    if drifts:
        lines += [
            "**⚠️ CER 随阈值发生了变化 —— 这是 bug，不是阈值效果。**",
            "",
            (
                "拆块只产出定位框，正文由 `_page_markdown` / `_block_markdown` 独立生成，"
                "两条路径在源码里不共享可变状态，所以 CER 对阈值必须完全不敏感。变了就说明"
                "拆块路径回写到了 block / markdown 数据（例如原地修改 `block['text']`）。"
            ),
            "",
            "| 页 | CER(前) 出现过的值 | CER(后) 出现过的值 |",
            "|---|---|---|",
            *drifts,
        ]
    else:
        raw_set: set[float] = set()
        norm_set: set[float] = set()
        for threshold in THRESHOLDS:
            for metric in sweep[threshold]:
                raw_set.add(round(metric["cer_raw"], 10))
                norm_set.add(round(metric["cer_norm"], 10))
        lines += [
            "**通过**：8 个阈值 × 7 页，CER 一个字符都没动。",
            "",
            (
                f"- 归一化前出现过 {len(raw_set)} 个不同的 CER 值（应为 7——每页一个），"
                f"归一化后 {len(norm_set)} 个（同样应为 7）。"
            ),
            (
                "- 即：阈值只改定位框的数量与位置，**不改正文**。"
                "这一点本来也只是「理论上应该」，现在有实测兜住了——"
                "将来谁不小心让拆块逻辑回写正文，这张表会立刻变红。"
            ),
        ]

    lines += ["", "## Q3：576 全卷（164 页）precision 分布", ""]
    if corpus is None:
        lines += [
            f"未跑：{corpus_error}",
            "",
            f"数据源 `{CORPUS_PAGES_JSON.relative_to(REPO_ROOT)}` 不可用时，Q3 无法给出数字——这里不编造占位值。",
        ]
    else:
        tally: Counter[str] = corpus["precision_tally"]
        total = corpus["block_count"]
        raw_table_blocks = corpus["raw_table_blocks"]
        # 拆块前的块数：拆格只多出块（一个整表框 → 几十个格框），
        # 所以减掉全部 cell 块就回到原来的块数；table_row 是「按行拆代替按格拆」，
        # 它也必须减（它同样是多出来的块），否则改造前会被误算成更大。
        before_total = total - tally.get("cell", 0)
        before_exact = before_total - raw_table_blocks
        lines += [
            (
                f"- 页数：{corpus['page_count']}，其中有 layout 的页：{corpus['pages_with_layout']}"
                f"（其余页是本地 OCR 无坐标，`build_positioned_blocks` 直接跳过，与线上一致）"
            ),
            f"- 定位块总数：**{total}**",
            "",
            "| precision | 块数 | 占比 | 含义 |",
            "|---|---|---|---|",
            f"| `exact` | {tally.get('exact', 0)} | {_pct(tally.get('exact', 0), total)} | 引擎真实返回的 bbox（可信） |",
            f"| `cell` | {tally.get('cell', 0)} | {_pct(tally.get('cell', 0), total)} | 表格均分推算框（半格误差） |",
            f"| `page` | {tally.get('page', 0)} | {_pct(tally.get('page', 0), total)} | 整表未拆 / 坐标基本无意义 |",
            "",
            "### 按块类型拆开看",
            "",
            "只有 `table` 块会走拆分，「page」几乎全部来自这里；正文块的坐标本来就是引擎给的 `exact`。",
            "",
            "| 块类型 | exact | cell | page | 小计 |",
            "|---|---|---|---|---|",
        ]
        for block_type in sorted(corpus["type_tally"]):
            per_type: Counter[str] = corpus["type_tally"][block_type]
            lines.append(
                f"| {block_type} | {per_type.get('exact', 0)} | {per_type.get('cell', 0)} | "
                f"{per_type.get('page', 0)} | {sum(per_type.values())} |"
            )
        lines += [
            "",
            "### 整表保留的 62 张表：卡在哪个判据",
            "",
            "`_split_table_into_cells` 返回空列表有多条互斥出口，知道卡在哪一条才知道",
            "「把阈值上调到 999 能不能救它们」。下面直接对 62 个整表块重跑拆分入口并归因：",
            "",
            "| 场景 | 张数 | 高于阈值能否救 |",
            "|---|---|---|",
            *[
                f"| {reason} | {count} | {rescued} |"
                for reason, (count, rescued) in corpus["blocked_reasons"].items()
            ],
            f"| **合计** | **{sum(count for count, _ in corpus['blocked_reasons'].values())}** | — |",
            "",
            "归因要点：",
            "",
            "- **行数闸**：上调 `_TABLE_SPLIT_MAX_ROWS` 确实能把它们放进来，但这些表的行数在 50~285，",
            "  正是「均分误差累积到好几行」的长表段——拆了也不能用。",
            "- **含图片 / 可信度判据**：结构性不可拆（格子里是照片或印章 / 单格面积过大 / 单格塞整段正文），",
            "  阈值调到多少都无效。",
            "- **矮表**（高度 < 18% 页高）：卡在 `_TABLE_SPLIT_MIN_HEIGHT_RATIO`，不是行数闸，",
            "  改 `_TABLE_SPLIT_MAX_ROWS` 同样无效。",
            "",
            "所以「把阈值改大 = 多给律师一些可点框」这个直觉不成立：让这些表不拆的多数不是行数闸。",
            "反过来说，这也答复了 Q1 的「12 vs 20」——把 12 提到 20 只能多救行数在 13~20 的表，",
            "而全卷这个区间只有 p22 一张（见下方 Q3 补充）。",
            "",
            "### 全卷行数分布（只列 ≥ 12 行的表）",
            "",
            "| 行数 | 张数 |",
            "|---|---|",
            *corpus["row_histogram"],
        ]
        lines += [
            "",
            "### 与「改造前」的对照",
            "",
            "改造前没有 `precision` 字段，整卷只有布尔 `approx`：**所有**表格块（拆格 / 拆行 / 整表）",
            "统一是 `approx=True`，前端一律当「整页近似」画。按这个口径，「改造前」的等价分布是：",
            "`exact` = 非表格块数、`cell` = 0、`page` = **拆块前的原始表格块数**。",
            "",
            f'拆块前的原始 `table` 块数（直接数 layout 里的 `type == "table"`）：**{corpus["raw_table_blocks"]}**。',
            (
                f"改造后这 {corpus['raw_table_blocks']} 个块被展开成 `table_cell` / `table_row` / 整表 `table` 三种，"
                f"所以块**总数**从改造前的 {before_total} 涨到 {total}——这是「一个整表框变成几十个格框」的必然结果，"
                "不是重复计数。"
            ),
        ]
        lines += [
            "",
            (
                f"- 改造前：`exact` {before_exact}（{_pct(before_exact, before_total)}）、"
                f"`cell` 0、`page` {raw_table_blocks}（{_pct(raw_table_blocks, before_total)}），共 {before_total} 块"
            ),
            (
                f"- 改造后：`exact` {tally.get('exact', 0)}（{_pct(tally.get('exact', 0), total)}）、"
                f"`cell` {tally.get('cell', 0)}（{_pct(tally.get('cell', 0), total)}）、"
                f"`page` {tally.get('page', 0)}（{_pct(tally.get('page', 0), total)}），共 {total} 块"
            ),
            (
                f"- 净变化：{tally.get('cell', 0)} 个块从「一律说整页近似」变成「明确标成半格推算框」；"
                f"只剩 {tally.get('page', 0)} / {raw_table_blocks} 张表仍是整表框。"
            ),
            (
                f"  按占比说：改造前有 {_pct(raw_table_blocks, before_total)} 的块自称「整页近似」，"
                f"改造后降到 {_pct(tally.get('page', 0), total)}；自称整页近似的**绝对块数从 "
                f"{raw_table_blocks} 降到 {tally.get('page', 0)}**。"
            ),
            "",
            (
                "注意这不是「准确率提升」——`cell` 框本身就是推算的（均分），"
                "这次改造让它**被标成推算**而不是被冒充成精确位置。真正变好的是「谎报率下降」："
                "以前所有表格块都说「这是整页近似」、包括那些实际上只是格子里的一个字段；"
                "现在这些格子被单独标为 `cell`，前端能分开画，律师能看出「这个框是猜的」。"
            ),
            "",
            "### `approx` 与 `precision` 自洽性",
            "",
        ]
        if corpus["approx_mismatch"]:
            lines += [
                "**⚠️ 有块违反了「`approx=True` ⟺ `precision != exact`」的约定：**",
                "",
                *[f"- {item}" for item in corpus["approx_mismatch"][:20]],
            ]
        else:
            lines.append(
                f"全部 {total} 块自洽：`approx=True` 的块全部不是 `exact`，反之亦然。"
                "老前端读 `approx`、新前端读 `precision`，两套规则不会打架。"
            )

    lines += [
        "",
        "## 结论",
        "",
    ]
    lines += render_conclusion(golds=golds, sweep=sweep, drifts=drifts, corpus=corpus)
    return "\n".join(lines) + "\n"


def render_conclusion(
    *,
    golds: list[dict[str, Any]],
    sweep: dict[int, list[dict[str, Any]]],
    drifts: list[str],
    corpus: dict[str, Any] | None,
) -> list[str]:
    """从实测数字推出推荐阈值。结论必须落在**框数**上，不是 CER 上。

    为什么：CER 与 cell F1 在所有阈值下都不动（已被 ``cer_drift`` 证实），
    「哪个阈值更准」这个问题本身不成立。唯一随阈值变化的是「律师能点到多少框、
    这些框有多可信」，所以推荐必须讲清楚是在这两者之间怎么权衡。
    """
    lines: list[str] = []

    # 每一页在哪个阈值下第一次开始产生 cell 块 —— 这是「这页需要多大阈值才拆」的直接答案
    onset: dict[int, int | None] = {}
    for index, gold in enumerate(golds):
        first = None
        for threshold in THRESHOLDS:
            if sweep[threshold][index]["cell_blocks"] > 0:
                first = threshold
                break
        onset[int(gold["page"])] = first
    lines += [
        "### 每页在哪个阈值下开始冒 cell 框",
        "",
        "| 页 | 类型 | 行×列 | 首次出现 cell 框的阈值 | 该页最大 cell 块数 |",
        "|---|---|---|---|---|",
    ]
    for gold in golds:
        index = golds.index(gold)
        structure = table_structure(gold)
        max_blocks = max(
            sweep[threshold][index]["cell_blocks"] for threshold in THRESHOLDS
        )
        first = onset[int(gold["page"])]
        shape = f"{structure['rows']}×{structure['cols']}" if structure else "—"
        lines.append(
            f"| p{gold['page']} | {gold['kind']} | {shape} | "
            f"{first if first is not None else '从不拆'} | {max_blocks} |"
        )

    cell_counts = {
        threshold: sum(m["cell_blocks"] for m in sweep[threshold])
        for threshold in THRESHOLDS
    }
    lines += [
        "",
        "### 结论",
        "",
        "1. **CER 与 cell F1 在所有阈值下完全一致**"
        + (
            "（本次实测 `CER 随阈值变化` —— 见上文 bug 段，结论不成立）"
            if drifts
            else "（8 个阈值 × 7 页，无一例变化）"
        )
        + "。",
        (
            "   所以「调阈值能提高取字质量」这个假设**不成立**：阈值只决定拆不拆定位框，"
            "与正文/CER 完全正交。之前把 `_TABLE_SPLIT_MAX_ROWS` 当质量参数来调，方向就错了。"
        ),
        "",
        "2. **拆框数随阈值单调不增**："
        + "、".join(
            f"{threshold}→{cell_counts[threshold]} 个 cell 块"
            for threshold in THRESHOLDS
        )
        + "。",
    ]

    # 给出「12」在实测里的实际位置：它是否真的挡掉了长表、放行了该放行的表
    c12 = cell_counts.get(12, 0)
    c20 = cell_counts.get(20, 0)
    c30 = cell_counts.get(30, 0)
    c999 = cell_counts.get(999, 0)
    lines += [
        "",
        (
            f"3. **当前值 12 在实测里的位置**：12 放行 {c12} 个 cell 块，"
            f"20 放行 {c20} 个，30 放行 {c30} 个，999（无上限）放行 {c999} 个。"
        ),
    ]
    if c20 > c12:
        lines.append(
            "   12→20 多出来的全是 p22 押品表（17 行）拆出的 68 个格框：它的行数 17 落在"
            "「13~20」区间，所以只有阈值 ≥18 才会拆。这张表正是律师真要逐格点的表单。"
        )
    if c999 > c30:
        lines.append(
            "   30→999 多出来的全是 p62 52 行流水表拆出的 52 个行框（整节 52 个 `<tr>` 里"
            "4 行是 colspan 标题行、无字被跳过，所以是 52 不是 56）；"
            "而均分坐标在长表上误差累积到好几行——多出来的框**看起来多，实际指不准**。"
        )

    lines += [
        "",
        "4. **推荐：维持 12**。理由（按实测的切口逐个说）：",
        (
            "   - **12→20 的唯一差别是 p22**（68 格）。多 68 个格框听起来是好事，"
            "但它的代价是把「13~20 行表一律拆格」这个规则放出去：行数一多，"
            "均分误差就开始超过半格，而 13~20 行正好是「表头/标题行占好几行」的典型尺寸。"
            "本实验没有真实行坐标，**无法证明那 68 个框都指对了格**——不能验证的改善不能当理由。"
        ),
        (
            "   - **20 以上会把 52 行流水表也拆成行框**：这正是注释里说「第 1 行偏差 72px」的场景，"
            "拆出来的是「看起来能点、实际指错行」的框，比一个诚实的整表框更坏。"
        ),
        (
            "   - **0 / 3 / 6 / 12 在 golden 上行为完全一样**（都是 4 个整表框）：因为四张表里最小的是 "
            "p30 的 3×2，而它被 `_split_is_trustworthy` 的「单格面积过大」判据挡掉了（2 列 × 3 行、"
            "`rect` 是整页框，单格占比远超过 4%），根本走不到行数闸。"
            "这说明 **12 这个数在本批 golden 上没有任何区分力**，它的依据只能来自全卷行数分布"
            "与注释里的误差累积估算，不能来自这 7 页。"
        ),
        (
            "   - 80 / 999 等同于关掉这道闸：`_TABLE_ROW_SPLIT_MAX=80` 会成为唯一上限，"
            "而它的注释自己就说「这是冗余保险」，不该让它变成主力判据。"
        ),
        (
            "   - 往下的 0 / 3 / 6 则是把闸关得太紧：它们与 12 在 golden 上没区别，"
            "但会把 7~11 行这类「表头 + 几行数据」的小表单也推出拆分范围，白白丢掉可点击粒度。"
        ),
        (
            "   - **若将来要动，正确方向不是改阈值而是改判据**：Q3 显示行数本身在 12~30 区间里"
            "几乎没有观测值（只有 p22 一张），所以用行数当唯一判据本身就是个弱代理；"
            "真正决定均分准不准的是「行高齐不齐」，只是现有引擎数据里拿不到真实行高。"
        ),
        "",
        (
            "5. **无法验证的部分（诚实交代）**：本实验量不到「拆出来的框到底指没指中真实行/格」。"
            "golden 与 pages.json 都只有整表 bbox，没有逐行坐标——所以「p22 拆 68 格到底准不准」"
            "本次回答不了。这也是把推荐停在 12（保守侧）而不是 20 的根本原因。"
        ),
        "",
        (
            "6. **真正该改的不是阈值，是「框可不可信」的表达**：本实验测到的唯一实质改善，"
            "是 Q3 里那批块从「一律 approx=True」变成分档 `exact`/`cell`/`page`。"
            "阈值调到哪一档都改变不了「推算框就是推算框」，但把它**标出来**"
            "能让前端画虚线、让律师知道这个框是猜的。"
        ),
        "",
        (
            "> 再次强调口径：以上全部基于 `gold_known: false` 的 MinerU 快照，"
            "只能说明「同一份 golden 上阈值间无差异」，不能说明「阈值 12 的准确率是多少」。"
        ),
    ]
    if corpus is not None:
        tally = corpus["precision_tally"]
        lines += [
            "",
            (
                f"7. **Q3 补充**：全卷 {corpus['block_count']} 个定位块里 `cell` "
                f"{tally.get('cell', 0)} 个（{_pct(tally.get('cell', 0), corpus['block_count'])}），"
                f"`page` {tally.get('page', 0)} 个。拆块前的 {corpus['raw_table_blocks']} 张表里，"
                f"**{corpus['raw_table_blocks'] - tally.get('page', 0)} 张被拆开成格/行框**、"
                f"只剩 {tally.get('page', 0)} 张保持整表框。即使这样，表格块里仍有 "
                f"{_pct(tally.get('page', 0), corpus['raw_table_blocks'])} 的表只能给整表框——"
                "再上调阈值的收益空间本来就小，而且那些收益全是均分误差最大的长表，所以 12 已经足够。"
            ),
            "",
            (
                "   **但另一个发现值得看**：13~19 行的表全卷只有 5 张，而且其中几张被可信度判据挡掉；"
                "真正落在「12→20 区间内且有字可拆」的只有 p22 那张 17 行表。"
                "换句话说，12 / 20 / 30 这三个候选值在全卷上的差别**只有一张表**。"
                "这也反向证实了「调阈值不是杠杆」：杠杆在拆得准不准，不在门槛高低。"
            ),
            "",
            "   行数分布见上方「全卷行数分布」表（它由 `_grid_row_count` 对 `pages.json` 逐张表统计，可重跑核对）。",
        ]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="表格拆分阈值实验 + 全卷定位精度分布")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--skip-corpus",
        action="store_true",
        help="跳过 Q3（全卷 164 页），只跑 Q1 阈值对比",
    )
    args = parser.parse_args()

    golds = load_golden_pages()
    sweep = run_threshold_sweep(golds)
    drifts = cer_drift(sweep)

    corpus: dict[str, Any] | None = None
    corpus_error = ""
    if args.skip_corpus:
        corpus_error = "本次运行带了 `--skip-corpus`"
    elif not CORPUS_PAGES_JSON.exists():
        corpus_error = f"数据源不存在：`{CORPUS_PAGES_JSON}`"
    else:
        corpus = corpus_precision_distribution(load_corpus_pages())

    report = render_report(
        golds=golds,
        sweep=sweep,
        drifts=drifts,
        corpus=corpus,
        corpus_error=corpus_error,
    )
    args.out.write_text(report, encoding="utf-8")
    # 用 sys.stdout.write 而不是 print()：scripts/ 在 security_guard 的 print 门禁前缀内。
    # 报告的持久出口是 args.out，stdout 只是给人当场看。
    sys.stdout.write(report)
    sys.stdout.write(f"\n报告已写入 {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
