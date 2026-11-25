"""云端解析的**分批**执行（断点续传）。

## 问题

`OCRHandler.parse_cloud_pages` 把整份 PDF 一次性交给 MinerU：一次 HTTP 上传、
一次云端排队、一次等待全部返回。164 页的真实卷宗在这种模式下有两个
致命后果：

1. **进程一死就全部归零**。135 页的成果只存在于调用栈里，`analysis/` 目录是空的，
   没有任何中间产物可以复用，重启只能从第 1 页开始。实测同一份材料连续两次死在
   同样的位置（135/164），每次都从零开始。
2. **进度是假的**。`processed_pages` 只是本地计数，云端在算的那一个小时里
   前端看到的数字和实际进展没有关系。

## 做法

把页切成若干批，**每批单独切一份小 PDF → 上传 → 解析 → 立即逐页写缓存**。

```
原 PDF(164 页)
  ├─ 批1[p1..p40]   → 小PDF → MinerU → 写 40 个页缓存  ← 落盘
  ├─ 批2[p41..p80]  → 小PDF → MinerU → 写 40 个页缓存  ← 落盘
  ├─ 批3[p81..p120] → 小PDF → MinerU → 写 40 个页缓存  ← 落盘
  └─ 批4[p121..164] → 小PDF → MinerU → 写 44 个页缓存  ← 落盘
```

断在任何一批，前面的批次已经在缓存里；重跑时 `_resolve_pending_pages` 会先读缓存
跳过它们，只补剩下的。这就是「断点续传」，不需要额外维护进度表——**缓存本身
就是进度**。

## 为什么本地切 PDF 而不是要求云端支持页码

MinerU 的批量上传接口只有 `{"files": [...], "model_version": ...}`，没有页范围
参数（`mineru_backend.py::_upload_file`）。所以分批只能在本地切。所幸
`export_utils.export_segment_pdf` 已经能按页范围切且是按需零拷贝写内存，
切一份 40 页的小 PDF 只要几十毫秒，相比云端解析的分钟级成本可忽略。

## 单批体积（字节上限）

只按页数切是不够的：网关/浏览器侧对**单批 PDF** 有 48 MiB 硬上限，超出直接 413
（实测 66 MiB 被拒），而手机高清拍照件常见 2–3 MiB/页——25 页一批就是 50–75 MiB，
一批都传不上去，那 25 页只能退回本地逐页 OCR。所以切批同时受「页数」与「字节」
两条约束：先按页数贪心切，只有超上限的批才二分（`slice_batch_within_limit`）。

## 并发

多批可以并发跑：`CredentialPool` 已经支持「多 Key 轮询 + 每 Key 并发上限 +
失败冷却」，一批占一个 Key，天然把账号用满。默认并发取 `min(批数, 3)`，
保守一些避免把账号打到限流；可用 `PDF_SPLIT_CLOUD_BATCH_CONCURRENCY` 调整。
"""

from __future__ import annotations

import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import is_dataclass, replace
from pathlib import Path
from typing import Any, cast

import pymupdf as fitz

from apps.document_parsing.exceptions.parsing_exceptions import DocumentParsingError

from .export_utils import export_segment_pdf

logger = logging.getLogger("apps.pdf_splitting")

#: 单段解析的**真实**失败族：三个解析后端都把失败收敛成 ``DocumentParsingError``
#: 家族（MinerU 的 ``MineruAPIError`` / ``ParsingTimeoutError`` 均在其下），而落临时文件与
#: 切 PDF 失败是 ``OSError`` / ``ValueError``。
#:
#: 为什么不用裸 ``except Exception``：段级失败要能被「看得见地」吞掉（其他段的成果必须落盘），
#: 但真出新的失败形态时应带着栈当场暴露，而不是悄悄变成「这批没结果」——静默降级比失败
#: 难查得多。``forbid-new-broad-except`` 棘轮也只许下调，不新增。

