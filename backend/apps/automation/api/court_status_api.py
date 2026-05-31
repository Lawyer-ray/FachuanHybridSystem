"""法院自动化插件状态 API"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import Router

router = Router()

@router.get("/status")
def get_court_status(request: HttpRequest) -> Any:
    """查询法院自动化插件可用状态。"""
    try:
        from plugins import has_court_automation_plugin

        available = has_court_automation_plugin()
    except ImportError:
        available = False

    return {"available": available}
