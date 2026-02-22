"""
律所 API
只负责请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from typing import Any

from ninja import Router

from apps.organization.schemas import LawFirmIn, LawFirmOut, LawFirmUpdateIn
from apps.organization.services import LawFirmService

router = Router()


def _get_lawfirm_service() -> LawFirmService:
    """工厂函数：创建 LawFirmService 实例"""
    from apps.organization.services import LawFirmService

    return LawFirmService()


@router.get("/lawfirms", response=list[LawFirmOut])
def list_lawfirms(request: Any) -> Any:
    """列表查询律所"""
    service = _get_lawfirm_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    lawfirms = service.list_lawfirms(user=user)  # type: ignore[arg-type]
    return list(lawfirms)


@router.get("/lawfirms/{law_firm_id}", response=LawFirmOut)
def get_lawfirm(request: Any, law_firm_id: int) -> Any:
    """获取律所详情"""
    service = _get_lawfirm_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    lawfirm = service.get_lawfirm(law_firm_id, user)  # type: ignore[arg-type]
    return lawfirm


@router.post("/lawfirms", response=LawFirmOut)
def create_lawfirm(request: Any, payload: LawFirmIn) -> Any:
    """创建律所"""
    service = _get_lawfirm_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    lawfirm = service.create_lawfirm(data=payload, user=user)  # type: ignore[arg-type]
    return lawfirm


@router.put("/lawfirms/{law_firm_id}", response=LawFirmOut)
def update_lawfirm(request: Any, law_firm_id: int, payload: LawFirmUpdateIn) -> Any:
    """更新律所"""
    service = _get_lawfirm_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    lawfirm = service.update_lawfirm(lawfirm_id=law_firm_id, data=payload, user=user)  # type: ignore[arg-type]
    return lawfirm


@router.delete("/lawfirms/{law_firm_id}")
def delete_lawfirm(request: Any, law_firm_id: int) -> dict[str, bool]:
    """删除律所"""
    service = _get_lawfirm_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    service.delete_lawfirm(law_firm_id, user)  # type: ignore[arg-type]
    return {"success": True}
