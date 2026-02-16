"""API endpoints."""

from __future__ import annotations

"""
案由和法院数据 API

API 层职责:
1. 接收 HTTP 请求,验证参数(通过 Schema)
2. 调用 Service 层方法
3. 返回响应

不包含:业务逻辑、权限检查、异常处理(依赖全局异常处理器)
"""

from typing import Any

from ninja import Router, Schema

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

    Returns:
        CauseCourtDataService 实例
    """
    from apps.cases.services import CauseCourtDataService  # type: ignore[attr-defined]

    return CauseCourtDataService()


@router.get("/causes-data", response=list[CauseSchema])
def get_causes(request: Any, search: str | None = None, case_type: str | None = None, limit: int | None = 50) -> Any:
    """
    获取案由列表

    Args:
        search: 搜索关键词(可选)
        case_type: 案件类型 (civil, criminal, administrative, execution, bankruptcy)(可选)
        limit: 返回结果数量限制(默认50)
    """
    service = _get_cause_court_data_service()

    if search:
        # 如果提供了搜索关键词,使用搜索功能
        return service.search_causes(query=search, case_type=case_type, limit=limit)
    else:
        # 如果没有搜索关键词,返回空列表(避免返回大量数据)
        return []


@router.get("/causes-tree", response=list[CauseTreeNodeSchema])
def get_causes_tree(request: Any, parent_id: int | None = None) -> Any:
    """
    获取案由树形数据(按层级展开)

    Args:
        parent_id: 父级案由ID,为空时返回顶级案由
    """
    service = _get_cause_court_data_service()
    return service.get_causes_by_parent(parent_id=parent_id)


@router.get("/cause/{cause_id}")
def get_cause_by_id(request: Any, cause_id: int) -> Any:
    """
    根据ID获取案由信息(用于生成昵称)

    Args:
        cause_id: 案由ID
    """
    service = _get_cause_court_data_service()
    result = service.get_cause_by_id(cause_id)
    if result is None:
        from ninja import HttpError  # type: ignore[attr-defined]

        raise HttpError(404, "案由不存在") from None
    return result


@router.get("/courts-data", response=list[CourtSchema])
def get_courts(request: Any, search: str | None = None, limit: int | None = 50) -> Any:
    """
    获取法院列表

    Args:
        search: 搜索关键词(可选)
        limit: 返回结果数量限制(默认50)
    """
    service = _get_cause_court_data_service()

    if search:
        # 如果提供了搜索关键词,使用搜索功能
        return service.search_courts(query=search, limit=limit)
    else:
        # 如果没有搜索关键词,返回空列表(避免返回所有法院数据)
        return []
