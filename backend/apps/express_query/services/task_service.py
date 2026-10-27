"""快递查询任务查询服务。

四层架构约定：API 层不直接碰 `Model.objects`，任务列表查询下沉到此。
"""

from __future__ import annotations

from typing import Any

from apps.core.security.admin_access import is_admin_user
from apps.express_query.models import ExpressQueryTask

# 列表返回上限：快递查询任务是历史记录型数据，前端不做分页，靠上限兜住响应体积。
TASK_LIST_LIMIT = 200


def list_visible_tasks(user: Any) -> Any:
    """返回当前用户可见的快递查询任务。

    管理员/超管看全量，其余人只看自己创建的任务。
    2026Q4 审计收紧：is_staff 仅是 Django admin 准入标志，不再视为系统管理员；
    管理员判定收敛到 ``core.security.admin_access.is_admin_user``。
    """
    queryset = ExpressQueryTask.objects.all()
    if not is_admin_user(user):
        queryset = queryset.filter(created_by=user)
    return queryset.order_by("-created_at")[:TASK_LIST_LIMIT]
