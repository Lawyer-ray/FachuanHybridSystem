"""双引擎**编排**：跑 MinerU + PaddleOCR-VL，产出「引擎分歧」供人工裁决。

判据不在这里（在 ``dual_engine.py``）：本模块只负责「把两个引擎都跑起来、
把各自的逐页文本对齐成 ``{page_no: text}``、交给 ``compare_pages``、把结果
转成可 JSON 序列化的 dict」。分开的理由是两边的失败语义完全不同：

· 编排会失败（没配 Key、云端超时、上传被拒），必须能**只坏一个引擎**；
· 判据不该因为一个引擎挂了就改变行为（``compare_pages`` 对单引擎返回空）。

## 谁决定开不开

**由调用方传入的引擎列表决定，本模块不读任何配置**：传 2 个引擎就比对，
传 1 个就退化成单引擎（``compare_pages`` 对单引擎返回空）。用户在哪选引擎、
选择怎么存下来，是调用方的事（当前是 `PdfSplitJob.cloud_backend` 的逗号分隔值）。

为什么“读配置”是错的设计：律师要在「自动分段」的下拉菜单里逐次勾选引擎，
「这次要不要双跑」是**单次任务的输入**，不是部署级配置。放配置里要么全员被
同一档价格绑死，要么得先改配置再跑任务——两种都不是用户要的东西。

双引擎意味着**同一份 PDF 被两个云端平台各识别一遍**：耗时翻倍（164 页卷宗
实测单引擎就要几分钟到十几分钟）、费用翻倍，而收益是「找出两引擎不一致的
地方」。这份收益只在关键页上值得付全价，所以调用方没给引擎时（``engine_factories``
为空）就什么都不做，不要一上来全卷。

## 为什么并行

两个引擎之间没有任何数据依赖，串行只会把两份云端排队时间叠起来。用线程池：
两个后端都是 HTTP 阻塞 IO（MinerU 是上传+轮询+下载，PaddleOCR 是提交+轮询+下载），
线程完全够用，不需要动 asyncio——这两个后端的同步入口已经稳定，为双引擎
再写一套异步路径等于多一份要同步维护的实现。

## 一个引擎挂了怎么办

**不让它拖垮另一个**。失败的一方结果记 ``None``、原因记进
``summary["dual_engine"][引擎]["error"]``，另一个照常产出。此时
``compare_pages`` 因为「可比引擎不足 2 个」返回空列表——这是对的：单引擎
路径下没有「分歧」这个概念，报出任何东西都是噪声。
"""

from __future__ import annotations

import logging
import re
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pymupdf as fitz

from .dual_engine import (
    ENGINE_MINERU,
    ENGINE_PADDLEOCR_VL,
    MINERU_TABLE_BLOCK_TYPES,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    EngineDisagreement,
    EngineVariant,
    compare_pages,
    is_markdown_table_line,
    link_disagreement_to_blocks,
    normalize_mineru_blocks,
    normalize_paddleocr_vl_blocks,
)

logger = logging.getLogger("apps.pdf_splitting")

#: summary 里挂分歧数据的键名（前端 draft.ts 按这个读）。
SUMMARY_ENGINE_DISAGREEMENTS = "engine_disagreements"
SUMMARY_ENGINE_DISAGREE_SUMMARY = "engine_disagree_summary"

#: 严重度桶的固定顺序：前端抽屉就是按这三组渲染，缺哪组都要给 0。
_SEVERITY_BUCKETS = (SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW)

#: 落盘 ``full_text`` 的每变体字数上限。
#:
#: 依据（579 真实产物只读实测）：参与逐字比对的非表格行共 1177 条，最长 608 字、
#: p99 238 字，**没有一条超过 1000 字**；「整块覆盖不一致」分支会把整页拼成一条，
#: 实测最长 1165 字、p90 904 字，**没有一页超过 2000 字**。2000 覆盖全部实测情形
#: 还留约 1.7 倍余量，够容纳更密的卷宗。
#:
#: 为什么必须有上限：整页拼接那条分支的长度随页面密度线性增长，无上限时一份
#: 密集卷宗能把产物撑到几 MB（当前 579 已 524KB，其中 blocks 占 39%）。
#: 超限不静默截断，另打 ``full_text_truncated`` 让离线重算能剔除这些条。
_FULL_TEXT_MAX_CHARS = 2000

