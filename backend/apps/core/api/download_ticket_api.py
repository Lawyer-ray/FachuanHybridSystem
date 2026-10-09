"""短时下载票据签发端点（安全审计 2026Q4 M-2）。

**为什么需要这个端点**：JWT 退出 ``?token=`` 后，``<img src>`` /
``<iframe src>`` / ``<a download>`` 这类**浏览器原生发起、带不上
Authorization 头**的请求就没有凭证可用了。解法是让前端先用一次普通
（能带头的）API 调用换取一张短时票据，再把票据拼进 URL。

**设计约束**：

- 票据只含 ``user_id``，不含 JWT、不含任何长期凭证——从 access log 里
  捞出来也只能在 60 秒内用一次，换不来身份；
- 一次签发一张，按需取用，不做长列表（避免变成新的刷量面）；
- 端点本身复用普通 API 限流（``AUTH`` bucket），且要求已认证。

``resource`` 参数仅用于日志排障，**不参与权限判定**：真正的资源访问控制
仍由各下载端点自己完成（票据只回答「谁在请求」，不回答「能不能访问这个
资源」）。
"""

from __future__ import annotations

import logging
from typing import Any

from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth
from apps.core.security.download_tickets import issue_download_ticket

logger = logging.getLogger(__name__)

router = Router(tags=["下载票据"], auth=JWTOrSessionAuth())


class DownloadTicketIn(Schema):
    """签发票据的入参。``resource`` 仅用于日志排障，不参与权限判定。"""

    resource: str = ""


class DownloadTicketOut(Schema):
    ticket: str
    expires_in: int


@router.post("/download-ticket", response=DownloadTicketOut)
def create_download_ticket(request: Any, payload: DownloadTicketIn) -> DownloadTicketOut:
    """为当前用户签发一张短时下载票据。

    Query / body:
        resource: 可选，目标资源的日志标识（如 ``media:materials/a.pdf``）。
                  仅写入日志，不参与权限判定，长度上限 200 字符。

    Returns:
        ticket: 票据字符串，拼接到下载 URL 的 ``?ticket=`` 参数上；
        expires_in: 有效期秒数（默认 60）。
    """
    from django.conf import settings

    user = getattr(request, "auth", None) or getattr(request, "user", None)
    user_id = getattr(user, "id", None)
    if user_id is None:
        # 走到这里说明认证中间件没拦住（理论上不可达），fail-closed
        logger.warning("download_ticket_issue_without_user")
        from apps.core.exceptions import PermissionDenied

        raise PermissionDenied(message="未认证", code="UNAUTHENTICATED")

    resource = (payload.resource or "").strip()
    ticket = issue_download_ticket(int(user_id), resource=resource)
    ttl = int(getattr(settings, "DOWNLOAD_TICKET_TTL_SECONDS", 60))

    logger.info(
        "download_ticket_issued",
        extra={"user_id": int(user_id), "resource_prefix": resource.split(":", 1)[0][:40]},
    )
    return DownloadTicketOut(ticket=ticket, expires_in=ttl)
