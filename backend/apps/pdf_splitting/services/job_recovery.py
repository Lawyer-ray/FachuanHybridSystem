"""PDF 拆解任务的「卡死自救」机制。

## 为什么需要它

`qcluster` 在开发环境被 `watchfiles` 包裹（见 Makefile `qcluster-dev`）：只要有任何
`apps/ apiSystem/ plugins/` 下的 .py 变化，watchfiles 就 kill 掉整个 qcluster 子进程
并重启。正在跑的拆分任务随即消失，**但数据库里的 job 仍停在 `processing`**——
没有异常、没有日志、没有 error_message。曾有一次 164 页的真实卷宗任务卡在
135/164 二十余分钟，前端只是不停地转圈，律师完全无从判断。

生产环境同样会死：worker 被 OOM killer 杀掉、部署重启、机器断电。区别只是频率。

## 判活口径

| 字段 | 谁写 | 用途 |
|:--|:--|:--|
| `heartbeat_at` | worker 每处理一批页 | **唯一可信的存活信号** |
| `updated_at` | 任何 `save()`；进度回写现在显式写 | 兜底（老数据无 heartbeat） |
| `started_at` | 创建任务时写一次 | 判「从未开始」 |

判据：`processing` 状态下，`now - max(heartbeat_at, updated_at) > STALE_SECONDS`，
即视为 worker 已死。阈值必须显著大于进度回写间隔，否则会把慢任务误判为死任务。

## 三种收尾动作（按顺序尝试）

1. **可恢复 → 重排队**：Worker 死了但活没干完（`processed_pages == 0`，说明还没
   开始真正的工作），直接重新 `submit`。这条路最理想：律师什么都不用做。
2. **已有部分成果 → 转待复核**：`processed_pages > 0` 说明识别结果已落 `segments`，
   只是没走完收尾。**不重跑**（164 页重跑一次很贵），直接标 `review_required`，
   让律师基于已有分段继续——分段少几段也比从零开始好。
3. **反复失败 → 标记失败**：`recovery_attempts >= MAX_RECOVERY_ATTEMPTS`，
   停止自动重排（防死循环打满队列），明确写 `error_message` 让人介入。

## 为什么不做「立刻重排」

如果 worker 是被某个坏输入打死的，立刻重排会等剂量地再死一次，还连累队列里
其他任务。所以重排次数有上限，且失败原因如实落库。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.core.dependencies.core import build_task_submission_service
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus

logger = logging.getLogger("apps.pdf_splitting")

#: 超过这个时长没有心跳，判定 worker 已死。
#:
#: 为什么从 600 放宽到 1800：在 164 页真实卷宗上，交叉比对（双引擎整本再解析
#: 一遍）+ LLM 分段合计会超过 10 分钟，600s 会把**正常在跑**的任务判死并重排，
#: 而重排等价于把整份卷宗的云端费用再付一次（实测 7da5d020 就卡在这条线上）。
#:
#: 既然心跳现在由后端主动刷新（`services/heartbeat.periodic_heartbeat` 每 15s，
#: 取字阶段每页刷），1800s 只是兜底而不是常态判据：真活着的任务远不会静默半小时，
#: 真死了的晚一点发现也只是多等一会儿，代价远小于误杀重排。
STALE_SECONDS = 1800

#: 同一个任务最多自动重排几次。超过就停下报错，避免坏输入无限循环。
MAX_RECOVERY_ATTEMPTS = 2

#: 一次巡检最多处理多少个任务，防止首轮上线时一口气重排打满队列。
MAX_RECOVERY_PER_RUN = 5


def _last_liveness(job: PdfSplitJob) -> Any:
    """任务最后的存活信号：心跳优先，退回 updated_at，再退回 started_at/created_at。"""
    candidates = [job.heartbeat_at, job.updated_at, job.started_at, job.created_at]
    return max((item for item in candidates if item is not None), default=None)


def find_stale_jobs(*, now: Any = None, stale_seconds: int = STALE_SECONDS) -> list[PdfSplitJob]:
    """列出「状态是 processing 但心跳已停」的任务。

    只查 `processing`：`pending` 是还没被 worker 捡起来（正常，尤其队列忙时），
    `review_required`/`completed`/`failed`/`cancelled` 都是终态或待人工，均不该动。
    """
    now = now or timezone.now()
    threshold = now - timedelta(seconds=stale_seconds)

    # 先按 updated_at 粗筛（有索引可用），再在 Python 里按真实存活信号精筛。
    # 之所以不把 heartbeat 写进 SQL：老数据 heartbeat_at 全为 NULL，SQL 里
    # 的 COALESCE 会让条件变得又长又难读，而这里候选集本来就只有几十条。
    candidates = PdfSplitJob.objects.filter(
        status=PdfSplitJobStatus.PROCESSING,
    ).filter(Q(updated_at__lt=threshold) | Q(updated_at__gte=threshold))

    stale: list[PdfSplitJob] = []
    for job in candidates:
        last = _last_liveness(job)
        if last is not None and last < threshold:
            stale.append(job)
    return stale


def _resume_task_for(job: PdfSplitJob) -> tuple[str, str, int | None]:
    """按任务**当前阶段**决定从哪个任务入口续跑。

    返回 ``(任务路径, 任务名称, 该阶段的临时预算秒数)``。预算为 None 时表示用
    Django-Q 集群默认值（只有旧全量路径会落到这里）。

    ## 为什么不能一律用 `execute_pdf_split_job`

    那条是**旧全量路径**（`analyze_job` → `pipeline.analyze_pdf`），里面**不包含**
    `cross_check_stage`。于是双引擎任务一旦被重排，就会静默退化成单引擎——
    比对结果凭空消失，而律师那边看不出任何异常（任务照样跑完、照样出分段）。

    更糟的是旧路径本身就是为了绕开 600s 硬超时才被拆掉的：它把取字 + 分段
    挤在一次调用里，164 页实测跑到 499s 被杀。重排走回去等于等剂量地再死一次。

    ## 各阶段的正确续跑点

    | 任务当前阶段 | 续跑入口 | 理由 |
    |---|---|---|
    | `cross_check` | `run_cross_check_stage` | 取字产物已在 pages.json，只差比对 |
    | `segment` | `run_segment_stage` | 取字 + 比对都已落盘，只差分段 |
    | `extract` / 其它 | `run_extract_stage` | 从头取字（两阶段链路的正常起点） |

    非内容分析任务（手工拆分 / 按页拆分）仍走旧的全量入口——它们本来就是
    单一任务，没有阶段可复原。

    ## 为什么预算也要跟进来

    重排出来的任务如果不同时带上该阶段的 timeout，就会退回集群默认的 600s——
    等于「看门狗救回来的任务，比它原先那次更容易死」。重排的意义是让任务活着
    跑完，不是在 600s 处再杀它一次。
    """
    from apps.pdf_splitting.models import PdfSplitMode, PdfSplitStage
    from apps.pdf_splitting.services.split.two_stage import (
        CROSS_CHECK_STAGE_TIMEOUT_SECONDS,
        EXTRACT_STAGE_TIMEOUT_SECONDS,
        SEGMENT_STAGE_TIMEOUT_SECONDS,
        TASK_CROSS_CHECK,
        TASK_EXTRACT,
        TASK_SEGMENT,
    )

    if job.split_mode != PdfSplitMode.CONTENT_ANALYSIS:
        return "apps.pdf_splitting.tasks.execute_pdf_split_job", f"pdf_split_{job.id}", None

    stage = getattr(job, "stage", PdfSplitStage.EXTRACT)
    if stage == PdfSplitStage.CROSS_CHECK:
        return TASK_CROSS_CHECK, f"pdf_split_cross_check_{job.id}", CROSS_CHECK_STAGE_TIMEOUT_SECONDS
    if stage == PdfSplitStage.SEGMENT:
        return TASK_SEGMENT, f"pdf_split_segment_{job.id}", SEGMENT_STAGE_TIMEOUT_SECONDS
    return TASK_EXTRACT, f"pdf_split_extract_{job.id}", EXTRACT_STAGE_TIMEOUT_SECONDS


def _requeue(job: PdfSplitJob) -> str:
    """重新提交任务。返回动作描述。

    入口按当前阶段选（见 `_resume_task_for`）：双引擎任务重排后**仍是双引擎**，
    不会静默退化成旧全量路径；预算也一并带上，不会退回集群默认值再被杀一次。
    """
    task_path, task_name, timeout = _resume_task_for(job)
    task_id = build_task_submission_service().submit(
        task_path,
        args=[str(job.id)],
        task_name=task_name,
        timeout=timeout,
    )
    now = timezone.now()
    PdfSplitJob.objects.filter(id=job.id).update(
        status=PdfSplitJobStatus.PENDING,
        task_id=str(task_id),
        started_at=now,
        heartbeat_at=None,
        updated_at=now,
        error_message="",
        recovery_attempts=job.recovery_attempts + 1,
    )
    return f"requeued(attempt={job.recovery_attempts + 1}, path={task_path.rsplit('.', 1)[-1]}, task_id={task_id})"


def _salvage_as_review(job: PdfSplitJob) -> str:
    """把已产出的部分成果转成待复核，不重跑。

    这是本模块最重要的一条兜底：164 页扫描件的识别成本很高，重跑一次既贵又可能
    再次死在同一个地方。只要 `segments` 里已经有东西，就比从零开始有价值。
    """
    now = timezone.now()
    segment_count = job.segments.count()
    PdfSplitJob.objects.filter(id=job.id).update(
        status=PdfSplitJobStatus.REVIEW_REQUIRED,
        finished_at=now,
        updated_at=now,
        error_message=(
            f"识别进程中途退出，已按已产出的 {segment_count} 个分段转入待复核。分段可能不完整，请核对后使用或重试。"
        ),
    )
    return f"salvaged_as_review(segments={segment_count})"


def _mark_failed_after_retries(job: PdfSplitJob) -> str:
    now = timezone.now()
    PdfSplitJob.objects.filter(id=job.id).update(
        status=PdfSplitJobStatus.FAILED,
        finished_at=now,
        updated_at=now,
        error_message=(
            f"识别进程反复中断（已自动重排 {job.recovery_attempts} 次），已停止自动恢复。"
            "请检查后端 worker 日志，或缩小材料页数后重试。"
        ),
    )
    return "marked_failed_after_retries"


def recover_job(job: PdfSplitJob) -> str:
    """对单个卡死任务执行收尾。返回实际动作名（用于日志与断言）。

    ⚠️ 判「能不能救」看的是 `segments` 有没有落库，**不是** `processed_pages`。

    这两者不是一回事：分段是全部页解析完之后才一次性 `bulk_create` 的
    （见 `split/service.py::_persist_page_split`），所以一个任务完全可能显示
    「已处理 135/164 页」而 `segments` 仍然是 0。此时把它转成「待复核」只会
    给律师一个空列表——看似救回来了，实际什么都没留下。

    真实的判据只有一条：**有没有能交给律师看的分段**。
    """
    if job.recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
        return _mark_failed_after_retries(job)

    has_usable_segments = job.segments.exists()
    if has_usable_segments:
        return _salvage_as_review(job)
    return _requeue(job)


def sweep_stale_jobs(
    *,
    now: Any = None,
    stale_seconds: int = STALE_SECONDS,
    limit: int = MAX_RECOVERY_PER_RUN,
) -> dict[str, Any]:
    """巡检并拯救卡死任务。返回汇总，供管理命令与测试断言。

    Args:
        now: 测试注入的当前时刻；缺省用 timezone.now()。
        stale_seconds: 判死阈值。管理命令的 `--stale-seconds` 走这里——
            原先本函数没有这个参数，命令传了会在运行时抛 TypeError，
            也就是说「可调阈值」这个能力其实一直没生效。
        limit: 单次最多处理几个（防首轮一口气重排打满队列）。

    设计为**幂等**：重复调用不会重复重排（重排后 status 变 PENDING，
    不再被 `find_stale_jobs` 选中）。
    """
    stale = find_stale_jobs(now=now, stale_seconds=stale_seconds)[:limit]
    actions: list[dict[str, Any]] = []

    for job in stale:
        try:
            action = recover_job(job)
            logger.warning(
                "pdf_split_job_recovered",
                extra={
                    "job_id": str(job.id),
                    "action": action,
                    "processed_pages": job.processed_pages,
                    "total_pages": job.total_pages,
                    "last_liveness": str(_last_liveness(job)),
                },
            )
            actions.append({"job_id": str(job.id), "action": action})
        except Exception as exc:  # 单个任务失败不能影响其他任务的拯救
            logger.exception("pdf_split_job_recovery_failed", extra={"job_id": str(job.id)})
            actions.append({"job_id": str(job.id), "action": "error", "error": str(exc)})

    return {"stale_found": len(stale), "actions": actions}