#: 本模块**真能跑起来**的引擎。
#:
#: 只有两个：Textin 走的是另一套后端接口，逐页结构与归一化判据都还没接进
#: ``dual_engine``，硬塞进来只会产出假分歧。用户能勾它（`DUAL_ENGINE_CHOICES`
#: 里有），本模块就把它记进 ``dual_engine.unavailable``——静默丢弃是最坏的
#: 做法：用户以为跑了三个引擎，实际只跑了两个。
SUPPORTED_ENGINES: tuple[str, ...] = (ENGINE_MINERU, ENGINE_PADDLEOCR_VL)

#: 双引擎槽位里 PaddleOCR 固定用的模型键。
#:
#: 不受 ``PADDLEOCR_API_MODEL`` 影响：配置里的默认值可能是 PP-OCRv5（纯文字
#: OCR，不出逐页版面），拿它当「第二引擎」既拿不到页码也拿不到 bbox，双框对照
#: 做不成。
PADDLEOCR_VL_MODEL = "paddleocr_vl_1_6"


@dataclass
class DualEngineOutcome:
    """一次双引擎编排的产物。

    ``summary`` 可以直接 ``**`` 进 job summary（两个键都是纯 dict/list）；
    ``engine_pages`` / ``blocks_by_engine`` 是给调用方继续加工用的
    （页级 SKU 落盘、UI 双框），不进 summary——逐页全文会把 job 详情撑到几 MB。
    """

    engine_pages: dict[str, dict[int, str]]
    blocks_by_engine: dict[str, list[Any]]
    disagreements: list[EngineDisagreement]
    summary: dict[str, Any] = field(default_factory=dict)


def plan_dual_engine_factories(engines: Sequence[str]) -> tuple[dict[str, Any], list[str]]:
    """把「用户勾选的引擎」收成可运行的工厂字典。

    Returns:
        ``(factories, unavailable)``。``unavailable`` 是勾了但本模块还不支持的
        引擎（目前只有 textin），由调用方写进 summary，让「为什么没比对上」可见。

    去重与大小写归一在这里做（前端传什么都认），顺序按用户勾选顺序。
    """
    known = _default_engine_factories()
    factories: dict[str, Any] = {}
    unavailable: list[str] = []
    for raw in engines:
        engine = str(raw or "").strip().lower()
        if not engine:
            continue
        if engine in known:
            factories[engine] = known[engine]
        elif engine not in unavailable:
            unavailable.append(engine)
    return factories, unavailable


