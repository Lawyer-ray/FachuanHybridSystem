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
        logger.exception("onedrive_start_auth 端点失败 account_id=%s", account_id)
        return JsonResponse({"error": "操作失败，请稍后重试"}, status=400)


@staff_member_required
@require_POST
def onedrive_complete_auth(request: HttpRequest, account_id: int) -> JsonResponse:  # pragma: no cover
    """Complete device code flow by polling for token."""
    try:
        body = json.loads(request.body)
        device_code = body.get("device_code", "")
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "缺少 device_code"}, status=400)

    try:
        account = CloudStorageAccount.objects.get(id=account_id, storage_type="onedrive")
    except CloudStorageAccount.DoesNotExist:
        return JsonResponse({"error": "账号不存在"}, status=404)

    try:
        manager = OAuthTokenManager(account)
        access_token = manager.complete_device_code_flow(device_code)
        return JsonResponse({"status": "authorized", "token_preview": access_token[:20] + "..."})
    except Exception:
        logger.exception("onedrive_complete_auth 端点失败 account_id=%s", account_id)
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
        logger.exception("dropbox_start_auth 端点失败 account_id=%s", account_id)
        return JsonResponse({"error": "操作失败，请稍后重试"}, status=400)


@staff_member_required
@require_POST
def dropbox_complete_auth(request: HttpRequest, account_id: int) -> JsonResponse:  # pragma: no cover
    """Complete Dropbox device code flow by polling for token."""
    try:
        body = json.loads(request.body)
        device_code = body.get("device_code", "")
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "缺少 device_code"}, status=400)

    try:
        account = CloudStorageAccount.objects.get(id=account_id, storage_type="dropbox")
    except CloudStorageAccount.DoesNotExist:
        return JsonResponse({"error": "账号不存在"}, status=404)

    try:
        from .dropbox_provider import DropboxOAuthTokenManager

        manager = DropboxOAuthTokenManager(account)
        access_token = manager.complete_device_code_flow(device_code)
        return JsonResponse({"status": "authorized", "token_preview": access_token[:20] + "..."})
    except Exception:
        logger.exception("dropbox_complete_auth 端点失败 account_id=%s", account_id)
        return JsonResponse({"error": "操作失败，请稍后重试"}, status=400)
