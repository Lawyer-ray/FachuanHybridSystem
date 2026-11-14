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
from pathlib import Path
from typing import Any

import pymupdf as fitz

from .export_utils import export_segment_pdf

logger = logging.getLogger("apps.pdf_splitting")

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


def parse_in_batches(
    *,
    source_path: Path,
    page_numbers: list[int],
    parse_one: Any,
    on_batch_done: Any = None,
    on_progress: Any = None,
    size: int | None = None,
    concurrency: int | None = None,
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
        size / concurrency: 覆盖默认配置（测试用）。

    Returns:
        合并后的 `{原始页号: OCRPageResult}`。**只含成功的页**；失败的批次
        不出现在结果里，交给上层决定是否走本地 OCR 兜底或整体重试。
    """
    batches = plan_batches(page_numbers, size=size)
    if not batches:
        return {}

    # 只有一批且页号本来就是连续全文：不必切 PDF。
    # 切一刀虽只几十毫秒，但会让「单批场景」的行为与原实现不一致
    # （测试桩/外部实现不必支持从任意路径读），且白白产生一个临时文件。
    ordered = sorted(set(int(no) for no in page_numbers))
    if len(batches) == 1 and batches[0] == ordered and ordered[0] == 1:
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
    merged: dict[int, Any] = {}
    workers = min(concurrency or batch_concurrency(), len(batches))

    def run_batch(batch: list[int]) -> tuple[list[int], dict[int, Any]]:
        """切小 PDF → 解析 → 把页码映射回原始页号。"""
        payload = slice_pdf(source_path, batch)
        tmp_path: Path | None = None
        try:
            # MinerU 的解析接口只接受路径，必须落一个临时文件；
            # 用 delete=False 以便 Windows 上也能在关闭后再删。
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="pdf_split_batch_") as handle:
                handle.write(payload)
                tmp_path = Path(handle.name)

            rel = parse_one(tmp_path)
            offset = batch[0] - 1
            mapped = {int(page_no) + offset: value for page_no, value in rel.items()}
            missing = [page_no for page_no in batch if page_no not in mapped]
            if missing:
                logger.warning(
                    "pdf_split_batch_incomplete",
                    extra={"batch": f"{batch[0]}-{batch[-1]}", "missing": missing[:10], "missing_count": len(missing)},
                )
            return batch, mapped
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:  # 临时文件删不掉不影响解析结果
                    logger.debug("临时批文件删除失败: %s", tmp_path)

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pdfsplit-batch") as pool:
        futures = {pool.submit(run_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                _, mapped = future.result()
            except Exception:
                # 单批失败不能中断其他批：其他批的成果仍要落盘，
                # 失败的页留给上层用本地 OCR 兜底或下次重跑补。
                logger.exception(
                    "pdf_split_batch_failed",
                    extra={"batch": f"{batch[0]}-{batch[-1]}", "pages": len(batch)},
                )
                continue

            merged.update(mapped)
            resolved += len(mapped)
            if on_batch_done is not None:
                on_batch_done(batch, mapped)
            if on_progress is not None:
                on_progress(resolved, total)

    logger.info(
        "pdf_split_batches_done",
        extra={
            "batches": len(batches),
            "workers": workers,
            "resolved": resolved,
            "total": total,
            "source": source_path.name,
        },
    )
    return merged