def run_dual_engine(
    pdf_path: Path | str,
    *,
    page_numbers: Sequence[int] | None = None,
    engine_factories: Mapping[str, Any] | None = None,
    max_workers: int = 2,
    min_severity: str | None = None,
) -> DualEngineOutcome:
    """并行跑各引擎并比对，返回分歧（**不做任何持久化**）。

    引擎集合完全由调用方决定：``engine_factories`` 里放几个就跑几个（放 1 个也能
    跑，只是 ``compare_pages`` 会因为「可比引擎不足 2 个」返回空分歧）。本函数
    **不读任何配置**——「这次要不要双跑」是任务输入，不是部署配置。

    Args:
        pdf_path: 源 PDF。``page_numbers`` 非空时只把这几页切出来上传——
            关键页试点不该为整本卷宗付两次云端费用。
        page_numbers: 要跑的页码（1 起）。None / 空表示全本。
        engine_factories: ``{引擎名: 返回后端实例的可调用对象}``。测试注入口；
            缺省用全部支持的引擎（MinerU / PaddleOCR-VL）。**工厂在对应线程里
            调用**，所以后端实例不跨线程共享。
        max_workers: 线程数。几个引擎就几个，再多也不会更快（云端排队才是瓶颈）。
        min_severity: 透传给 ``compare_pages``；None 表示全返回。

    Returns:
        ``DualEngineOutcome``。某一引擎失败时它在 ``engine_pages`` 里是空 dict，
        失败原因写在 ``summary["dual_engine"][引擎]["error"]``。
    """
    source = Path(pdf_path)
    targets = _normalize_page_numbers(page_numbers)
    factories = dict(engine_factories) if engine_factories is not None else _default_engine_factories()

    # 切小 PDF 只做一次：两个引擎上传同一份字节，页号映射才是同一套。
    # （各自切一份等于同一件事做两遍，还可能因为切法不同导致页号对不上。）
    if targets is None:
        upload_path = source
        temp_holder: tempfile.TemporaryDirectory[str] | None = None
    else:
        temp_holder, upload_path = _slice_pdf(source, targets)

    try:
        raw_results = _run_engines_parallel(
            upload_path,
            factories=factories,
            page_numbers=targets,
            total_pages=len(targets) if targets is not None else _count_pages(upload_path),
            max_workers=max_workers,
        )
    finally:
        if temp_holder is not None:
            temp_holder.cleanup()

    engine_pages: dict[str, dict[int, str]] = {}
    blocks_by_engine: dict[str, list[Any]] = {}
    engine_status: dict[str, dict[str, Any]] = {}
    for engine in factories:
        text_pages, blocks, error = raw_results.get(engine, ({}, [], "引擎未运行"))
        if targets is not None:
            # 切页后上传的是从第 1 页起的小 PDF，两引擎给出的都是**相对页号**。
            # 分歧的页码必须是原卷页码——否则前端跳转和高亮会落到别的页上。
            text_pages, blocks = _remap_to_source_pages(text_pages, blocks, targets)
        engine_pages[engine] = text_pages
        blocks_by_engine[engine] = blocks
        engine_status[engine] = {
            "ok": not error,
            "page_count": len(text_pages),
            "block_count": len(blocks),
            # 错误信息里可能带本地路径（排障需要），但不能带 API Key
            "error": error,
        }

    disagreements = compare_pages(engine_pages, min_severity=min_severity)
    # 每条分歧挂上两侧的块矩形（前端「双框对照」读的就是 `blocks`）：不挂的话
    # 抽屉里点一条只能跳页、画不出两个框——而“两个引擎指在同一页的哪里”正是
    # 律师判断“谁对”唯一的凭据。匹配不上就缺着（`link_disagreement_to_blocks`
    # 不猜框）。
    annotations: dict[tuple[int, str, str], list[dict[str, Any]]] = {}
    for item in disagreements:
        linked = link_disagreement_to_blocks(item, blocks_by_engine)
        blocks = [engine_block_to_dict(engine, block) for engine, block in linked.items() if block is not None]
        if blocks:
            annotations[disagreement_key(item)] = blocks

    return DualEngineOutcome(
        engine_pages=engine_pages,
        blocks_by_engine=blocks_by_engine,
        disagreements=disagreements,
        summary={
            SUMMARY_ENGINE_DISAGREEMENTS: disagreements_to_dicts(disagreements, blocks_by_disagreement=annotations),
            SUMMARY_ENGINE_DISAGREE_SUMMARY: summarize_severities(disagreements),
            # 编排层自身的可观测字段：哪个引擎没跑起来、跑了多少页。
            # 与分歧数据分开，避免前端把「引擎挂了」误读成「没有分歧」。
            "dual_engine": {
                # engines 就是本次真正跑的引擎（用户勾选 ∩ 支持列表），前端据此
                # 说「MinerU / PaddleOCR-VL 对照」而不是照着勾选框猜。
                "engines": engine_status,
                "pages": list(targets) if targets is not None else [],
            },
        },
    )


def _remap_to_source_pages(
    text_pages: dict[int, str],
    blocks: list[Any],
    targets: Sequence[int],
) -> tuple[dict[int, str], list[Any]]:
    """相对页号（1..N）→ 原卷页号。

    只试试点页时最容易错的一步：切出来的小 PDF 第 1 页在原卷可能是第 38 页，
    两引擎都只知道自己手里那份的第几页。不映射的话，分歧会报在「第 1 页」，
    律师点进去看到的却是封面。

    映射表按 ``targets`` 的**升序**位置建（``_normalize_page_numbers`` 已排序，
    ``_slice_pdf`` 也按这个顺序插入），下标 i 对应原卷第 ``targets[i]`` 页。
    """
    mapping = {index + 1: page_no for index, page_no in enumerate(targets)}
    remapped_pages = {mapping[relative]: text for relative, text in text_pages.items() if relative in mapping}
    remapped_blocks: list[Any] = []
    for block in blocks:
        # block.page_no 在 EngineBlock 上是 int，但类型标注为 Any（兼容后端多样返回），
        # 先收窄再查表：非 int 的脏值直接跳过，不要让它在 replace() 里变成非法页码。
        relative_page = getattr(block, "page_no", None)
        if not isinstance(relative_page, int):
            continue
        source_page = mapping.get(relative_page)
        if source_page is None:
            continue
        remapped_blocks.append(replace(block, page_no=source_page))
    return remapped_pages, remapped_blocks


