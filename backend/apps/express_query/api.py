"""快递查询 API"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

from apps.express_query.models import ExpressQueryTask

router = Router()

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
def list_tasks(request: HttpRequest) -> Any:
    """获取快递查询任务列表"""
    return ExpressQueryTask.objects.all().order_by("-created_at")[:200]
