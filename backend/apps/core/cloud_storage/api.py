"""API endpoints for cloud storage account management."""

from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import CloudStorageAccount
from .onedrive_provider import OAuthTokenManager


@require_POST
def onedrive_start_auth(request, account_id: int) -> JsonResponse:
    """Start OneDrive device code authorization flow."""
    try:
        account = CloudStorageAccount.objects.get(id=account_id, storage_type="onedrive")
    except CloudStorageAccount.DoesNotExist:
        return JsonResponse({"error": "账号不存在"}, status=404)

    try:
        result = OAuthTokenManager.start_device_code_flow(account)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@require_POST
def onedrive_complete_auth(request, account_id: int) -> JsonResponse:
    """Complete device code flow by polling for token."""
    import json

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
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
