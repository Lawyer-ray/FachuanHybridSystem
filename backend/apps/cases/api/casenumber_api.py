"""
案件案号 API
符合四层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from typing import Any, cast

from ninja import Router

from ..schemas import CaseNumberIn, CaseNumberOut, CaseNumberUpdate

router = Router()


def _get_case_number_service() -> Any:
    """工厂函数：创建 CaseNumberService 实例"""
    from ..services.case_number_service import CaseNumberService

    return CaseNumberService()


@router.get("/case-numbers", response=list[CaseNumberOut])
def list_case_numbers(request: Any, case_id: int | None = None) -> list[CaseNumberOut]:
    """获取案号列表"""
    service = _get_case_number_service()
    user = getattr(request, "user", None)
    return cast(list[CaseNumberOut], service.list_numbers(case_id=case_id, user=user))


@router.get("/case-numbers/{number_id}", response=CaseNumberOut)
def get_case_number(request: Any, number_id: int) -> CaseNumberOut:
    """获取单个案号"""
    service = _get_case_number_service()
    user = getattr(request, "user", None)
    return cast(CaseNumberOut, service.get_number(number_id=number_id, user=user))


@router.post("/case-numbers", response=CaseNumberOut)
def create_case_number(request: Any, payload: CaseNumberIn) -> CaseNumberOut:
    """创建案号"""
    service = _get_case_number_service()
    user = getattr(request, "user", None)
    return cast(
        CaseNumberOut,
        service.create_number(case_id=payload.case_id, number=payload.number, remarks=payload.remarks, user=user),
    )


@router.put("/case-numbers/{number_id}", response=CaseNumberOut)
def update_case_number(request: Any, number_id: int, payload: CaseNumberUpdate) -> CaseNumberOut:
    """更新案号"""
    service = _get_case_number_service()
    user = getattr(request, "user", None)
    data = payload.dict(exclude_unset=True)
    return cast(CaseNumberOut, service.update_number(number_id=number_id, data=data, user=user))


@router.delete("/case-numbers/{number_id}")
def delete_case_number(request: Any, number_id: int) -> Any:
    """删除案号"""
    service = _get_case_number_service()
    user = getattr(request, "user", None)
    return service.delete_number(number_id=number_id, user=user)
