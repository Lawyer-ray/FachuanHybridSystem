"""
案由和法院数据 API

API 层职责:
1. 接收 HTTP 请求,验证参数(通过 Schema)
2. 调用 Service 层方法
3. 返回响应

不包含:业务逻辑、权限检查、异常处理(依赖全局异常处理器)
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from ninja import Router, Schema

from apps.core.exceptions import NotFoundError

router = Router()


class CauseSchema(Schema):
    """案由数据 Schema"""

    id: str
    name: str
    code: str | None = None
    raw_name: str | None = None


class CauseTreeNodeSchema(Schema):
    """案由树节点 Schema"""

    id: int
    code: str
    name: str
    case_type: str
    level: int
    has_children: bool
    full_path: str


class CourtSchema(Schema):
    """法院数据 Schema"""

    id: str
    name: str


def _get_cause_court_data_service() -> Any:
    """
    创建 CauseCourtDataService 实例

        CauseCourtDataService 实例
    """
    from apps.cases.services import CauseCourtDataService

    return CauseCourtDataService()


@router.get("/causes-data", response=list[CauseSchema])
def get_causes(
    request: HttpRequest, search: str | None = None, case_type: str | None = None, limit: int | None = 50
) -> Any:
    """
    获取案由列表

        search: 搜索关键词(可选)
        case_type: 案件类型 (civil, criminal, administrative, execution, bankruptcy)(可选)
        limit: 返回结果数量限制(默认50)
    """
    service = _get_cause_court_data_service()

    if search:
        return service.search_causes(query=search, case_type=case_type, limit=limit)
    else:
        return []


@router.get("/causes-tree", response=list[CauseTreeNodeSchema])
def get_causes_tree(request: HttpRequest, parent_id: int | None = None) -> Any:
    """
    获取案由树形数据(按层级展开)

        parent_id: 父级案由ID,为空时返回顶级案由
    """
    service = _get_cause_court_data_service()
    return service.get_causes_by_parent(parent_id=parent_id)


@router.get("/cause/{cause_id}")
def get_cause_by_id(request: HttpRequest, cause_id: int) -> Any:
    """
    根据ID获取案由信息(用于生成昵称)

        cause_id: 案由ID
    """
    service = _get_cause_court_data_service()
    result = service.get_cause_by_id(cause_id)
    if result is None:
        raise NotFoundError(message=_("案由不存在"), code="CAUSE_NOT_FOUND")
    return result


@router.get("/courts-data", response=list[CourtSchema])
def get_courts(request: HttpRequest, search: str | None = None, limit: int | None = 50) -> Any:
    """
    获取法院列表

        search: 搜索关键词(可选)
        limit: 返回结果数量限制(默认50)
    """
    service = _get_cause_court_data_service()

    if search:
        return service.search_courts(query=search, limit=limit)
    else:
        return []