#: 每批页数。
#:
#: 25 页的依据（从 40 调小）：
#: · 单批失败损失从 40 页降到 25 页（重跑代价更低）；
#: · 批间交错更密，进度条推进更穏定，律师看到“在动”的频率更高；
#: · 固定开销（上传/排队）被摊薄的幅度变小，但有缓存托底，总时长仍可控。
#:
#: 同时受另一条硬约束：Django-Q 的 worker 超时（DJANGO_Q_TIMEOUT，默认 600s）
#: 是整个任务的阖值，不是单批的。批拆得细只能降低“死一次损失多少”，
#: 不能把总时长拉长——超时照样被杀。
DEFAULT_BATCH_PAGES = 25

#: 并发批次数上限。受凭证池大小限制，实际并发不会超过可用 Key 数。
#:
#: 从 3 提到 5：批更细后需要更高并发才能把总时长压下来（多账号轮询本就
#: 支持）。若账号少，`CredentialPool` 会自然排队，不会超额限流。
DEFAULT_BATCH_CONCURRENCY = 5

#: 单批 PDF 的**字节**上限（MiB）。默认 32，可用 `PDF_SPLIT_CLOUD_BATCH_MAX_MIB` 调整。
#:
#: 硬上限来自网关/浏览器侧：单批 PDF 超过 48 MiB 直接 413（实测 66 MiB 被拒）。
#: 为什么是 32 MiB 而不是贴着 48 MiB（留 16 MiB / 33% 余量）：
#: · 48 MiB 是**拒绝阈值**不是推荐值，贴着跑等于把偶发 413 变成常态，重试也只是再撞一次；
#: · 上传体还要被 multipart 包装，实际请求体比文件本身更大；
#: · 同一批页经 PyMuPDF 重写后字节数可能略大于原文件，余量给它兜底。
DEFAULT_BATCH_MAX_MIB = 32

_MIB = 1024 * 1024


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("忽略非法环境变量 %s=%r，使用默认 %d", name, raw, default)
        return default


def batch_size() -> int:
    return _env_int("PDF_SPLIT_CLOUD_BATCH_PAGES", DEFAULT_BATCH_PAGES)


def batch_concurrency() -> int:
    return _env_int("PDF_SPLIT_CLOUD_BATCH_CONCURRENCY", DEFAULT_BATCH_CONCURRENCY)


def batch_max_bytes() -> int:
    """单批小 PDF 的字节上限（`PDF_SPLIT_CLOUD_BATCH_MAX_MIB`，单位 MiB）。"""
    return _env_int("PDF_SPLIT_CLOUD_BATCH_MAX_MIB", DEFAULT_BATCH_MAX_MIB) * _MIB


def plan_batches(page_numbers: list[int], *, size: int | None = None) -> list[list[int]]:
    """把待解析页号切成连续的批。

    **必须连续**：批次内部页号连续，切出来的小 PDF 才能用
    `insert_pdf(from_page, to_page)` 一次取一段；如果页号零散（比如只有偶数页
    缺），切成连续区间会让小 PDF 里夹进无关页，页码映射会错。

    所以这里只做「按连续区间切」：先把稀疏页号归并成连续段，再把每个连续段
    按 size 切块。这样 `offset` 与原始页号的换算始终成立。
    """
    if not page_numbers:
        return []

    size = max(1, size or batch_size())
    ordered = sorted({int(no) for no in page_numbers})

    batches: list[list[int]] = []
    run: list[int] = []
    for page_no in ordered:
        # 页号断开 → 先收尾当前连续段
        if run and page_no != run[-1] + 1:
            batches.extend(_split_run(run, size))
            run = []
        run.append(page_no)
        if len(run) >= size:
            batches.extend(_split_run(run, size))
            run = []
    if run:
        batches.extend(_split_run(run, size))
    return [batch for batch in batches if batch]


