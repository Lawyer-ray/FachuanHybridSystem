"""
律师 API
只负责请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from typing import Any, cast

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import File, Router
from ninja.files import UploadedFile

from apps.core.security.auth import JWTOrSessionAuth
from apps.organization.api.utils_api import get_request_user
from apps.organization.dtos import LawyerCreateDTO, LawyerListFiltersDTO, LawyerUpdateDTO
from apps.organization.schemas import (
    LawyerApproveIn,
    LawyerApproveOut,
    LawyerCreateIn,
    LawyerOut,
    LawyerSlimOut,
    LawyerUpdateIn,
)
from apps.organization.services import LawyerApprovalService, LawyerService

router = Router(auth=JWTOrSessionAuth())


def _get_lawyer_service() -> LawyerService:
    """工厂函数：获取律师服务实例"""
    return LawyerService()


_lawyer_service = _get_lawyer_service()


@router.get("/lawyers", response=list[LawyerOut] | list[LawyerSlimOut])
async def list_lawyers(  # pragma: no cover
    request: HttpRequest,
    search: str | None = None,
    law_firm_id: int | None = None,
    slim: bool = False,
) -> Any:
    """律师列表。

    - slim=true 只回 id/real_name/phone/license_no/law_firm_name——列表页做
      「lawyer_id → 人名电话执业证」映射就够，不需要文件签 URL 与律所嵌套对象。
      全量 500 人时省掉 1000 次存储签名 + 嵌套 DTO 构建。
    """
    # 显式放开 service 层默认 page_size=20 的截断：前端办案页需要全量律师
    # （量级=律所人数，几十~几百），此前只拿前 20 条导致执业证号/律所补不全
    filters = LawyerListFiltersDTO(search=search, law_firm_id=law_firm_id)
    rows = await sync_to_async(
        lambda: list(_lawyer_service.list_lawyers(filters=filters, user=get_request_user(request), page_size=500))
    )()
    if not slim:
        return rows
    return [LawyerSlimOut.from_orm(r) for r in rows]


# ============================================================
# 注册审批
#
# 必须声明在 ``/lawyers/{lawyer_id}`` 之前：Ninja 按声明顺序匹配，
# 让 ``pending`` 先被字面路径吃掉，避免落到整型路径参数上。
# ============================================================


@router.get("/lawyers/pending", response=list[LawyerOut])
async def list_pending_lawyers(request: HttpRequest) -> Any:  # pragma: no cover
    """待审批注册列表（仅管理员）。"""
    service = LawyerApprovalService()

    # 序列化必须在 sync_to_async 内完成：LawyerOut 会解析 law_firm 外键，
    # 在异步上下文里裸调 from_orm 会触发 SynchronousOnlyOperation（500）。
    def _do() -> Any:
        return [LawyerOut.from_orm(row) for row in service.list_pending(get_request_user(request))]

    return await sync_to_async(_do)()


@router.post("/lawyers/{lawyer_id}/approve", response=LawyerApproveOut)
async def approve_lawyer(  # pragma: no cover
    request: HttpRequest, lawyer_id: int, payload: LawyerApproveIn | None = None
) -> LawyerApproveOut:
    """通过注册审批：激活账号，并归入审批人所在律所（仅管理员）。"""
    service = LawyerApprovalService()
    data = payload or LawyerApproveIn()

    def _do() -> Any:
        lawyer = service.approve(
            lawyer_id,
            get_request_user(request),
            law_firm_id=data.law_firm_id,
            lawyer_team_ids=data.lawyer_team_ids,
            biz_team_ids=data.biz_team_ids,
        )
        # 同上：序列化跟着进线程，否则激活已提交但响应 500（数据变了、客户端以为失败）
        return LawyerApproveOut(success=True, user=LawyerOut.from_orm(lawyer), message="已通过审批，账号可登录")

    return cast(LawyerApproveOut, await sync_to_async(_do)())


@router.post("/lawyers/{lawyer_id}/reject", response=LawyerApproveOut)
async def reject_lawyer(request: HttpRequest, lawyer_id: int) -> LawyerApproveOut:  # pragma: no cover
    """拒绝注册申请：删除待审批账号（仅管理员）。"""
    service = LawyerApprovalService()
    await sync_to_async(service.reject)(lawyer_id, get_request_user(request))
    return LawyerApproveOut(success=True, message="已拒绝该注册申请")


@router.get("/lawyers/{lawyer_id}", response=LawyerOut)
async def get_lawyer(request: HttpRequest, lawyer_id: int) -> LawyerOut:  # pragma: no cover
    return await sync_to_async(_lawyer_service.get_lawyer)(lawyer_id, get_request_user(request))  # type: ignore[return-value]


@router.post("/lawyers", response=LawyerOut)
async def create_lawyer(  # pragma: no cover
    request: HttpRequest,
    payload: LawyerCreateIn,
    license_pdf: UploadedFile | None = File(None),
    avatar: UploadedFile | None = File(None),
) -> LawyerOut:
    dto = LawyerCreateDTO(
        username=payload.username,
        password=payload.password,
        real_name=payload.real_name,
        phone=payload.phone,
        license_no=payload.license_no,
        id_card=payload.id_card,
        law_firm_id=payload.law_firm_id,
        is_admin=payload.is_admin,
        lawyer_team_ids=payload.lawyer_team_ids,
        biz_team_ids=payload.biz_team_ids,
    )
    return await sync_to_async(_lawyer_service.create_lawyer)(  # type: ignore[return-value]
        data=dto, user=get_request_user(request), license_pdf=license_pdf, avatar=avatar
    )


@router.put("/lawyers/{lawyer_id}", response=LawyerOut)
async def update_lawyer(  # pragma: no cover
    request: HttpRequest,
    lawyer_id: int,
    payload: LawyerUpdateIn,
    license_pdf: UploadedFile | None = File(None),
    avatar: UploadedFile | None = File(None),
) -> LawyerOut:
    dto = LawyerUpdateDTO(
        real_name=payload.real_name,
        phone=payload.phone,
        license_no=payload.license_no,
        id_card=payload.id_card,
        law_firm_id=payload.law_firm_id,
        is_admin=payload.is_admin,
        password=payload.password,
        lawyer_team_ids=payload.lawyer_team_ids,
        biz_team_ids=payload.biz_team_ids,
    )
    return await sync_to_async(_lawyer_service.update_lawyer)(  # type: ignore[return-value]
        lawyer_id=lawyer_id,
        data=dto,
        user=get_request_user(request),
        license_pdf=license_pdf,
        avatar=avatar,
    )


@router.delete("/lawyers/{lawyer_id}")
async def delete_lawyer(request: HttpRequest, lawyer_id: int) -> dict[str, bool]:  # pragma: no cover
    await sync_to_async(_lawyer_service.delete_lawyer)(lawyer_id, get_request_user(request))
    return {"success": True}
