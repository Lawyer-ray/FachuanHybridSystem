"""把「生效且启用」的个人技能重新物化到 ``$FACHUAN_AGENT_HOME/skills/<user_id>/``。

## 什么时候需要它

写盘发生在 ``transaction.on_commit`` 里且失败只告警（DB 是权威，磁盘只是 pi 的
注入缓存）。所以磁盘可能落后于数据库：换了 ``FACHUAN_AGENT_HOME``、手工删过
目录、或某次落盘失败。本命令按数据库重建，是唯一的「把磁盘拉回真值」入口。

用法::

    python manage.py skills_reconcile                 # 全量重物化（不动多余目录）
    python manage.py skills_reconcile --user-id 42    # 只重建某个律师
    python manage.py skills_reconcile --prune         # 额外删掉不在启用集合里的目录
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand

from apps.agent.models import AgentSkill
from apps.agent.services.skills import store

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "按数据库重建个人技能的物化目录（--prune 清理孤儿目录）"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--user-id", type=int, default=None, help="只处理该律师（默认全量）")
        parser.add_argument("--prune", action="store_true", help="删除不在启用集合里的物化目录")

    def handle(self, *args: Any, **options: Any) -> None:
        user_id: int | None = options["user_id"]
        skills = AgentSkill.objects.filter(
            scope=AgentSkill.Scope.LAWYER,
            status=AgentSkill.Status.ACTIVE,
            enabled=True,
        )
        if user_id is not None:
            skills = skills.filter(lawyer_id=user_id)

        written = 0
        failed = 0
        keep: dict[int, set[str]] = {}
        for skill in skills.iterator():
            if skill.lawyer_id is None:  # pragma: no cover - CHECK 约束保证 lawyer 作用域必有归属
                continue
            keep.setdefault(int(skill.lawyer_id), set()).add(skill.name)
            try:
                store.write_skill(skill)
                written += 1
            except (OSError, ValueError):
                failed += 1
                logger.warning("技能物化失败: %s/%s", skill.lawyer_id, skill.name, exc_info=True)

        pruned = 0
        if options["prune"]:
            targets = {user_id} if user_id is not None else set(keep) | set(store.list_user_ids())
            for target in sorted(targets):
                pruned += len(store.prune(target, keep.get(target, set())))

        summary = f"物化 {written} 条个人技能（失败 {failed}）"
        if options["prune"]:
            summary += f"，清理 {pruned} 个多余目录"
        self.stdout.write(self.style.SUCCESS(summary))
