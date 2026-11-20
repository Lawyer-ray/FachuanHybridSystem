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
有**自己独立的预算**（见下方 `*_STAGE_TIMEOUT_SECONDS`，由提交时逐任务传入
django-q，覆盖集群默认值）。

拆链只解决「前一段吃掉后一段的时间」，不解决「单段自己就不够」。云服务慢的时候
双引擎一段就能超 600s，所以两件事都做了：拆链 + 按阶段放宽预算。

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
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from django.utils import timezone

from apps.core.dependencies.core import build_task_submission_service
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitStage
from apps.pdf_splitting.services.storage import PdfSplitStorage

from .ocr_handler import OCRStageBudget

logger = logging.getLogger("apps.pdf_splitting")

TASK_EXTRACT = "apps.pdf_splitting.tasks.run_extract_stage"
TASK_CROSS_CHECK = "apps.pdf_splitting.tasks.run_cross_check_stage"
TASK_SEGMENT = "apps.pdf_splitting.tasks.run_segment_stage"

#: 各阶段自己的 Django-Q 墙钟预算（秒）。
#:
#: ## 为什么不能只靠全局 `DJANGO_Q_TIMEOUT`
#:
#: 全局值是一个**所有任务共用**的数字，而这三个阶段的耗时特征差得很远：
#:
#: | 阶段 | 164 页实测 | 云服务慢时的合理上限 |
#: |:--|:--|:--|
#: | extract（单引擎取字） | ~2-4 分钟 | 20 分钟 |
#: | cross_check（双引擎） | 269s（2026-11-16）| 45 分钟 |
#: | segment（LLM 分段） | ~130s | 35 分钟（按最坏路径推算，见下） |
#:
#: 把全局值抬到能容忍最坏情况（45 分钟），等于让**每一个**普通任务都享有
#: 45 分钟的失控窗口：真卡死时 worker 槽位要白占这么久才能回收。反之把全局
#: 留在 600s，双引擎一遇云端排队/重传就会被硬杀，连 `finally` 都跑不到。
#:
#: 所以这里用 django-q 的**单任务 timeout**（`worker.py` 里
#: `task.pop("timeout", timeout)`，每个任务可覆盖集群默认值）：全局保持小值
#: 兜底，重活按需单独放宽。
#:
#: ## 数值怎么定的
#:
#: extract / cross_check 取「实测值 × 3 左右」的整数分钟，理由见 `mineru_backend.py`
#: 的同一次事故：MinerU 那一路曾因 TCP 半死静默阻塞到 4347s（72 分钟），说明云服务
#: 侧的长尾远超直觉。×3 是给「云端排队 + 一次重传」留余量，同时仍能在真卡死时收口。
#:
#: segment **不能按实测 ×3 定**：它的耗时上界由分批重试策略决定，而不是由平均值决定。
#: 按当前代码推算（`segment_batch.DEFAULT_BATCH_RETRY=2`、
#: `llm_segment_detector._WALL_TIMEOUT_SECONDS=480`、`DEFAULT_SEGMENT_CONCURRENCY=4`）：
#:
#: · 单批耗尽重试 = 3 × 480s = **1440s**，已经超过原来的 1200s——**一批**偶发抖动
#:   就足以让整阶段被硬杀，而心跳线程还在正常跳（看门狗认为它活着），无从申辩；
#: · 并行度 4、164 页 7 批：慢批占着一个槽跑 1440s 期间，其余 6 批在另外 3 个槽上
#:   早已跑完，所以尾部只需再留一轮墙钟 480s；
#: · 合并 + 跨页一致性校对 + Markdown 重建 + 落盘再留 180s。
#:
#: 合计 1440 + 480 + 180 = 2100s = 35 分钟。**刻意不抬到 45 分钟**：本预算只覆盖
#: 「至多一批耗尽重试」这一实测形态（7 批里 1 批偶发失败）。多批同时耗尽意味着 LLM
#: 整体不可用，那时就该被杀并由整轮规则引擎兜底，而不是让 worker 槽白占更久。
#:
#: ## extract 为什么从 20 分钟抬到 24 分钟（2026-11-20 事故重算）
#:
#: 事故时间线（93 页，单引擎）：11:40:43 启动 → 11:41:56 MinerU 4 批跑完（73s）→
#: 11:43:23 最后一拍心跳 → PaddleOCR 单页 **8 次 300s 超时** → 11:57 恢复 →
#: 11:59 跑完 93/93（progress=100）→ 12:00:43 按 1200s 硬杀。
#:
#: 即：**真正干活 + 抖动 = 1096s**，之后还剩下不到 104s 写页缓存/ pages.json /
#: 摘要 / 推进阶段——20 分钟**从算术上就装不下这次事故**（连“零额外抖动”都不够）。
#:
#: 24 分钟 = 1440s = 1096s（实测形态）+ 150s（尾部，见下）+ ~190s 余量。它不再是
#: “拍一个大数字求安心”：真正的上界由**降级**给出——最后一次性页云端调用在
#: `剩余 ≥ 单页最坏 300s + 余量 60s` 时才会发出（见 `ocr_handler.OCRStageBudget`），
#: 所以本阶段最迟在 `deadline` 前自然结束，不会被 django-q 硬杀。
#:
#: 刻意**不**抬到 30/45 分钟：它会把“真卡死”时白占 worker 槽的时间拉长，而
#: 超出 1440s 的那些情况（多页连续抖动、云端整体不可用）本来就该由降级处理，
#: 不是由无限加预算处理。
EXTRACT_STAGE_TIMEOUT_SECONDS = 24 * 60
CROSS_CHECK_STAGE_TIMEOUT_SECONDS = 45 * 60
SEGMENT_STAGE_TIMEOUT_SECONDS = 35 * 60