def disagreement_key(item: EngineDisagreement) -> tuple[int, str, str]:
    """一条分歧的稳定标识：``(页码, 类型, 上下文)``。

    只用于内部的“分歧 → 块矩形”配对，与前端 `draft/engine.ts` 的
    `disagreementKey` 不是同一个用途（那边面给“已核对”做勾选键）。
    """
    return (item.page_no, item.kind, item.context)


def engine_block_to_dict(engine: str, block: Any) -> dict[str, Any]:
    """``EngineBlock`` → 前端 ``EngineBlockRect``。

    坐标口径与 ``PositionedBlockOut.rect`` 完全一致（归一化 0-1、相对页面图像），
    前端把两套框画在同一张图上才有意义。``engine`` 取自分歧变体的引擎名：
    ``EngineBlock.engine`` 本身就填了，但这里以变体为准——块是按变体文字匹配来的，
    两者必须严格对应，否则会把一个框标到另一个引擎名下。
    """
    return {
        "engine": engine,
        "page_no": block.page_no,
        "text": block.text,
        "rect": dict(block.rect),
        "block_type": block.block_type,
        "approx": bool(block.approx),
    }


def _variant_to_dict(variant: EngineVariant) -> dict[str, Any]:
    """一个变体 → 落盘 dict：摘要恒在，全文**只在与摘要不同时**才写。

    为什么需要全文：``text`` 是剥标签 + 压空白 + 截到 120 字的摘要，而严重度判据
    吃的是**原始行**。只存摘要的产物无法离线重算严重度——截断前缀看着只差标点，
    真差异可能在 120 字之后（579 旧产物 332 条里 87 条至少一侧被截断，重算不了）。

    为什么等值时不写：摘要与原文相同就说明摘要已是全文，再存一份是纯重复
    （579 的 664 个变体里 510 个如此，实测省 30KB）。两侧消费方都是「全文缺省退回摘要」
    （后端 ``EngineVariant.body``、前端 ``draft/engine.ts`` 的 variantBody），
    缺键与等值同义，形状兼容。

    为什么按 variant 限长而不是按严重度分级存：低等级也要能重算——校准的目的
    正是验证「被降为 low 的那些真的只是标点差异」，只给 high/medium 存全文
    等于把要验证的那一半藏起来。
    """
    payload: dict[str, Any] = {
        "engine": variant.engine,
        "label": variant.label,
        "text": variant.text,
    }
    body = str(variant.body or "")
    if not body or body == variant.text:
        return payload
    payload["full_text"] = body[:_FULL_TEXT_MAX_CHARS]
    if len(body) > _FULL_TEXT_MAX_CHARS:
        # 明确告诉离线重算的人「这一条不是全文」，否则截断伪影会被当成真噪声
        payload["full_text_truncated"] = True
    return payload


