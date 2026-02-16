"""
案件日志 API 层
符合三层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""
from typing import List, Optional
from datetime import datetime
from ninja import Router

from ..schemas import CaseLogIn, CaseLogUpdate, CaseLogOut
from ..services.caselog_service import CaseLogService

router = Router()


def _get_caselog_service() -> CaseLogService:
    """工厂函数：创建 CaseLogService 实例"""
    return CaseLogService()


def _parse_reminder_time(rt: Optional[str]) -> Optional[datetime]:
    """解析提醒时间字符串"""
    if not rt:
        return None
    # 尝试 ISO 格式
    try:
        return datetime.fromisoformat(rt)
    except (ValueError, TypeError):
        pass
    # 尝试标准格式
    try:
        return datetime.strptime(rt, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


@router.get("/logs", response=List[CaseLogOut])
def list_logs(request, case_id: Optional[int] = None):
    """获取日志列表"""
    service = _get_caselog_service()
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    return service.list_logs(
        case_id=case_id,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@router.post("/logs", response=CaseLogOut)
def create_log(request, payload: CaseLogIn):
    """创建日志"""
    service = _get_caselog_service()
    user = getattr(request, "user", None)

    reminder_time = _parse_reminder_time(payload.reminder_time)

    return service.create_log(
        case_id=payload.case_id,
        content=payload.content,
        user=user,
        reminder_type=payload.reminder_type,
        reminder_time=reminder_time,
    )


@router.get("/logs/{log_id}", response=CaseLogOut)
def get_log(request, log_id: int):
    """获取单个日志"""
    service = _get_caselog_service()
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    return service.get_log(
        log_id=log_id,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@router.put("/logs/{log_id}", response=CaseLogOut)
def update_log(request, log_id: int, payload: CaseLogUpdate):
    """更新日志"""
    service = _get_caselog_service()
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    # 构建更新数据
    data = payload.dict(exclude_unset=True)

    # 解析提醒时间
    if "reminder_time" in data and isinstance(data["reminder_time"], str):
        data["reminder_time"] = _parse_reminder_time(data["reminder_time"])

    return service.update_log(
        log_id=log_id,
        data=data,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@router.delete("/logs/{log_id}")
def delete_log(request, log_id: int):
    """删除日志"""
    service = _get_caselog_service()
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    return service.delete_log(
        log_id=log_id,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@router.post("/logs/{log_id}/attachments")
def upload_log_attachments(request, log_id: int):
    """上传日志附件"""
    service = _get_caselog_service()
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    files = request.FILES.getlist("files") if hasattr(request, "FILES") else []

    return service.upload_attachments(
        log_id=log_id,
        files=files,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )
