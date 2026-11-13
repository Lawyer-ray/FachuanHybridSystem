"""巡检并自动拯救卡死的 PDF 拆分任务。

用法：

    # 只看不救（上线首日建议先这样跑一次，确认判据不会误伤好任务）
    python manage.py sweep_stale_pdf_splits --dry-run

    # 实际拯救
    python manage.py sweep_stale_pdf_splits

    # 放宽/收紧判死阈值（秒）
    python manage.py sweep_stale_pdf_splits --stale-seconds 900

建议挂成 cron（每 5 分钟）或与 qcluster 同生命周期启动；也可以由运维手动触发。
判活与收尾逻辑全在 `services/job_recovery.py`，本命令只做 IO 与展示。
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.pdf_splitting.services import job_recovery


class Command(BaseCommand):
    help = "找出心跳已停的 processing 任务，按规则重排/转待复核/标记失败"

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

    def handle(self, *args: Any, **options: Any) -> None:
        stale_seconds: int = options["stale_seconds"]
        limit: int = options["limit"]

        if options["dry_run"]:
            stale = job_recovery.find_stale_jobs(stale_seconds=stale_seconds)
            if not stale:
                self.stdout.write(self.style.SUCCESS("没有卡死的任务"))
                return
            self.stdout.write(self.style.WARNING(f"发现 {len(stale)} 个卡死任务（未处理）:"))
            for job in stale:
                last = job_recovery._last_liveness(job)
                self.stdout.write(
                    f"  {job.id}  页 {job.processed_pages}/{job.total_pages}  "
                    f"最后存活 {last}  已重排 {job.recovery_attempts} 次"
                )
            return

        result = job_recovery.sweep_stale_jobs(stale_seconds=stale_seconds, limit=limit)
        if not result["stale_found"]:
            self.stdout.write(self.style.SUCCESS("没有卡死的任务"))
            return

        self.stdout.write(self.style.WARNING(f"发现 {result['stale_found']} 个卡死任务，处理结果:"))
        for item in result["actions"]:
            self.stdout.write(f"  {item['job_id']}  →  {item['action']}")
        errored = [item for item in result["actions"] if item["action"] == "error"]
        if errored:
            self.stderr.write(self.style.ERROR(f"{len(errored)} 个任务拯救时出错，详见日志"))
