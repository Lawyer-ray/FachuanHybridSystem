"""快递查询 API"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth
from apps.express_query.models import ExpressQueryTask

router = Router(auth=JWTOrSessionAuth())


class ExpressQueryTaskOut(Schema):
    id: int
    title: str
    status: str
    carrier_type: str
    tracking_number: str
    result_pdf: str | None = None
    created_at: Any
    updated_at: Any


@router.get("/tasks", response=list[ExpressQueryTaskOut])
def list_tasks(request: HttpRequest) -> Any:  # pragma: no cover
    """获取快递查询任务列表（管理员/超管全量，其余仅返回本人创建的任务）"""
    user: Any = request.auth  # type: ignore[attr-defined]
    # 2026Q4 审计收紧：is_staff 仅是 Django admin 准入标志，不再视为系统管理员
    if not (getattr(user, "is_superuser", False) or getattr(user, "is_admin", False)):
        return ExpressQueryTask.objects.filter(created_by=user).order_by("-created_at")[:200]
    return ExpressQueryTask.objects.all().order_by("-created_at")[:200]
