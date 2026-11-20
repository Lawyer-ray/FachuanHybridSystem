"""把案件会话所属项目（``AgentSession.contract_id``）回填上。

## 为什么需要这条命令

``contract_id`` 是「这条会话属于哪个项目」的锚点：项目页按它拉会话、侧栏按它
分组、跨会话共享上下文（项目笔记）按它挂载。而前端在案件页只发 ``case_id``
（``copilot/scope-types.ts`` 的 ``CopilotScope`` 是 case|contract 二选一），
所以历史上案件会话的 ``contract_id`` 恒为 NULL。

建会话时的推导（``services/session_service.resolve_contract_id``）只对**新**会话
生效，存量走本命令一次性补齐。

## 幂等与「不猜」

- 只处理 ``contract_id`` 仍为空的行，重复执行安全；
- 两种补不了的情况分别计数、不写库：
  1. 案件本身没关联项目（``Case.contract`` 允许为空，历史/导入案件）；
  2. 案件已不存在（脏 ``case_id``）。
  ——宁可在项目维度缺一条，也不猜一个错的项目挂上去。

用法::

    python manage.py backfill_session_contract --dry-run   # 只统计
    python manage.py backfill_session_contract             # 写库
"""

from __future__ import annotations

from typing import Any

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.db.models import Count, QuerySet

from apps.agent.models import AgentSession


class Command(BaseCommand):
    help = "为案件会话回填所属项目（AgentSession.contract_id）"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
        parser.add_argument("--batch-size", type=int, default=500, help="每批 bulk_update 的行数")

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = bool(options["dry_run"])
        batch_size: int = max(1, int(options["batch_size"]))

        pending: QuerySet[AgentSession] = AgentSession.objects.filter(case_id__isnull=False, contract_id__isnull=True)
        total = pending.count()
        if not total:
            self.stdout.write(self.style.SUCCESS("没有需要回填的会话"))
            return

        case_model = django_apps.get_model("cases", "Case")
        # 过滤 None：查询条件已限定 ``case_id__isnull=False``，但 ``values_list`` 的
        # 静态类型仍是 ``int | None``——拿它去 ``pk__in`` 会被 mypy 拦。
        case_ids: set[int] = {cid for cid in pending.values_list("case_id", flat=True) if cid is not None}

        contract_of_case: dict[int, int] = dict(
            case_model.objects.filter(pk__in=case_ids, contract__isnull=False).values_list("id", "contract_id")
        )
        known_case_ids = set(case_model.objects.filter(pk__in=case_ids).values_list("id", flat=True))

        by_origin = {row["origin"]: row["n"] for row in pending.values("origin").annotate(n=Count("id"))}

        filled = 0
        case_without_project = 0
        missing_case = 0
        buffer: list[AgentSession] = []

        for session in pending.only("id", "case_id", "contract_id").iterator(chunk_size=batch_size):
            # 同上：查询已排除空 case_id，这里把类型收窄成 ``int`` 再查表
            target = contract_of_case.get(session.case_id) if session.case_id is not None else None
            if target is None:
                if session.case_id in known_case_ids:
                    case_without_project += 1
                else:
                    missing_case += 1
                continue
            session.contract_id = target
            buffer.append(session)
            if len(buffer) >= batch_size:
                filled += self._flush(buffer, dry_run=dry_run, batch_size=batch_size)
                buffer.clear()
        filled += self._flush(buffer, dry_run=dry_run, batch_size=batch_size)

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}候选 {total} 条（按入口：{by_origin}）；"
            f"可回填 {filled} 条；案件未关联项目 {case_without_project} 条；案件已不存在 {missing_case} 条"
        )
        if not dry_run and filled:
            self.stdout.write(self.style.SUCCESS(f"已回填 {filled} 条会话的 contract_id"))
        if case_without_project or missing_case:
            self.stdout.write(self.style.WARNING("以上「补不了」的行保持 contract_id 为空，项目维度上仍是无主的"))

    def _flush(self, buffer: list[AgentSession], *, dry_run: bool, batch_size: int) -> int:
        """落一批（dry-run 只数不写）。"""
        if not buffer:
            return 0
        if not dry_run:
            AgentSession.objects.bulk_update(buffer, ["contract_id"], batch_size=batch_size)
        return len(buffer)
