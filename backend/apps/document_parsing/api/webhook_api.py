"""云端解析回调接收端点（MinerU / Textin 推送）。

挂载在 ``/api/v1/document-parsing`` 之下，最终路径
``/api/v1/document-parsing/webhook/{provider}``。

**为什么是 auth=None**：调用方是 MinerU / Textin 的服务器，拿不到也不该拿
JWT。安全边界改由「请求签名 + 定位不到任务就拒」承担，具体见
``services/callback_dispatch_service.py``；未启用回调的平台（配置缺失）直接
回 404，等于端点不存在。

**为什么单独一个 router**：解析主路由在 ``api.py`` 里以
``JWTOrSessionAuth()`` 挂载，挂载级 auth 会覆盖端点上的 ``auth=None``，
混在同一个 router 里回调就永远打不进来。
"""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from ninja import Router

from apps.document_parsing.services.callback_config import is_callback_enabled
from apps.document_parsing.services.callback_dispatch_service import (
    ACCEPTED,
    DUPLICATE,
    DocumentParsingCallbackDispatchService,
)

logger = logging.getLogger("apps.document_parsing")

router = Router(tags=["文档解析"])

#: 处理结论 → HTTP 状态码。
#:
#: 200 只给「确认处理过」（含重复推送：重复推送的语义是「这份结果我已经收下
#: 了」，让云端停止重推才是对的）。其余一律非 200——云端以状态码判定送达，
#: 把验签失败当成 200 会让一次真实的推送被永久丢弃。
_STATUS_BY_OUTCOME: dict[str, int] = {
    ACCEPTED: 200,
    DUPLICATE: 200,
    "signature": 403,
    "unrecognized": 400,
    "task_not_found": 404,
}


def _dispatch() -> DocumentParsingCallbackDispatchService:
    """工厂函数：创建回调分发服务实例。"""
    return DocumentParsingCallbackDispatchService()


def receive_webhook(request: HttpRequest, provider: str) -> HttpResponse:
    """接收云端回调并写回解析结果。

    验签策略（fail-closed）：平台未启用回调 → 404；签名不匹配 → 403；
    载荷不可识别 → 400；找不到对应任务 → 404。只有真的写回了（或确认是
    重复推送）才回 200。
    """
    if not is_callback_enabled(provider):
        logger.warning("回调端点被调用但平台未启用回调: provider=%s", provider)
        return JsonResponse({"error": "provider disabled"}, status=404)

    headers = {key.lower(): value for key, value in request.headers.items()}
    outcome = _dispatch().handle(provider, request.body, headers)
    status = _STATUS_BY_OUTCOME.get(outcome, 400)
    if status != 200:
        logger.warning("回调被拒: provider=%s outcome=%s status=%s", provider, outcome, status)
    return JsonResponse({"result": outcome}, status=status)


router.add_api_operation(
    "/webhook/{provider}",
    ["POST"],
    receive_webhook,
    auth=None,
    summary="云解析平台完成回调（MinerU / Textin 服务器调用）",
)
