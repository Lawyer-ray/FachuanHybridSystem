"""ICS URL provider — download .ics from a remote URL and parse it."""

from __future__ import annotations

import ipaddress
import logging
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
            response = httpx.get(url, timeout=DOWNLOAD_TIMEOUT, follow_redirects=True)
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

        # Block private/reserved IPs to prevent SSRF
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_reserved:
                return "不允许访问内网地址"
        except ValueError:
            pass  # hostname is a domain, not an IP

        # Block common local hostnames
        blocked_hosts = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
        if hostname.lower() in blocked_hosts:
            return "不允许访问本地地址"

        return ""