def _split_run(run: list[int], size: int) -> list[list[int]]:
    return [run[index : index + size] for index in range(0, len(run), size)]


def rebase_page_result(value: Any, page_no: int) -> Any:
    """把一批结果的「批内相对页号」改写成**整卷绝对页号**。

    ## 为什么必须同时改「键」和「值」（2026-11-20 事故）

    `parse_in_batches` 原本只平移字典的键：

        mapped = {rel + offset: value}      # 键变绝对页号，value.page_no 仍是相对号

    而下游写 OCR 页缓存时文件名取自 **`result.page_no`**（见
    `pipeline._persist_cloud_batch`）。于是每一批都把自己的结果写到「1..n」这批
    缓存文件名上，**不同批互相覆盖、谁最后写完谁赢**（完成顺序决定归属）。
    更糟的是读缓存时 `read_ocr_cache` 会把请求的页号强行盖回 result，中毒从此
    不可见——之后每次重跑都把脏数据当真理读回来。

    实测后果：93 页卷宗的 `pages.json` 里出现「相隔 50 页的同一段文字」
    （p2/p52 疾病诊断证明书、p3/p53 出院记录、p4/p54、p6/p56…），而缓存里同一段
    文字又落在 −4、+46、+65 等不同偏移上——那是**多次中毒叠加**的指纹。

    改值而不只是改键，一处修掉三个后果：缓存按绝对页号命名、断点续传读到的是
    正确的那一页、`pages.json` 的页号↔文本绑定不可能再错位。
    """
    if not is_dataclass(value):
        return value
    layout = getattr(value, "layout", None)
    new_layout = layout
    if isinstance(layout, dict) and "page_no" in layout:
        # layout 是「该页的版面」，里面的 page_no 与 result.page_no 必须同源；
        # 只改外层会让下游按 layout["page_no"] 取框时又落回相对号。
        new_layout = {**layout, "page_no": page_no}
    try:
        # `is_dataclass` 只窄化到 DataclassInstance，而 `replace()` 的类型变量要求具体类；
        # 这里刻意 cast 到 Any —— 形状在运行期已由 is_dataclass 与 TypeError 兜住。
        return replace(cast(Any, value), page_no=page_no, layout=new_layout)
    except TypeError:  # pragma: no cover - 值形状变化时宁可原样返回，不要炸掉整批
        return value


def slice_pdf(source_path: Path, page_numbers: list[int]) -> bytes:
    """把 `page_numbers` 覆盖的连续区间切出来，作为独立小 PDF 的字节。

    前提：`page_numbers` 连续且升序（由 `plan_batches` 保证）。
    """
    if not page_numbers:
        raise ValueError("page_numbers 不能为空")
    first, last = page_numbers[0], page_numbers[-1]
    if last - first + 1 != len(page_numbers):
        raise ValueError(f"页号必须连续: {first}..{last} 但收到 {len(page_numbers)} 页")

    with fitz.open(source_path.as_posix()) as source:
        return export_segment_pdf(source, first, last)


