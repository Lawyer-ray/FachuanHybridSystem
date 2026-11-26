"""审查后台任务入口（django-q）。

**为什么审查必须异步**：一次审查要几十秒（全文 + 模型）。同步 HTTP 会让浏览器
转圈到超时，而律师需要的是「点一下就开始，右栏出现『审查中』，跑完自动出清单」。
"""

from __future__ import annotations

import logging

from .models import ReviewRun, RunStatus

logger = logging.getLogger(__name__)


def execute_review_run(run_id: int) -> dict[str, object]:
    """跑一轮审查。幂等：已完成的轮次不会重跑。"""
    from .services import review_pipeline

    run = ReviewRun.objects.filter(id=run_id).first()
    if run is None:
        logger.warning("审查任务找不到轮次: %s", run_id)
        return {"ok": False, "reason": "run_not_found"}
    if run.status in (RunStatus.DONE, RunStatus.SUPERSEDED):
        return {"ok": True, "skipped": True, "run_id": run_id}

    review_pipeline.execute_run(run)
    run.refresh_from_db()
    return {"ok": run.status == RunStatus.DONE, "run_id": run_id, "status": run.status}


__all__ = ["execute_review_run"]