def disagreements_to_dicts(
    disagreements: Iterable[EngineDisagreement],
    *,
    blocks_by_disagreement: Mapping[tuple[int, str, str], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """``EngineDisagreement``（frozen dataclass）→ 纯 dict，供 JSON 序列化。

    手写转换而不是 ``dataclasses.asdict``：``variants`` 是 ``EngineVariant`` 列表，
    asdict 会把它转成 dict，但我们要给每个变体再加一个给人看的 ``label``
    （``MinerU`` / ``PaddleOCR-VL``），这是前端直接渲染的字段。

    ``blocks`` 只有拿到对应块时才出现（匹配不上就不写这个键，而不是给空列表）：
    前端对“缺坐标”与“坐标为空”的处理是同一件事，但缺键能区分“根本没过这一层”。
    """
    blocks_by_disagreement = blocks_by_disagreement or {}
    out: list[dict[str, Any]] = []
    for item in disagreements:
        payload: dict[str, Any] = {
            "page_no": item.page_no,
            "kind": item.kind,
            "severity": item.severity,
            "variants": [_variant_to_dict(variant) for variant in item.variants],
            "context": item.context,
            "anchor_hit": item.anchor_hit,
            "similarity": round(float(item.similarity), 4),
        }
        blocks = blocks_by_disagreement.get(disagreement_key(item))
        if blocks:
            payload["blocks"] = blocks
        out.append(payload)
    return out


def summarize_severities(disagreements: Iterable[EngineDisagreement]) -> dict[str, int]:
    """按严重度计数。三个桶**总是**都在（没有就是 0）。

    理由：前端抽屉要显示「🔴 高危（0）」这类标题，缺键会让它得写 ``?? 0``；
    固定的形状比省三个 int 有用。
    """
    counts = dict.fromkeys(_SEVERITY_BUCKETS, 0)
    for item in disagreements:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    return counts


def _run_engines_parallel(
    upload_path: Path,
    *,
    factories: Mapping[str, Any],
    page_numbers: Sequence[int] | None,
    total_pages: int,
    max_workers: int,
) -> dict[str, tuple[dict[int, str], list[Any], str]]:
    """并行跑各引擎；任一引擎抛异常只影响它自己那一份结果。"""
    if not factories:
        return {}

    results: dict[str, tuple[dict[int, str], list[Any], str]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(factories)))) as executor:
        future_map = {
            executor.submit(_run_single_engine, engine, factory, upload_path, page_numbers, total_pages): engine
            for engine, factory in factories.items()
        }
        for future, engine in future_map.items():
            try:
                results[engine] = future.result()
            except Exception as exc:
                # 工厂本身炸了（没配 Key、依赖缺失）也走到这里：
                # 另一个引擎的结果必须照常返回。
                logger.exception("pdf_split_dual_engine_failed", extra={"engine": engine})
                results[engine] = ({}, [], f"{type(exc).__name__}: {_sanitize(str(exc))}")
    return results


def _run_single_engine(
    engine: str,
    factory: Any,
    upload_path: Path,
    page_numbers: Sequence[int] | None,
    total_pages: int,
) -> tuple[dict[int, str], list[Any], str]:
    """跑单个引擎。返回 ``(逐页文本, 归一化块, 错误信息)``，错误信息为空即成功。"""
    try:
        backend = factory()
        if engine == ENGINE_MINERU:
            return _run_mineru(backend, upload_path)
        if engine == ENGINE_PADDLEOCR_VL:
            return _run_paddleocr_vl(backend, upload_path, page_numbers=page_numbers, total_pages=total_pages)
        return {}, [], f"未知引擎: {engine}"
    except Exception as exc:
        logger.exception("pdf_split_dual_engine_engine_error", extra={"engine": engine})
        return {}, [], f"{type(exc).__name__}: {_sanitize(str(exc))}"


def _run_mineru(backend: Any, upload_path: Path) -> tuple[dict[int, str], list[Any], str]:
    """MinerU：一次解析整份 PDF，从 ``layout["pages"]`` 恢复逐页文本与版面块。

    页号恢复与 ``OCRHandler.parse_cloud_pages`` 同一口径（``page.page_no``）：
    两处对同一份 MinerU 结果必须切出同一套页码，否则分歧的页码会和页缓存错位。
    """
    parsed = backend.parse_document(
        file_path=upload_path.as_posix(),
        file_type="pdf",
        extract_tables=True,
        extract_images=False,
        return_markdown=False,
    )
    layout = getattr(parsed, "layout", None) or {}
    pages = [page for page in layout.get("pages", []) if isinstance(page, dict)]
    raw_blocks = list(getattr(parsed, "blocks", None) or [])

    pages_text: dict[int, str] = {}
    page_sizes: dict[int, dict[str, Any]] = {}
    for page in pages:
        page_no = _coerce_page_no(page.get("page_no"))
        if page_no is None:
            continue
        # 页 dict 应该自带 ``blocks``（``_extract_page_layout_from_content_list``
        # 就是这么建的）；早期产物 / 回放路径可能没带，退到顶层的同名块列表，
        # 否则剔表格就只能按行形态猜，整表行会被当成正文继续参与逐字比对。
        page_blocks = page.get("blocks")
        if not isinstance(page_blocks, list):
            page_blocks = [block for block in raw_blocks if _block_page_no(block) == page_no]
        pages_text[page_no] = _mineru_page_text_without_tables({**page, "blocks": page_blocks})
        page_sizes[page_no] = {"width": page.get("width"), "height": page.get("height")}

    blocks = normalize_mineru_blocks(raw_blocks, page_sizes)
    if not pages_text:
        # 解析「成功」但一页都没出来：等同失败，否则会静默变成「没有分歧」
        return {}, blocks, "MinerU 未返回任何按页结果"
    return pages_text, blocks, ""


