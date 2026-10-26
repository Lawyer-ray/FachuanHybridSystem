"""DS 取文件代理的 service 层（从 API 层下沉）。

API 层只做参数提取与响应映射；用户解析、站内路径白名单、跨 service
取文件都在这里。放行哪些业务路径、怎么取文件、谁能看，统一由
`domain_registry` 声明——本模块不再写死某个业务域。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.contrib.auth import get_user_model
from django.http import FileResponse

logger = logging.getLogger(__name__)


def parse_contract_review_path(path: str) -> tuple[UUID, str] | None:
    """兼容旧调用点：识别 contract-review 下载路径。

    保留此函数仅为存量 import；新代码请用 domain_registry.domain_for_path。
    """
    from .domain_registry import get_domain

    domain = get_domain("contract_review")
    return domain.parse_path(path) if domain else None


def resolve_user(uid: str) -> Any:
    """按签名令牌里的 user_id 解析用户；不存在返回 None。"""
    try:
        return get_user_model().objects.filter(pk=int(uid)).first()
    except (TypeError, ValueError):
        return None


def fetch_internal_file(path: str, user: Any) -> FileResponse | None:
    """按签名里的用户身份读取站内文件；不支持/无权/业务失败返回 None。

    权限口径由业务域统一声明（属主或超管）；`resolve_for_proxy` 类业务域
    （如 contract_folder）自己走原端点的 ACL，代理不放宽任何权限。
    """
    from .domain_registry import domain_for_path, is_owner_or_admin

    hit = domain_for_path(path)
    if hit is None:
        logger.warning("OnlyOffice 代理不支持该路径: %s", path)
        return None
    domain, owner_id, rest = hit

    if domain.resolve_for_proxy is not None:
        fpath = domain.resolve_for_proxy(user, owner_id, rest)
        if fpath is None:
            logger.warning("OnlyOffice 代理取文件失败: path=%s user=%s", path, getattr(user, "pk", None))
            return None
        return FileResponse(fpath.open("rb"), as_attachment=True, filename=fpath.name)

    from apps.contract_review.services.wiring import get_review_service

    svc = get_review_service()
    task = svc.get_task_status(owner_id)
    if not is_owner_or_admin(user, domain.get_owner_id(task)):
        logger.warning("OnlyOffice 代理拒绝越权取文件: path=%s user=%s", path, user.pk)
        return None
    fpath = domain.resolve_file(svc, owner_id, rest)
    return FileResponse(fpath.open("rb"), as_attachment=True, filename=fpath.name)
