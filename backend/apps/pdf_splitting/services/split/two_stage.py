"""两阶段任务链：取字 → 分段。

## 为什么必须拆

Django-Q 的 worker 超时（`DJANGO_Q_TIMEOUT`，默认 600s）是**整个任务**的闐值，
不是单次调用的。164 页的真实卷宗上：

| 阶段 | 实测耗时 | 备注 |
|:--|:--|:--|
| 云端 OCR（25 页/批，5 并发） | ~2-4 分钟 | 批量已控住 |
| LLM 分段（25 页/批，重叠窗口） | ~4-8 分钟 | 受 LLM 限制 |
| 落库/建 Markdown | 十几秒 | |

合在一起很轻松就超过 600s——实测 164 页任务跑到 499s 就被杀。拆开后每段
各自有 600s 预算，两段都能稳住。

## 中间产物

`extract` 阶段除逐页 OCR 缓存外，还把整个 `pages` 列表落 `pages.json`。
这是第二阶段的输入，也是断点续传的依据：

- OCR 缓存命中 → 第一阶段不用重跑云端；
- `pages.json` 存在 → 第二阶段不用重跑第一阶段。

## 兼容

`split_mode=PAGE_SPLIT`（按页数均分）不涉及识别，仍走单任务；
`MANUAL_SPLIT` 直接进待复核。只有 `CONTENT_ANALYSIS` 走两段。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from django.utils import timezone

from apps.core.dependencies.core import build_task_submission_service
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitStage
from apps.pdf_splitting.services.storage import PdfSplitStorage

logger = logging.getLogger("apps.pdf_splitting")

TASK_EXTRACT = "apps.pdf_splitting.tasks.run_extract_stage"
TASK_SEGMENT = "apps.pdf_splitting.tasks.run_segment_stage"


def submit_extract_stage(job: PdfSplitJob) -> str:
    """提交第一阶段（取字）。"""
    return build_task_submission_service().submit(
        TASK_EXTRACT,
        args=[str(job.id)],
        task_name=f"pdf_split_extract_{job.id}",
    )


def submit_segment_stage(job: PdfSplitJob) -> str:
    """提交第二阶段（分段）。

    独立提交是拆链的关键：第一阶段无论成功或失败，第二阶段的 600s 预算
    都是全新的，不会被第一阶段的耗时抵掉。
    """
    return build_task_submission_service().submit(
        TASK_SEGMENT,
        args=[str(job.id)],
        task_name=f"pdf_split_segment_{job.id}",
    )


def _pages_payload_path(storage: PdfSplitStorage) -> Path:
    return storage.pages_json_path


def save_pages(storage: PdfSplitStorage, pages: list[Any]) -> None:
    """把取字结果落盘（第二阶段与断点续传的输入）。"""
    payload = [asdict(page) if hasattr(page, "__dataclass_fields__") else page for page in pages]
    storage.write_json(_pages_payload_path(storage), payload)


def load_pages(storage: PdfSplitStorage) -> list[dict[str, Any]]:
    """读回 pages.json；不存在或损坏返回空表。"""
    path = _pages_payload_path(storage)
    try:
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("pdf_split_pages_unreadable", extra={"path": str(path)})
        return []
    return raw if isinstance(raw, list) else []


def advance_to_segment_stage(job: PdfSplitJob, *, pages_count: int) -> None:
    """第一阶段完成后把任务推进到第二阶段，并把它排进队列。"""
    now = timezone.now()
    task_id = submit_segment_stage(job)
    PdfSplitJob.objects.filter(id=job.id).update(
        stage=PdfSplitStage.SEGMENT,
        task_id=task_id,
        heartbeat_at=now,
        updated_at=now,
        progress=max(50, int(job.progress or 0)),
    )
    logger.info(
        "pdf_split_stage_advanced",
        extra={"job_id": str(job.id), "stage": "segment", "pages": pages_count, "task_id": task_id},
    )


def mark_stage_failed(job_id: Any, stage: str, message: str) -> None:
    """阶段级失败：写清楚死在哪个阶段，方便排障与重试决策。"""
    now = timezone.now()
    PdfSplitJob.objects.filter(id=job_id).update(
        status=PdfSplitJobStatus.FAILED,
        stage=stage,
        finished_at=now,
        updated_at=now,
        error_message=message[:4000],
    )