def _block_page_no(block: Any) -> int | None:
    """读一个块的页码（dict 与 ``ParsedBlock`` 两种形状都认）。"""
    raw = block.get("page_no") if isinstance(block, Mapping) else getattr(block, "page_no", None)
    return _coerce_page_no(raw)


def _mineru_page_text_without_tables(page: Mapping[str, Any]) -> str:
    """取一页 MinerU 文本，**剔掉表格块**，只留参与逐字比对的部分。

    ## 为什么必须在输入侧剔、不能留给 ``compare_pages``

    ``page["text"]`` 现在是按块顺序拼接的（表格块也在里面，表格正文是一整行
    1000+ 字符），而 PaddleOCR-VL 那边表格是多行 GFM markdown。同一张表在两边
    的行切分与空白处理必然不同，直接喂给 difflib 就是每条表一条 high 级「替换」，
    把「张三 / 张叁」那种一字的真名错字淹没。

    所以在进比对之前就剔掉：有 ``blocks`` 就按块重建（仅保留非表格块，顺序不变）；
    没有块可用的降级路径只能按行过滤（与 VL 侧同一道 ``is_markdown_table_line``）。
    剩下的块文本恰好就是 ``parsed.text`` 与块内容同源的那一份（见 mineru_backend
    里 ``_content_block_text``），剔表格不丢正文。

    ``pages_text`` 的其余用途（页级 SKU 落盘、UI 展示）读的是同一份字典，因此表格
    内容也从那里消失——这是有意的：表格已经进了 Markdown / 块数据，在这里重复一遍
    只会造出一段没人能对上的单行文本。
    """
    blocks = page.get("blocks")
    if isinstance(blocks, list) and blocks:
        kept: list[str] = []
        for block in blocks:
            # 块的形状不固定：有的是 ``ParsedBlock`` 对象，有的是 dict（回放页缓存）。
            # 两种都要认，否则回放路径会把整张表又放回比对里。
            block_type = block.get("type") if isinstance(block, Mapping) else getattr(block, "type", None)
            if str(block_type or "").strip().lower() in MINERU_TABLE_BLOCK_TYPES:
                continue
            block_text = block.get("text") if isinstance(block, Mapping) else getattr(block, "text", None)
            text = str(block_text or "").strip()
            if text:
                kept.append(text)
        if kept:
            return "\n".join(kept)

    # 没有块可用（本地后端、或整页都是表格）：只能按行过滤表格形态的行。
    return "\n".join(
        line for line in str(page.get("text") or "").splitlines() if line.strip() and not is_markdown_table_line(line)
    )


def _run_paddleocr_vl(
    backend: Any,
    upload_path: Path,
    *,
    page_numbers: Sequence[int] | None,
    total_pages: int,
) -> tuple[dict[int, str], list[Any], str]:
    """PaddleOCR-VL：整份（或切好的页范围）PDF 上传，按 ``layoutParsingResults`` 下标恢复页号。

    页号只能按**下标 + 1** 推：VL 的结果里没有页码字段，它按上传文件的页序返回。
    切页之后上传的是一份从第 1 页开始的小 PDF，所以下标也是从 1 起。
    """
    payload = upload_path.read_bytes()
    result = backend.recognize_bytes(payload, is_pdf=True, page_count=total_pages)

    layout_results = _extract_layout_results(result)
    pages_text: dict[int, str] = {}
    for index, item in enumerate(layout_results):
        if not isinstance(item, dict):
            continue
        markdown = item.get("markdown")
        if isinstance(markdown, dict):
            text = str(markdown.get("text") or "")
        else:
            text = str(item.get("text") or "")
        pages_text[index + 1] = text

    if not pages_text:
        # 没有版面结果的模型（PP-OCRv5 之类）只能给整段文本，不能硬编页码：
        # 编出来就是假页码，分歧会指到错误的页。这时只返回空，让它按「失败」降级。
        merged = str(getattr(result, "text", "") or "")
        if merged.strip():
            return {}, [], "PaddleOCR-VL 未返回逐页版面结果（可能是模型未配置为 VL）"
        return {}, [], "PaddleOCR-VL 返回空结果"

    # 归一化要的是每页的 ``prunedResult``（块在 ``parsing_res_list`` 里），
    # 不是 ``layoutParsingResults[i]`` 本身——直接传后者会一个块都拿不到。
    pruned_results = [item.get("prunedResult") for item in layout_results if isinstance(item, dict)]
    blocks = normalize_paddleocr_vl_blocks(pruned_results)
    return pages_text, blocks, ""


