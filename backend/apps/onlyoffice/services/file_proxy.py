"""DS 取文件代理的 service 层（从 API 层下沉）。

API 层只做参数提取与响应映射；用户解析、站内路径白名单、跨 service
取文件都在这里。权限口径与 contract_review 的 review_api._check_task_access
一致：任务属主或超管。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from django.contrib.auth import get_user_model
from django.http import FileResponse

logger = logging.getLogger(__name__)

# DS 取文件走代理时唯一放行的业务路径（与 editor-config 支持面一致）
_CONTRACT_REVIEW_RE = re.compile(r"^/api/v1/contract-review/([0-9a-f-]{36})/(download|download-original)")


def parse_contract_review_path(path: str) -> tuple[UUID, str] | None:
    """识别 contract-review 下载路径，返回 (task_id, download|download-original)。"""
    m = _CONTRACT_REVIEW_RE.match(path)
    if not m:
        return None
    return UUID(m.group(1)), m.group(2)


def resolve_user(uid: str) -> Any:
    """按签名令牌里的 user_id 解析用户；不存在返回 None。"""
    try:
        return get_user_model().objects.filter(pk=int(uid)).first()
    except (TypeError, ValueError):
        return None


def fetch_internal_file(path: str, user: Any) -> FileResponse | None:
    """按签名里的用户身份读取站内文件；不支持/无权/业务失败返回 None。

    权限复用各业务 service 的判定（与 REST 端点同口径），代理不放宽任何权限。
    """
    from apps.contract_review.services.wiring import get_review_service

    parsed = parse_contract_review_path(path)
    if parsed is None:
        logger.warning("OnlyOffice 代理不支持该路径: %s", path)
        return None
    task_id, which = parsed

    svc = get_review_service()
    task = svc.get_task_status(task_id)
    # 与 review_api._check_task_access 同口径：任务属主或超管
    if not (user.is_superuser or getattr(task, "user_id", None) == user.pk):
        logger.warning("OnlyOffice 代理拒绝越权取文件: path=%s user=%s", path, user.pk)
        return None
    fpath = svc.get_result_file(task_id) if which == "download" else svc.get_original_file(task_id)
    return FileResponse(fpath.open("rb"), as_attachment=True, filename=fpath.name)
