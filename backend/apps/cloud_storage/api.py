"""API endpoints for cloud storage account management.

四层架构约定：API 层只做参数提取与响应封装，不直接碰 `Model.objects`——
账号查询一律走 `account_service`。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from .account_service import aget_storage_account_by_type, get_storage_account_by_type
from .onedrive_provider import OAuthTokenManager

logger = logging.getLogger(__name__)


def _parse_device_code(request: HttpRequest) -> str | None:
    """从请求体取 device_code，缺失或格式非法返回 None。"""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    device_code = body.get("device_code", "")
    return device_code if isinstance(device_code, str) and device_code else None


def _token_manager(storage_type: str, account: Any) -> Any:
    """按存储类型构造 OAuth TokenManager。

    OneDrive 在模块顶层绑定 ``OAuthTokenManager``（测试 patch 接缝为
    ``apps.cloud_storage.api.OAuthTokenManager``）；Dropbox 包在函数内延迟导入，
    使 ``apps.cloud_storage.dropbox_provider.DropboxOAuthTokenManager`` 的 patch 生效。
    """
    if storage_type == "dropbox":
        from .dropbox_provider import DropboxOAuthTokenManager

        return DropboxOAuthTokenManager(account)
    return OAuthTokenManager(account)


def _error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


@staff_member_required
@require_POST
def start_auth(request: HttpRequest, storage_type: str, account_id: int) -> JsonResponse:  # pragma: no cover
    """开始 device code 授权流程（OneDrive / Dropbox 共用）。"""
    account = get_storage_account_by_type(account_id=account_id, storage_type=storage_type)
    if account is None:
        return _error("账号不存在", 404)

    try:
        return JsonResponse(_token_manager(storage_type, account).start_device_code_flow(account))
    except Exception:
        logger.exception("%s_start_auth 端点失败 account_id=%s", storage_type, int(account_id))
        return _error("操作失败，请稍后重试", 400)


async def _acomplete_auth(request: HttpRequest, storage_type: str, account_id: int) -> JsonResponse:
    """完成 device code 授权（轮询换 token，异步不阻塞事件循环）。"""
    device_code = _parse_device_code(request)
    if device_code is None:
        return _error("缺少 device_code", 400)

    account = await aget_storage_account_by_type(account_id=account_id, storage_type=storage_type)
    if account is None:
        return _error("账号不存在", 404)

    try:
        await _token_manager(storage_type, account).acomplete_device_code_flow(device_code)
        # 安全审计：响应不回显 token 前缀（token_preview）——前端/模板均不消费，
        # 回显明文前缀只会扩大泄露面；授权成功与否由 status 表达。
        return JsonResponse({"status": "authorized"})
    except Exception:
        logger.exception("%s_complete_auth 端点失败 account_id=%s", storage_type, int(account_id))
        return _error("操作失败，请稍后重试", 400)


@staff_member_required
@require_POST
async def onedrive_complete_auth(request: HttpRequest, account_id: int) -> JsonResponse:  # pragma: no cover
    return await _acomplete_auth(request, "onedrive", account_id)


@staff_member_required
@require_POST
async def dropbox_complete_auth(request: HttpRequest, account_id: int) -> JsonResponse:  # pragma: no cover
    return await _acomplete_auth(request, "dropbox", account_id)


@staff_member_required
@require_POST
def onedrive_start_auth(request: HttpRequest, account_id: int) -> JsonResponse:  # pragma: no cover
    return start_auth(request, "onedrive", account_id)


@staff_member_required
@require_POST
def dropbox_start_auth(request: HttpRequest, account_id: int) -> JsonResponse:  # pragma: no cover
    return start_auth(request, "dropbox", account_id)
