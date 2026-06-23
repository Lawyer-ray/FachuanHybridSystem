"""WebDAV storage provider — works with any WebDAV-compatible service."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field

import httpx
import requests
from requests.auth import HTTPBasicAuth

from .protocols import CloudFileInfo

logger = logging.getLogger(__name__)

# Nutstore WebDAV rate limits: 600 req / 30 min (free), 1500 (paid)
_DEFAULT_RATE_LIMIT_INTERVAL = 3.5  # seconds between requests (conservative)


@dataclass
class _RateLimiter:  # pragma: no cover
    min_interval: float = _DEFAULT_RATE_LIMIT_INTERVAL
    _last_call: float = field(default=0.0, init=False)
    _lock: Any = field(default=None, init=False)  # asyncio.Lock 延迟创建

    def _ensure_lock(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()

    def wait_if_needed(self) -> None:  # pragma: no cover
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()

    async def await_if_needed(self) -> None:  # pragma: no cover
        self._ensure_lock()
        async with self._lock:  # type: ignore[union-attr]
            elapsed = time.monotonic() - self._last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_call = time.monotonic()


class WebDAVProvider:  # pragma: no cover
    """Read/write files on any WebDAV server.

    Uses ``requests`` + HTTPBasicAuth directly for full control over
    PROPFIND / PUT / GET / DELETE / MKCOL operations, avoiding the
    quirks of the ``webdavclient3`` library for edge cases.
    """

    DEFAULT_WEBDAV_URL = "https://dav.jianguoyun.com/dav/"

    def __init__(  # pragma: no cover
        self,
        username: str,
        app_password: str,
        root_path: str = "/",
        *,
        webdav_url: str = "",
        rate_limiter: _RateLimiter | None = None,
    ) -> None:
        self._username = username
        self._password = app_password
        self._webdav_url = (webdav_url or self.DEFAULT_WEBDAV_URL).rstrip("/") + "/"
        self._root = root_path.rstrip("/") or ""
        self._auth = HTTPBasicAuth(username, app_password)
        self._limiter = rate_limiter or _RateLimiter()
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.headers.update({"Accept": "application/json"})
        self._async_client: httpx.AsyncClient | None = None

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                auth=httpx.BasicAuth(self._username, self._password),
                headers={"Accept": "application/json"},
            )
        return self._async_client

    # ── Internal helpers ───────────────────────────────────────

    def _full_path(self, path: str) -> str:
        """Build absolute WebDAV path from a relative path (no trailing slash)."""
        clean = path.strip("/")
        parts = [p for p in (self._root, clean) if p]
        return "/" + "/".join(parts)

    def _url(self, path: str) -> str:
        return self._webdav_url + self._full_path(path).lstrip("/")

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:  # type: ignore[no-untyped-def]
        self._limiter.wait_if_needed()
        url = self._url(path)
        resp = self._session.request(method, url, timeout=30, **kwargs)
        if resp.status_code == 503:
            from .exceptions import CloudStorageRateLimitError

            raise CloudStorageRateLimitError(
                "云存储服务暂时不可用（请求过于频繁），请稍后重试",
                provider="WebDAV",
                retry_after=60,
            )
        if resp.status_code >= 400:
            logger.error("WebDAV %s %s returned %d", method, url, resp.status_code)
        return resp

    async def _arequest(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        await self._limiter.await_if_needed()
        url = self._url(path)
        client = self._get_async_client()
        resp = await client.request(method, url, timeout=30, **kwargs)
        if resp.status_code == 503:
            from .exceptions import CloudStorageRateLimitError

            raise CloudStorageRateLimitError(
                "云存储服务暂时不可用（请求过于频繁），请稍后重试",
                provider="WebDAV",
                retry_after=60,
            )
        if resp.status_code >= 400:
            logger.error("WebDAV %s %s returned %d", method, url, resp.status_code)
        return resp

    # ── Protocol implementation ────────────────────────────────

    def list_directory(self, path: str) -> list[CloudFileInfo]:
        """List immediate children using PROPFIND Depth:1."""
        # PROPFIND on directories requires trailing slash for Nutstore
        url = self._url(path).rstrip("/") + "/"
        self._limiter.wait_if_needed()
        resp = self._session.request(
            "PROPFIND",
            url,
            headers={"Depth": "1"},
            timeout=30,
        )
        if resp.status_code == 503:
            from .exceptions import CloudStorageRateLimitError

            raise CloudStorageRateLimitError(
                "云存储服务暂时不可用（请求过于频繁），请稍后重试",
                provider="WebDAV",
                retry_after=60,
            )
        if resp.status_code == 404:
            return []
        if resp.status_code >= 400:
            logger.error("PROPFIND %s returned %d", url, resp.status_code)
            return []

        return self._parse_propfind_response(resp.text, path)

    def _parse_propfind_response(self, xml_text: str, base_path: str) -> list[CloudFileInfo]:
        """Parse PROPFIND XML response into CloudFileInfo list."""
        import urllib.parse
        from xml.etree import ElementTree

        results: list[CloudFileInfo] = []

        # Nutstore returns hrefs prefixed with the WebDAV root (e.g. "/dav/我的坚果云")
        # We need to strip this prefix to get paths relative to our root_path
        server_url = urllib.parse.urlparse(self._webdav_url)
        dav_root_prefix = server_url.path.rstrip("/")

        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return results

        base_href = self._full_path(base_path).rstrip("/")
        for response in root.iter():
            if response.tag.endswith("}response") or response.tag == "response":
                href = None
                is_dir = False
                size = 0
                modified = 0.0
                for child in response:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if tag == "href":
                        href = urllib.parse.unquote(child.text or "")
                    elif tag == "propstat":
                        for prop in child:
                            prop_tag = prop.tag.split("}")[-1] if "}" in prop.tag else prop.tag
                            if prop_tag == "prop":
                                for p in prop:
                                    p_tag = p.tag.split("}")[-1] if "}" in p.tag else p.tag
                                    if p_tag == "resourcetype":
                                        # Check for <d:collection/>
                                        for collection in p.iter():
                                            c_tag = (
                                                collection.tag.split("}")[-1]
                                                if "}" in collection.tag
                                                else collection.tag
                                            )
                                            if c_tag == "collection":
                                                is_dir = True
                                    elif p_tag == "getcontentlength":
                                        try:
                                            size = int(p.text or "0")
                                        except ValueError:
                                            size = 0
                                    elif p_tag == "getlastmodified":
                                        try:
                                            from email.utils import parsedate_to_datetime

                                            modified = parsedate_to_datetime(p.text or "").timestamp()
                                        except (ValueError, TypeError):
                                            modified = 0.0

                if href:
                    # Strip WebDAV root prefix to get path relative to our root_path
                    if dav_root_prefix and href.startswith(dav_root_prefix):
                        href = href[len(dav_root_prefix) :]
                    # Normalize: strip trailing slash, extract name
                    href_clean = href.rstrip("/")
                    name = href_clean.split("/")[-1] if href_clean else ""
                    # Skip the base directory itself
                    if href_clean == base_href:
                        continue
                    # Compute relative path from base
                    rel_path = href_clean
                    if base_href and rel_path.startswith(base_href):
                        rel_path = rel_path[len(base_href) :].lstrip("/")

                    results.append(
                        CloudFileInfo(
                            name=name,
                            path=rel_path,
                            is_dir=is_dir,
                            size=size if not is_dir else 0,
                            modified_at=modified,
                        )
                    )

        results.sort(key=lambda x: x.name.lower())
        return results

    def read_file(self, path: str) -> bytes:
        resp = self._request("GET", path)
        resp.raise_for_status()
        return resp.content

    def write_file(self, path: str, content: bytes) -> None:
        # Ensure parent directories exist
        parent = "/".join(path.strip("/").split("/")[:-1])
        if parent:
            self.mkdir(parent)
        resp = self._request("PUT", path, data=content)
        resp.raise_for_status()

    def mkdir(self, path: str) -> None:
        # Create intermediate directories
        parts = path.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            sub = "/".join(parts[:i])
            if not self.exists(sub):
                resp = self._request("MKCOL", sub)
                if resp.status_code not in (201, 405):  # 405 = already exists
                    logger.warning("MKCOL %s returned %d", sub, resp.status_code)

    def exists(self, path: str) -> bool:
        resp = self._request("HEAD", path)
        return resp.status_code in (200, 207)

    def is_dir(self, path: str) -> bool:
        url = self._url(path).rstrip("/") + "/"
        self._limiter.wait_if_needed()
        resp = self._session.request("PROPFIND", url, headers={"Depth": "0"}, timeout=30)
        if resp.status_code >= 400:
            return False
        from xml.etree import ElementTree

        try:
            root = ElementTree.fromstring(resp.text)
        except ElementTree.ParseError:
            return False
        for elem in root.iter():
            if elem.tag.endswith("}resourcetype") or elem.tag == "resourcetype":
                for child in elem:
                    c_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if c_tag == "collection":
                        return True
        return False

    def delete_file(self, path: str) -> None:
        resp = self._request("DELETE", path)
        if resp.status_code not in (200, 204, 404):
            logger.warning("DELETE %s returned %d", path, resp.status_code)

    def get_file_info(self, path: str) -> CloudFileInfo | None:
        url = self._url(path)
        self._limiter.wait_if_needed()
        resp = self._session.request("PROPFIND", url, headers={"Depth": "0"}, timeout=30)
        if resp.status_code >= 400:
            return None

        infos = self._parse_propfind_response(resp.text, "/".join(path.strip("/").split("/")[:-1]))
        name = path.strip("/").split("/")[-1]
        for info in infos:
            if info.name == name:
                return info
        return None

    def walk(self, path: str) -> Iterator[tuple[str, list[str], list[CloudFileInfo]]]:
        """Recursively walk directory tree via WebDAV PROPFIND."""
        children = self.list_directory(path)
        subdirs = [c.name for c in children if c.is_dir]
        files = [c for c in children if not c.is_dir]
        yield (path, subdirs, files)
        for subdir in subdirs:
            sub_path = f"{path.rstrip('/')}/{subdir}"
            yield from self.walk(sub_path)

    # ── Async protocol implementation ──────────────────────────

    async def alist_directory(self, path: str) -> list[CloudFileInfo]:
        """List immediate children using PROPFIND Depth:1 (async)."""
        url = self._url(path).rstrip("/") + "/"
        await self._limiter.await_if_needed()
        client = self._get_async_client()
        resp = await client.request(
            "PROPFIND",
            url,
            headers={"Depth": "1"},
            timeout=30,
        )
        if resp.status_code == 503:
            from .exceptions import CloudStorageRateLimitError

            raise CloudStorageRateLimitError(
                "云存储服务暂时不可用（请求过于频繁），请稍后重试",
                provider="WebDAV",
                retry_after=60,
            )
        if resp.status_code == 404:
            return []
        if resp.status_code >= 400:
            logger.error("PROPFIND %s returned %d", url, resp.status_code)
            return []

        return self._parse_propfind_response(resp.text, path)

    async def aread_file(self, path: str) -> bytes:
        resp = await self._arequest("GET", path)
        resp.raise_for_status()
        return resp.content

    async def awrite_file(self, path: str, content: bytes) -> None:
        parent = "/".join(path.strip("/").split("/")[:-1])
        if parent:
            await self.amkdir(parent)
        resp = await self._arequest("PUT", path, content=content)
        resp.raise_for_status()

    async def amkdir(self, path: str) -> None:
        parts = path.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            sub = "/".join(parts[:i])
            if not await self.aexists(sub):
                resp = await self._arequest("MKCOL", sub)
                if resp.status_code not in (201, 405):
                    logger.warning("MKCOL %s returned %d", sub, resp.status_code)

    async def aexists(self, path: str) -> bool:
        resp = await self._arequest("HEAD", path)
        return resp.status_code in (200, 207)

    async def ais_dir(self, path: str) -> bool:
        url = self._url(path).rstrip("/") + "/"
        await self._limiter.await_if_needed()
        client = self._get_async_client()
        resp = await client.request("PROPFIND", url, headers={"Depth": "0"}, timeout=30)
        if resp.status_code >= 400:
            return False
        from xml.etree import ElementTree

        try:
            root = ElementTree.fromstring(resp.text)
        except ElementTree.ParseError:
            return False
        for elem in root.iter():
            if elem.tag.endswith("}resourcetype") or elem.tag == "resourcetype":
                for child in elem:
                    c_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if c_tag == "collection":
                        return True
        return False

    async def adelete_file(self, path: str) -> None:
        resp = await self._arequest("DELETE", path)
        if resp.status_code not in (200, 204, 404):
            logger.warning("DELETE %s returned %d", path, resp.status_code)

    async def aget_file_info(self, path: str) -> CloudFileInfo | None:
        url = self._url(path)
        await self._limiter.await_if_needed()
        client = self._get_async_client()
        resp = await client.request("PROPFIND", url, headers={"Depth": "0"}, timeout=30)
        if resp.status_code >= 400:
            return None

        infos = self._parse_propfind_response(resp.text, "/".join(path.strip("/").split("/")[:-1]))
        name = path.strip("/").split("/")[-1]
        for info in infos:
            if info.name == name:
                return info
        return None

    async def awalk(self, path: str) -> AsyncIterator[tuple[str, list[str], list[CloudFileInfo]]]:
        """Recursively walk directory tree via WebDAV PROPFIND (async)."""
        children = await self.alist_directory(path)
        subdirs = [c.name for c in children if c.is_dir]
        files = [c for c in children if not c.is_dir]
        yield (path, subdirs, files)
        for subdir in subdirs:
            sub_path = f"{path.rstrip('/')}/{subdir}"
            async for item in self.awalk(sub_path):
                yield item


# Backward-compat alias
JianguoyunProvider = WebDAVProvider