def _extract_layout_results(result: Any) -> list[Any]:
    """从识别结果里取 ``layoutParsingResults``（结构见 paddleocr_api_service）。

    ``PaddleOCRApiResult`` 只保留合并文本与图片，逐页结构没有字段承载，
    所以真实运行时要靠后端暴露的原始结果；这里统一在多个可能的挂载点里找，
    找不到就返回空让调用方按失败处理——**不猜**。
    """
    for attr in ("layout_results", "layout_parsing_results", "pruned_results"):
        raw = getattr(result, attr, None)
        if isinstance(raw, list) and raw:
            return raw
    raw = getattr(result, "raw", None)
    if isinstance(raw, dict):
        results = raw.get("layoutParsingResults")
        if isinstance(results, list):
            return results
    return []


def _default_engine_factories() -> dict[str, Any]:
    """真实后端工厂。**延迟到线程里构造**：构造函数会读配置/校验 Key，可能抛异常。

    放在这里（而不是模块导入时）还有一个原因：没配 PaddleOCR 的部署上，
    双引擎开关即使误开也不该在 import 阶段就炸。
    """

    def _mineru() -> Any:
        from apps.document_parsing.services.backends.mineru_backend import MineruBackend

        return MineruBackend()

    def _paddleocr_vl() -> Any:
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        return PaddleOCRApiEngine(model=PADDLEOCR_VL_MODEL)

    return {ENGINE_MINERU: _mineru, ENGINE_PADDLEOCR_VL: _paddleocr_vl}


def _normalize_page_numbers(page_numbers: Sequence[int] | None) -> list[int] | None:
    """页码规整：去重 + 升序；空输入视为「全本」（None）。"""
    if not page_numbers:
        return None
    return sorted({int(no) for no in page_numbers if int(no) >= 1})


def _slice_pdf(source: Path, page_numbers: Sequence[int]) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    """把指定页切成一个临时小 PDF，返回 (临时目录持有者, 路径)。

    临时目录对象必须由调用方持有到用完为止：只返回 Path 的话目录会被
    ``TemporaryDirectory.__del__`` 立刻删掉，上传时文件已经不存在。
    """
    holder: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory(prefix="dual_engine_")
    target = Path(holder.name) / "pages.pdf"
    with fitz.open(source) as doc:
        total = int(doc.page_count)
        wanted = [no for no in page_numbers if 1 <= no <= total]
        if not wanted:
            raise ValueError(f"页范围 {list(page_numbers)} 超出 PDF 总页数 {total}")
        # 逐页单独插入：页范围可能不连续（关键页试点常常就是跳着挑的），
        # 用 export_segment_pdf 的连续区间会多带进不需要的页。
        out = fitz.open()
        try:
            for page_no in wanted:
                out.insert_pdf(doc, from_page=page_no - 1, to_page=page_no - 1)
            target.write_bytes(out.tobytes())
        finally:
            out.close()
    return holder, target


def _count_pages(path: Path) -> int:
    try:
        with fitz.open(path) as doc:
            return int(doc.page_count)
    except Exception:
        logger.warning("pdf_split_dual_engine_count_pages_failed", extra={"path": path.as_posix()})
        return 0


def _coerce_page_no(raw: Any) -> int | None:
    try:
        page_no = int(str(raw))
    except (TypeError, ValueError):
        return None
    return page_no if page_no >= 1 else None


#: 异常信息里的凭证痕迹。一个是 ``Authorization: bearer xxx`` 这类请求头，
#: 一个是 ``api_key=xxx`` 这类 query / 配置串。
_BEARER_RE = re.compile(r"(?i)(bearer\s+)\S+")
_API_KEY_RE = re.compile(r"(?i)(api_key[=:]\s*)\S+")


def _sanitize(message: str) -> str:
    """错误信息脱敏并截断。

    为什么必须脱敏：后端异常里可能带完整请求头/URL（含 API Key）。
    summary 会随 ``PdfSplitJobOut`` 透给前端，密钥不能出现在那里。
    """
    text = _BEARER_RE.sub(r"\1***", str(message or ""))
    text = _API_KEY_RE.sub(r"\1***", text)
    return text[:400]
