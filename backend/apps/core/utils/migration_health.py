"""启动期的迁移健康检查（只在 DEBUG 下告警，绝不阻断启动）。

## 为什么需要它

`column ... does not exist` 这类事故在本仓已经发生了三次（0016 agent_kind、
0017 message.agent_kind、0023 decision_reason）。共同点：

- 迁移文件**生成了**，开发库**没跑 migrate**；
- 单测全绿（测试库自己建表）、前后端 CI 全绿；
- 只有真人点一下就炸，报错在日志深处（`ProgrammingError`）。

CI 层已有三道闸门（`scripts/check_migrations.sh`：生成 / 已应用 / 分支冲突），
但那只在有人跑 `make pr-ready` 或 `ci-local` 时才生效。这里补**最后一道**：
服务一启动就把「有 N 个未应用迁移」喊出来——开发者第一眼就能看到，
而不是等律师点按钮。

## 边界

- 只在 `DEBUG` 下跑（生产滚动部署期间本来就可能短暂落后，喊也没人管）；
- 只 **WARNING**，不 raise：启动失败比一个字段缺失更糟；
- 任何异常（库不可连、表不存在）都静默降级为 debug 日志；
- 走 ``run_startup_db_sync`` 摆渡（ASGI 部署下 ready() 在事件循环线程里，
  直接查库会抛 ``SynchronousOnlyOperation``）。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def unapplied_migrations() -> list[str]:
    """返回未应用的迁移清单（``app.name`` 形式）；查不到返回空列表。"""
    from django.core.exceptions import ImproperlyConfigured
    from django.db import DatabaseError, connection
    from django.db.migrations.executor import MigrationExecutor

    try:
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
    except (DatabaseError, ImproperlyConfigured, RuntimeError):
        # 库还没建 / 连接断了 / 迁移表不存在：都不是本检查要报的事。
        # 用具体类型而非宽捕获：本仓有宽异常捕获棘轮门禁（新文件也不许加）。
        logger.debug("迁移健康检查跳过（无法读取迁移计划）", exc_info=True)
        return []
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]


def warn_if_unapplied() -> int:
    """DEBUG 下有未应用迁移就喊一声，返回未应用条数。"""
    from django.conf import settings

    if not getattr(settings, "DEBUG", False):
        return 0
    pending = unapplied_migrations()
    if not pending:
        return 0
    shown = "、".join(pending[:5]) + ("…" if len(pending) > 5 else "")
    logger.warning(
        "⚠️ 数据库有 %d 个未应用的迁移：%s\n"
        "   症状会是「column ... does not exist」这类 500，而单测与 CI 全绿。\n"
        "   修：cd backend/apiSystem && DB_NAME=<你的库> ../.venv/bin/python manage.py migrate",
        len(pending),
        shown,
    )
    return len(pending)
