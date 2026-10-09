"""短时下载票据（安全审计 2026Q4 M-2）。

**问题**：``JWTOrSessionAuth`` 为了兼容 ``<img src>`` / ``<iframe src>`` /
``<a download>`` 这类带不上 ``Authorization`` 头的场景，支持从 ``?token=``
查询参数取 JWT。但完整 JWT 会随之落入：

- nginx access log（``$request`` 含完整 query string）；
- 浏览器历史；
- 外链跳转时的 ``Referer`` 头；
- 任何中间代理 / CDN 的访问日志。

拿到 JWT 即等于拿到身份（有效期 2 小时，且可换 refresh）。用查询参数传
**长期凭证**是这里的根因。

**方案**：不再把 JWT 放进 URL。需要一个「能放进 URL、但即使泄露也无多大
损失」的凭证——短时一次性票据：

- ``issue_download_ticket`` 由已认证端点签发，票据里只带 ``user_id`` +
  目标资源标识，**不含 JWT、不含任何长期凭证**；
- 票据用 ``django.core.signing`` 加 ``SECRET_KEY`` 签名并带时间戳，天然
  防伪造、可验过期，无需落库；
- ``consume_download_ticket`` 校验签名与有效期后兑现为 ``user_id``，端点
  据此鉴权。票据默认 60 秒有效——足够浏览器发起一次请求，却不值得攻击者
  从日志里捞出来重用；
- 单次使用：票据入 ``DOWNLOAD_TICKET_JTI_CACHE`` 前缀的缓存（Redis 优先），
  兑现后即标记，重复兑现被拒。缓存不可用时（如 LocMemCache 被清）退化为
  「仅靠签名 + 过期」，不因缓存故障拒绝合法下载。

**为什么不是 session cookie**：下载可能由第三方日历 App / 外部浏览器
（ICS 订阅那类）发起，没有本站 cookie；且本项目的认证主路径是 JWT。

**为什么不是 nginx secure link**：那要求 nginx 与后端共享密钥并改造
``deploy/``（该目录被 gitignore，改动进不了仓库），覆盖面不可控。
"""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from django.conf import settings
from django.core import signing

logger = logging.getLogger(__name__)

TICKET_SALT = "fachuan.download-ticket.v1"
TICKET_PARAM = "ticket"
_JTI_CACHE_PREFIX = "download_ticket:jti:"


class TicketError(Exception):
    """票据无效 / 过期 / 已使用。"""


def _ttl_seconds() -> int:
    raw = getattr(settings, "DOWNLOAD_TICKET_TTL_SECONDS", 60)
    try:
        return max(5, int(raw))
    except (TypeError, ValueError):
        return 60


def _single_use() -> bool:
    return bool(getattr(settings, "DOWNLOAD_TICKET_SINGLE_USE", True))


def issue_download_ticket(user_id: int, *, resource: str = "") -> str:
    """为已认证用户签发一张短时下载票据。

    ``resource`` 只用于日志排障（如 ``media:materials/x.pdf``），**不参与**
    权限判定——真正的资源访问控制仍由各端点自己做，票据只回答「谁在请求」。

    ``jti`` 是票据自身的随机标识，用于单次使用判定；它与签名相互独立，
    伪造者无法猜中。
    """
    payload: dict[str, Any] = {"uid": int(user_id), "jti": secrets.token_urlsafe(12)}
    if resource:
        payload["res"] = resource[:200]
    return signing.dumps(payload, salt=TICKET_SALT, compress=True)


def _mark_used(jti: str) -> bool:
    """标记票据已使用，返回是否首次标记成功（缓存不可用时视为成功）。

    ``cache.add`` 的语义正是「不存在才写入」，所以返回 False 就等于
    「这个 jti 已经兑现过」。缓存键带 TTL，无需手动清理。
    """
    from django.core.cache import cache

    try:
        return bool(cache.add(f"{_JTI_CACHE_PREFIX}{jti}", 1, timeout=_ttl_seconds() + 30))
    except Exception:  # pragma: no cover - 缓存后端故障不放宽也不误杀
        logger.warning("download_ticket_jti_cache_unavailable", exc_info=True)
        return True


def consume_download_ticket(ticket: str) -> int:
    """校验并兑现票据，返回 ``user_id``。失败抛 ``TicketError``。

    校验顺序：签名 → 过期 → 单次使用。任一步不过都抛，由调用方决定
    转成 403 还是重定向到登录。
    """
    if not ticket:
        raise TicketError("empty ticket")

    try:
        payload = signing.loads(ticket, salt=TICKET_SALT, max_age=_ttl_seconds())
    except signing.SignatureExpired as exc:
        raise TicketError("ticket expired") from exc
    except signing.BadSignature as exc:
        raise TicketError("bad signature") from exc

    user_id = payload.get("uid")
    if not isinstance(user_id, int):
        raise TicketError("malformed payload")

    if _single_use():
        jti = payload.get("jti")
        if not isinstance(jti, str) or not jti:
            raise TicketError("missing jti")
        if not _mark_used(jti):
            raise TicketError("ticket already used")

    return user_id


def append_ticket(url: str, ticket: str) -> str:
    """把票据追加到 URL 的 query string（保留既有参数）。

    空票据原样返回：拼出 ``?ticket=`` 会让后端走一趟票据解析再失败，
    不如让请求以「无凭证」的形态直接被拒，日志上也更干净。
    """
    if not ticket:
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query[TICKET_PARAM] = [ticket]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def strip_ticket(url: str) -> str:
    """移除 URL 上的票据参数（日志/展示用，避免票据进日志）。"""
    parsed = urlparse(url)
    if TICKET_PARAM not in parsed.query:
        return url
    query = parse_qs(parsed.query, keep_blank_values=True)
    query.pop(TICKET_PARAM, None)
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
