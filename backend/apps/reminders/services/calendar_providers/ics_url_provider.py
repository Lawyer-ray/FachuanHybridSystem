"""ICS URL provider — download .ics from a remote URL and parse it."""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

from .base import CalendarEvent
from .ics_provider import IcsFileProvider

logger = logging.getLogger(__name__)

#: Maximum .ics file size to download (5 MB)
MAX_ICS_SIZE = 5 * 1024 * 1024

#: Download timeout in seconds
DOWNLOAD_TIMEOUT = 10


class IcsUrlProvider:
    """Download .ics content from a URL and parse events."""

    def __init__(self) -> None:
        self._ics_provider = IcsFileProvider()

    def fetch_events(self, *, url: str, **kwargs: object) -> list[CalendarEvent]:  # pragma: no cover
        """Download .ics from *url* and return parsed CalendarEvent list."""
        validation_error = self._validate_url(url)
        if validation_error:
            logger.info("ICS URL validation failed: %s", validation_error)
            return []

        try:
            response = httpx.get(url, timeout=DOWNLOAD_TIMEOUT, follow_redirects=False)
            if response.status_code in (301, 302, 303, 307, 308):
                # Re-validate redirect target to prevent SSRF bypass
                redirect_url = response.headers.get("location")
                if redirect_url:
                    validation_error = self._validate_url(redirect_url)
                    if validation_error:
                        logger.info("Redirect URL validation failed: %s", validation_error)
                        return []
                    response = httpx.get(redirect_url, timeout=DOWNLOAD_TIMEOUT, follow_redirects=False)
                    response.raise_for_status()
            else:
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.info("ICS URL download failed: %s", exc)
            return []

        content_length = len(response.content)
        if content_length > MAX_ICS_SIZE:
            logger.info("ICS URL content too large: %d bytes", content_length)
            return []

        return self._ics_provider.fetch_events(ics_content=response.content)

    async def afetch_events(self, *, url: str, **kwargs: object) -> list[CalendarEvent]:  # pragma: no cover
        """异步版本。Download .ics from *url* and return parsed CalendarEvent list."""
        validation_error = self._validate_url(url)
        if validation_error:
            logger.info("ICS URL validation failed: %s", validation_error)
            return []

        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=False) as client:
                response = await client.get(url)
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_url = response.headers.get("location")
                    if redirect_url:
                        validation_error = self._validate_url(redirect_url)
                        if validation_error:
                            logger.info("Redirect URL validation failed: %s", validation_error)
                            return []
                        response = await client.get(redirect_url)
                        response.raise_for_status()
                else:
                    response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.info("ICS URL download failed: %s", exc)
            return []

        content_length = len(response.content)
        if content_length > MAX_ICS_SIZE:
            logger.info("ICS URL content too large: %d bytes", content_length)
            return []

        return self._ics_provider.fetch_events(ics_content=response.content)

    def _validate_url(self, url: str) -> str:
        """Return an error message if the URL is invalid/unsafe, empty string if OK."""
        try:
            parsed = urlparse(url)
        except Exception:
            return "URL 格式无效"

        if parsed.scheme != "https":
            return "仅支持 https 协议的 URL"

        hostname = parsed.hostname
        if not hostname:
            return "URL 缺少主机名"

        # ── 字面 IP：直接按内网/环回/保留判定（保持「内网地址」口径）──
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None
        if ip is not None:
            if ip.is_private or ip.is_loopback or ip.is_reserved:
                return "不允许访问内网地址"
            return ""

        # ── 域名：本地名单先行（localhost 保持「本地地址」口径）──
        # "0.0.0.0" 是 SSRF 拦截名单条目，并非 bind 地址
        blocked_hosts = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}  # nosec B104
        if hostname.lower() in blocked_hosts:
            return "不允许访问本地地址"

        # 安全审计（2026-10-19）：域名要做 DNS 解析后再校验——只拦字面 IP 时，
        # 一条 A 记录指向内网的公网域名即可绕过（DNS rebinding 到内网）
        try:
            infos = socket.getaddrinfo(hostname, None)
        except OSError:
            return "域名解析失败"
        for info in infos:
            addr = info[4][0]
            try:
                resolved = ipaddress.ip_address(str(addr).split("%")[0])
            except ValueError:
                continue
            if resolved.is_private or resolved.is_loopback or resolved.is_reserved:
                return "不允许访问内网地址"

        return ""
