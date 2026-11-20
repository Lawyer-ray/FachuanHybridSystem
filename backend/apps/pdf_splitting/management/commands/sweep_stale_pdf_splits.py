"""巡检并自动拯救卡死的 PDF 拆分任务。

用法：

    # 只看不救（上线首日建议先这样跑一次，确认判据不会误伤好任务）
    python manage.py sweep_stale_pdf_splits --dry-run

    # 实际拯救
    python manage.py sweep_stale_pdf_splits

    # 放宽/收紧「心跳」判死阈值（秒）
    python manage.py sweep_stale_pdf_splits --stale-seconds 900

    # 只看心跳，不套用「阶段硬超时」第二判据（万一某阶段预算临时改大过，用它避误杀）
    python manage.py sweep_stale_pdf_splits --no-stage-budget

建议挂成 cron（每 5 分钟）或与 qcluster 同生命周期启动；也可以由运维手动触发。
判活与收尾逻辑全在 `services/job_recovery.py`，本命令只做 IO 与展示。

## 两条判死依据（`--dry-run` 会把依据一起打出来）

1. 心跳：静默超过 `--stale-seconds`（默认 1800s）。
2. 阶段硬超时：静默超过「该阶段提交给 django-q 的 timeout + 余量」（默认 +120s）。
   django-q 在该 timeout 处一定会销毁 worker，所以这一条是**可证明已死**，
   不必再等满 30 分钟（2026-11-20 事故：`extract` 1200s 预算烧完被杀，
   旧判据要等到 12:29 才重排）。
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.pdf_splitting.services import job_recovery


class Command(BaseCommand):
    help = "找出可证明已死的 processing 任务（心跳超时 / 阶段硬超时），按规则重排/转待复核/标记失败"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只列出卡死任务，不执行任何收尾动作",
        )
        parser.add_argument(
            "--stale-seconds",
            type=int,
            default=job_recovery.STALE_SECONDS,
            help=f"超过多少秒没心跳判定为死（默认 {job_recovery.STALE_SECONDS}）",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=job_recovery.MAX_RECOVERY_PER_RUN,
            help=f"本次最多处理几个任务（默认 {job_recovery.MAX_RECOVERY_PER_RUN}）",
        )
        parser.add_argument(
            "--no-stage-budget",
            action="store_true",
            help="关闭「阶段硬超时 + 余量」第二判据，只按 --stale-seconds 判定",
        )
        parser.add_argument(
            "--stage-grace-seconds",
            type=int,
            default=job_recovery.STAGE_DEAD_GRACE_SECONDS,
            help=f"阶段硬超时的余量秒数（默认 {job_recovery.STAGE_DEAD_GRACE_SECONDS}）",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        stale_seconds: int = options["stale_seconds"]
        limit: int = options["limit"]
        grace_seconds: int = options["stage_grace_seconds"]
        # 显式空表 = 关闭第二判据；None = 用 job_recovery 里登记的阶段预算表
        stage_timeouts: dict[str, int] | None = {} if options["no_stage_budget"] else None

        if options["dry_run"]:
            stale = job_recovery.find_stale_jobs(
                stale_seconds=stale_seconds,
                stage_timeouts=stage_timeouts,
                grace_seconds=grace_seconds,
            )
            if not stale:
                self.stdout.write(self.style.SUCCESS("没有卡死的任务"))
                return
            self.stdout.write(self.style.WARNING(f"发现 {len(stale)} 个卡死任务（未处理）:"))
            for job in stale:
                verdict = job_recovery.explain_staleness(
                    job,
                    stale_seconds=stale_seconds,
                    stage_timeouts=stage_timeouts,
                    grace_seconds=grace_seconds,
                )
                self.stdout.write(f"  {job.id}  已重排 {job.recovery_attempts} 次  {verdict.describe()}")
            return

        result = job_recovery.sweep_stale_jobs(
            stale_seconds=stale_seconds,
            limit=limit,
            stage_timeouts=stage_timeouts,
            grace_seconds=grace_seconds,
        )
        # sweep_stale_jobs 返回 dict[str, Any]：显式收窄供 mypy 判定
        stale_found = int(result.get("stale_found") or 0)
        actions: list[dict[str, Any]] = list(result.get("actions") or [])
        if not stale_found:
            self.stdout.write(self.style.SUCCESS("没有卡死的任务"))
            return

        self.stdout.write(self.style.WARNING(f"发现 {result['stale_found']} 个卡死任务，处理结果:"))
        for item in result["actions"]:
            reason = item.get("reason") or ""
            self.stdout.write(f"  {item['job_id']}  →  {item['action']}  ({reason})")
        errored = [item for item in actions if item["action"] == "error"]
        if errored:
            self.stderr.write(self.style.ERROR(f"{len(errored)} 个任务拯救时出错，详见日志"))