def slice_batch_within_limit(source_path: Path, batch: list[int], *, max_bytes: int) -> list[tuple[list[int], bytes]]:
    """把一批页切成若干段，**每一段切出的 PDF 字节数都不超过 `max_bytes`**。

    做法是「超限才二分」：页数维度的贪心切已经由 `plan_batches` 做完，这里只对
    超上限的批继续二分——正常批只切一刀，不必为每个批都把整本重切一遍。

    单页本身超限（手机拍的一整页大图、整页扫描）时，这一页**独占一段并告警**：
    网关仍可能 413，但绝不静默丢页——丢一页会让整卷页序错位，比一次看得见的
    上传失败严重得多（上层会把它记成失败页走本地兜底或下次重跑）。

    Returns:
        按页号升序、互不重叠的 `(页号, 小PDF 字节)` 列表，合起来正好是 `batch`
        ——同一份源文件与页号永远切出同样的结果（不丢页、不重页）。
    """
    payload = slice_pdf(source_path, batch)
    if len(payload) <= max_bytes:
        return [(batch, payload)]
    if len(batch) == 1:
        # 单页就超限：只能独占一批，但**必须留痕**（否则律师只会看到一次 413 重试）
        logger.warning(
            "pdf_split_batch_single_page_over_limit",
            extra={"page_no": batch[0], "bytes": len(payload), "limit": max_bytes, "source": source_path.name},
        )
        return [(batch, payload)]
    logger.info(
        "pdf_split_batch_over_limit_split",
        extra={"batch": f"{batch[0]}-{batch[-1]}", "pages": len(batch), "bytes": len(payload), "limit": max_bytes},
    )
    middle = len(batch) // 2
    return [
        *slice_batch_within_limit(source_path, batch[:middle], max_bytes=max_bytes),
        *slice_batch_within_limit(source_path, batch[middle:], max_bytes=max_bytes),
    ]


def _source_size(path: Path) -> int | None:
    """源文件字节数（整本直传时它就是上传体的大小）；读不到时返回 `None`。

    读不到只可能意味着源文件不可用，那时不允许整本直传：交给切批路径去抛
    一个能说明问题的错误（`fitz.open` 打不开），而不是先传一次注定失败的文件。
    """
    try:
        return path.stat().st_size
    except OSError:
        logger.warning("pdf_split_source_stat_failed", extra={"source": path.name})
        return None


def _parse_batch_payload(payload: bytes, page_numbers: list[int], parse_one: Any) -> dict[int, Any]:
    """把一段小 PDF 落成临时文件交给 `parse_one`，并把批内相对页号映射回整卷绝对页号。"""
    tmp_path: Path | None = None
    try:
        # MinerU 的解析接口只接受路径，必须落一个临时文件；
        # 用 delete=False 以便 Windows 上也能在关闭后再删。
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="pdf_split_batch_") as handle:
            handle.write(payload)
            tmp_path = Path(handle.name)

        rel = parse_one(tmp_path)
        offset = page_numbers[0] - 1
        # **键和值一起重定基**：只平移键会让每批的缓存写到同一批文件名上、
        # 互相覆盖（见 rebase_page_result 的注释与 2026-11-20 事故）。
        mapped = {
            int(page_no) + offset: rebase_page_result(value, int(page_no) + offset) for page_no, value in rel.items()
        }
        missing = [page_no for page_no in page_numbers if page_no not in mapped]
        if missing:
            logger.warning(
                "pdf_split_batch_incomplete",
                extra={
                    "batch": f"{page_numbers[0]}-{page_numbers[-1]}",
                    "missing": missing[:10],
                    "missing_count": len(missing),
                },
            )
        return mapped
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:  # 临时文件删不掉不影响解析结果
                logger.debug("临时批文件删除失败: %s", tmp_path)