#: 取字阶段留给「OCR 都做完了、但结果还没落到可交付状态」的尾段时间。
#:
#: 这段不是零：2026-11-20 那次 progress 已经到 100（11:59），到 12:00:43 被杀还有
#: ≥100s 没跑完（逐页写 OCR 缓存 + pages.json + 取字摘要 + 页面质量画像 + 推进阶段）。
#: 150s 在实测尾部上再留一半余量；预算不让 OCR 吃到这一段，否则又会“OCR 成功了、
#: 任务还是被杀”。
EXTRACT_STAGE_TAIL_RESERVE_SECONDS = 150


def extract_stage_budget(
    *,
    timeout_seconds: float = EXTRACT_STAGE_TIMEOUT_SECONDS,
    tail_reserve_seconds: float = EXTRACT_STAGE_TAIL_RESERVE_SECONDS,
    now: float | None = None,
) -> OCRStageBudget:
    """在 `extract` 阶段开始时算一个墙钟预算，供逐页 OCR 做降级决策。

    用 ``time.monotonic()`` 而不是 ``time.time()``：预算关心的是“过了多久”，
    NTP 校时 / 时区变化都不应该让正在跑的任务凭空多出或少掉几分钟。

    Args:
        timeout_seconds: 本任务的 django-q 硬阀值。**必须与 `submit_extract_stage`
            提交的值一致**：两者不同步就等于拿错的尺子量剩余时间。
        tail_reserve_seconds: 留给落盘/推进阶段的时间（见常量注释）。
        now: 注入当前 monotonic 值（单测用；生产不传）。
    """
    started = time.monotonic() if now is None else now
    return OCRStageBudget(
        started_monotonic=started,
        deadline_monotonic=started + float(timeout_seconds) - float(tail_reserve_seconds),
        total_seconds=float(timeout_seconds) - float(tail_reserve_seconds),
    )


def submit_extract_stage(job: PdfSplitJob) -> str:
    """提交第一阶段（取字）。"""
    # submit() 返回 Any（task 后端可替换）：显式 str() 收窄
    return str(
        build_task_submission_service().submit(
            TASK_EXTRACT,
            args=[str(job.id)],
            task_name=f"pdf_split_extract_{job.id}",
            timeout=EXTRACT_STAGE_TIMEOUT_SECONDS,
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
    就是跟 `extract → segment` 一样拆成独立任务，让这一段有自己完整的预算。

    预算取 `CROSS_CHECK_STAGE_TIMEOUT_SECONDS`（45 分钟）而不是集群默认的
    600s：本阶段 164 页实测 269s，但那是**云端顺利时**的数字。云服务排队、
    重传、网络抖动都会把它推过 600s——2026-11-16 那次就是 MinerU 单路阻塞到
    4347s。留 45 分钟是为了让「慢但最终成功」不被误杀，同时仍能在真死时收口。
    """
    return str(
        build_task_submission_service().submit(
            TASK_CROSS_CHECK,
            args=[str(job.id)],
            task_name=f"pdf_split_cross_check_{job.id}",
            timeout=CROSS_CHECK_STAGE_TIMEOUT_SECONDS,
        )
    )


def submit_segment_stage(job: PdfSplitJob) -> str:
    """提交分段阶段。

    独立提交是拆链的关键：前面每个阶段无论成功或失败，本阶段的预算
    都是全新的，不会被前面阶段的耗时抵掉。
    """
    return str(
        build_task_submission_service().submit(
            TASK_SEGMENT,
            args=[str(job.id)],
            task_name=f"pdf_split_segment_{job.id}",
            timeout=SEGMENT_STAGE_TIMEOUT_SECONDS,
        )
    )


def _pages_payload_path(storage: PdfSplitStorage) -> Path:
    return storage.pages_json_path


def _page_quality_payload_path(storage: PdfSplitStorage) -> Path:
    return storage.page_quality_json_path


def _extract_summary_payload_path(storage: PdfSplitStorage) -> Path:
    return storage.extract_summary_json_path


def save_extract_summary(storage: PdfSplitStorage, payload: dict[str, Any]) -> None:
    """落盘取字阶段的观测摘要。

    必须落盘的理由：``ocr_provider``（**实际生效**的平台，容灾后会与首选不同）是
    分段阶段换算 bbox 单位的唯一依据。``job.cloud_backend`` 只是用户偏好，默认
    "auto" 在 ``resolve_bbox_unit`` 里是 unknown —— 拿它当依据会让 positioned 恒空。
    """
    storage.write_json(_extract_summary_payload_path(storage), payload)


def load_extract_summary(storage: PdfSplitStorage) -> dict[str, Any]:
    """读回取字摘要；不存在或损坏返回空表（旧任务没这个产物，坐标降级为不可用）。"""
    path = _extract_summary_payload_path(storage)
    try:
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("pdf_split_extract_summary_unreadable", extra={"path": str(path)})
        return {}
    return raw if isinstance(raw, dict) else {}


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
