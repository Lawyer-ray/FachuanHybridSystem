"""快递查询 API"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth
from apps.express_query.services.task_service import list_visible_tasks

router = Router(auth=JWTOrSessionAuth())


class ExpressQueryTaskOut(Schema):
    id: int
    title: str
    status: str
    carrier_type: str
    tracking_number: str
    result_pdf: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@router.get("/tasks", response=list[ExpressQueryTaskOut])
def list_tasks(request: HttpRequest) -> Any:  # pragma: no cover
    """获取快递查询任务列表（管理员/超管全量，其余仅返回本人创建的任务）"""
    user: Any = request.auth  # type: ignore[attr-defined]
    return list_visible_tasks(user)