def parse_in_batches(
    *,
    source_path: Path,
    page_numbers: list[int],
    parse_one: Any,
    on_batch_done: Any = None,
    on_progress: Any = None,
    size: int | None = None,
    concurrency: int | None = None,
    max_bytes: int | None = None,
) -> dict[int, Any]:
    """分批解析，每批完成立即回调（用于写缓存）并汇报进度。

    Args:
        source_path: 原始 PDF。
        page_numbers: 需要解析的页号（可稀疏）。
        parse_one: 可调用对象 `(mini_pdf_path) -> {page_no: OCRPageResult}`，
            封装了「用哪个 backend、怎么调 MinerU」。页码应相对小 PDF（1..n）。
        on_batch_done: 每批成功后的回调 `(batch_page_numbers, results)`，
            **在这里写缓存**——这是断点续传的唯一落盘点。
        on_progress: `(resolved, total)` 进度回调。
        size / concurrency / max_bytes: 覆盖默认配置（测试用）。`max_bytes` 是单批
            小 PDF 的字节上限，默认取 `batch_max_bytes()`；超限的批会被二分。

    Returns:
        合并后的 `{原始页号: OCRPageResult}`。**只含成功的页**；失败的批次
        不出现在结果里，交给上层决定是否走本地 OCR 兜底或整体重试。
    """
    batches = plan_batches(page_numbers, size=size)
    if not batches:
        return {}

    limit = max(1, max_bytes if max_bytes is not None else batch_max_bytes())

    # 只有一批且页号就是 1..n：不必切 PDF（原实现的「整本一次」快路径）。
    # 切一刀虽只几十毫秒，但会让「单批场景」的行为与原实现不一致
    # （测试桩/外部实现不必支持从任意路径读），且白白产生一个临时文件。
    # 直传的也是「一批 PDF」，同样要守字节上限——这时量源文件就够了，它就是上传体。
    ordered = sorted(set(int(no) for no in page_numbers))
    single_batch_from_first = len(batches) == 1 and batches[0] == ordered and ordered[0] == 1
    direct_size = _source_size(source_path) if single_batch_from_first else None
    if single_batch_from_first and direct_size is not None and direct_size <= limit:
        # 异常**不在这里吞**：必须冒泡给 `_parse_cloud`，它要靠异常内容
        # 拼出 `ocr_fallback_reason` 写进 summary——吞掉的话律师只能看到
        # 「云端解析失败」而不是「mineru: RuntimeError: ...」。
        direct = parse_one(source_path)
        if on_batch_done is not None:
            on_batch_done(ordered, direct)
        if on_progress is not None:
            on_progress(len(direct), len(ordered))
        # parse_one 是注入的回调（Any）：这里显式收窄，避免 no-any-return
        return dict(direct)

    total = len(set(page_numbers))
    resolved = 0
    segments_done = 0
    merged: dict[int, Any] = {}
    workers = min(concurrency or batch_concurrency(), len(batches))

    def run_batch(batch: list[int]) -> list[tuple[list[int], dict[int, Any]]]:
        """切小 PDF（超字节上限就二分）→ 解析 → 把页码映射回原始页号。

        返回**段列表**：一批可能因体积被二分成多个上传体，每段都要单独落盘、
        单独计进度（断点续传的粒度不能因为切批而变粗）。
        """
        segments: list[tuple[list[int], dict[int, Any]]] = []
        for pages, payload in slice_batch_within_limit(source_path, batch, max_bytes=limit):
            try:
                segments.append((pages, _parse_batch_payload(payload, pages, parse_one)))
            except (DocumentParsingError, OSError, ValueError, RuntimeError):
                # 单段失败不能中断其他段：其他批/段的成果仍要落盘，
                # 失败的页留给上层用本地 OCR 兜底或下次重跑补。
                logger.exception(
                    "pdf_split_batch_failed",
                    extra={"batch": f"{pages[0]}-{pages[-1]}", "pages": len(pages), "bytes": len(payload)},
                )
        return segments

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pdfsplit-batch") as pool:
        futures = {pool.submit(run_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                segments = future.result()
            except Exception:
                # 连切 PDF 都没成（源文件打不开/权限）：整批都没有结果
                logger.exception(
                    "pdf_split_batch_failed",
                    extra={"batch": f"{batch[0]}-{batch[-1]}", "pages": len(batch)},
                )
                continue

            for pages, mapped in segments:
                merged.update(mapped)
                resolved += len(mapped)
                segments_done += 1
                if on_batch_done is not None:
                    on_batch_done(pages, mapped)
                if on_progress is not None:
                    on_progress(resolved, total)

    logger.info(
        "pdf_split_batches_done",
        extra={
            "batches": len(batches),
            "segments": segments_done,
            "workers": workers,
            "resolved": resolved,
            "total": total,
            "max_bytes": limit,
            "source": source_path.name,
        },
    )
    return merged
