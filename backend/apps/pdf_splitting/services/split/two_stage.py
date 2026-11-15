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
TASK_CROSS_CHECK = "apps.pdf_splitting.tasks.run_cross_check_stage"
TASK_SEGMENT = "apps.pdf_splitting.tasks.run_segment_stage"


def submit_extract_stage(job: PdfSplitJob) -> str:
    """提交第一阶段（取字）。"""
    # submit() 返回 Any（task 后端可替换）：显式 str() 收窄
    return str(
        build_task_submission_service().submit(
            TASK_EXTRACT,
            args=[str(job.id)],
            task_name=f"pdf_split_extract_{job.id}",
        )
    )


def submit_cross_check_stage(job: PdfSplitJob) -> str:
    """提交交叉比对阶段（双引擎）。

    ## 为什么必须独立成任务（而不是留在我取字阶段里）

    双引擎要把整本 PDF **再解析一遍**（两个引擎各一次），164 页实测要十几分钟。
    而 Django-Q 的 `Q_CLUSTER.timeout` 默认 600s 是**单个任务**的硬阀值：超时
    直接杀 worker 进程，连 `finally` 都不执行——任务不留任何记录（实测
    `django_q_task` 里一行都没有），DB 里只剩一个 `stage=cross_check` 的僵尸。

    心跳线程救不了这个：进程整个被杀，任何线程都没机会跑。唯一有效的做法
    就是跟 `extract → segment` 一样拆成独立任务，让这一段有自己完整的 600s。
    """
    return str(
        build_task_submission_service().submit(
            TASK_CROSS_CHECK,
            args=[str(job.id)],
            task_name=f"pdf_split_cross_check_{job.id}",
        )
    )


def submit_segment_stage(job: PdfSplitJob) -> str:
    """提交分段阶段。

    独立提交是拆链的关键：前面每个阶段无论成功或失败，本阶段的 600s 预算
    都是全新的，不会被前面阶段的耗时抵掉。
    """
    return str(
        build_task_submission_service().submit(
            TASK_SEGMENT,
            args=[str(job.id)],
            task_name=f"pdf_split_segment_{job.id}",
        )
    )


def _pages_payload_path(storage: PdfSplitStorage) -> Path:
    return storage.pages_json_path


def _page_quality_payload_path(storage: PdfSplitStorage) -> Path:
    return storage.page_quality_json_path


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


def save_page_quality(storage: PdfSplitStorage, payload: dict[str, Any]) -> None:
    """落盘页面质量画像（summary 区块 + 逐页画像）。

    必须在取字阶段落盘：分段阶段要据此给每段贴 ``quality_flags``，
    而那时取字结果只剩 pages.json，拿不到逐页判定。
    """
    storage.write_json(_page_quality_payload_path(storage), payload)


def load_page_quality(storage: PdfSplitStorage) -> dict[str, Any]:
    """读回页面质量画像；不存在或损坏返回空表（旧任务没这个产物，分段阶段照常跑）。"""
    path = _page_quality_payload_path(storage)
    try:
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("pdf_split_page_quality_unreadable", extra={"path": str(path)})
        return {}
    return raw if isinstance(raw, dict) else {}


def _engine_disagreements_payload_path(storage: PdfSplitStorage) -> Path:
    return storage.engine_disagreements_json_path


def save_engine_disagreements(storage: PdfSplitStorage, payload: dict[str, Any]) -> None:
    """落盘双引擎分歧（summary 区块）。

    为什么必须在取字阶段落盘：分歧是在取字阶段跟双引擎一起算出来的，而 summary
    要到分段阶段才写 DB。不落盘就得在分段阶段重跑两个云端引擎——等于整本卷宗
    再付一次费。
    """
    storage.write_json(_engine_disagreements_payload_path(storage), payload)


def load_engine_disagreements(storage: PdfSplitStorage) -> dict[str, Any]:
    """读回双引擎分歧；不存在或损坏返回空表（旧任务/关着开关时都没这个产物）。"""
    path = _engine_disagreements_payload_path(storage)
    try:
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("pdf_split_engine_disagreements_unreadable", extra={"path": str(path)})
        return {}
    return raw if isinstance(raw, dict) else {}


def advance_after_extract(job: PdfSplitJob, *, pages_count: int) -> None:
    """取字完成后推进到下一阶段：开了双引擎就去交叉比对，否则直接分段。

    双引擎要再解析一遍整本，必须给它单独的 600s 预算（为什么见
    `submit_cross_check_stage`）；没开双引擎时多排一个空阶段只是白跑一趟，
    所以在这里直接短路到分段。
    """
    from apps.pdf_splitting.models import parse_dual_engines

    engines = parse_dual_engines(getattr(job, "dual_engines", ""))
    if len(engines) >= 2:
        advance_to_cross_check_stage(job, pages_count=pages_count)
        return
    advance_to_segment_stage(job, pages_count=pages_count)


def advance_to_cross_check_stage(job: PdfSplitJob, *, pages_count: int) -> None:
    """取字完成后推进到交叉比对阶段，并把它排进队列。"""
    now = timezone.now()
    task_id = submit_cross_check_stage(job)
    # progress 压到 90：取字确实做完了（processed_pages 满值不回退），
    # 但整条流水线还没完，不能让前端看到 100% 后再纹丝不动十几分钟。
    PdfSplitJob.objects.filter(id=job.id).update(
        stage=PdfSplitStage.CROSS_CHECK,
        task_id=task_id,
        heartbeat_at=now,
        updated_at=now,
        progress=90,
    )
    logger.info(
        "pdf_split_stage_advanced",
        extra={"job_id": str(job.id), "stage": "cross_check", "pages": pages_count, "task_id": task_id},
    )


def advance_to_segment_stage(job: PdfSplitJob, *, pages_count: int) -> None:
    """推进到分段阶段，并把它排进队列。"""
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
