"""API endpoints for cloud storage account management."""

from __future__ import annotations

import json
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from .models import CloudStorageAccount
from .onedrive_provider import OAuthTokenManager

logger = logging.getLogger(__name__)


@staff_member_required
@require_POST
def onedrive_start_auth(request: HttpRequest, account_id: int) -> JsonResponse:  # pragma: no cover
    """Start OneDrive device code authorization flow."""
    try:
        account = CloudStorageAccount.objects.get(id=account_id, storage_type="onedrive")
    except CloudStorageAccount.DoesNotExist:
        return JsonResponse({"error": "账号不存在"}, status=404)

    try:
        result = OAuthTokenManager.start_device_code_flow(account)
        return JsonResponse(result)
    except Exception:
        logger.exception("onedrive_start_auth 端点失败 account_id=%s", int(account_id))
        return JsonResponse({"error": "操作失败，请稍后重试"}, status=400)


@staff_member_required
@require_POST
async def onedrive_complete_auth(request: HttpRequest, account_id: int) -> JsonResponse:  # pragma: no cover
    """Complete device code flow by polling for token (async, 不阻塞事件循环)."""
    try:
        body = json.loads(request.body)
        device_code = body.get("device_code", "")
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "缺少 device_code"}, status=400)

    account = await CloudStorageAccount.objects.filter(id=account_id, storage_type="onedrive").afirst()
    if account is None:
        return JsonResponse({"error": "账号不存在"}, status=404)

    try:
        manager = OAuthTokenManager(account)
        await manager.acomplete_device_code_flow(device_code)
        # 安全审计：响应不回显 token 前缀（token_preview）——前端/模板均不消费，
        # 回显明文前缀只会扩大泄露面；授权成功与否由 status 表达。
        return JsonResponse({"status": "authorized"})
    except Exception:
        logger.exception("onedrive_complete_auth 端点失败 account_id=%s", int(account_id))
        return JsonResponse({"error": "操作失败，请稍后重试"}, status=400)


@staff_member_required
@require_POST
def dropbox_start_auth(request: HttpRequest, account_id: int) -> JsonResponse:  # pragma: no cover
    """Start Dropbox device code authorization flow."""
    from .dropbox_provider import DropboxOAuthTokenManager

    try:
        account = CloudStorageAccount.objects.get(id=account_id, storage_type="dropbox")
    except CloudStorageAccount.DoesNotExist:
        return JsonResponse({"error": "账号不存在"}, status=404)

    try:
        result = DropboxOAuthTokenManager.start_device_code_flow(account)
        return JsonResponse(result)
    except Exception:
        logger.exception("dropbox_start_auth 端点失败 account_id=%s", int(account_id))
        return JsonResponse({"error": "操作失败，请稍后重试"}, status=400)


@staff_member_required
@require_POST
async def dropbox_complete_auth(request: HttpRequest, account_id: int) -> JsonResponse:  # pragma: no cover
    """Complete Dropbox device code flow by polling for token (async, 不阻塞事件循环)."""
    try:
        body = json.loads(request.body)
        device_code = body.get("device_code", "")
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "缺少 device_code"}, status=400)

    account = await CloudStorageAccount.objects.filter(id=account_id, storage_type="dropbox").afirst()
    if account is None:
        return JsonResponse({"error": "账号不存在"}, status=404)

    try:
        from .dropbox_provider import DropboxOAuthTokenManager

        manager = DropboxOAuthTokenManager(account)
        await manager.acomplete_device_code_flow(device_code)
        # 安全审计：同 onedrive_complete_auth，不回显 token 前缀。
        return JsonResponse({"status": "authorized"})
    except Exception:
        logger.exception("dropbox_complete_auth 端点失败 account_id=%s", int(account_id))
        return JsonResponse({"error": "操作失败，请稍后重试"}, status=400)
