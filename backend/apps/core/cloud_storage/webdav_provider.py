"""Nutstore (坚果云) WebDAV storage provider."""

from __future__ import annotations

import io
import logging
import time
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field

import requests
from requests.auth import HTTPBasicAuth

from .protocols import CloudFileInfo

logger = logging.getLogger(__name__)

# Nutstore WebDAV rate limits: 600 req / 30 min (free), 1500 (paid)
_DEFAULT_RATE_LIMIT_INTERVAL = 3.5  # seconds between requests (conservative)


@dataclass
class _RateLimiter:
    min_interval: float = _DEFAULT_RATE_LIMIT_INTERVAL
    _last_call: float = field(default=0.0, init=False)

    def wait_if_needed(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()


class JianguoyunProvider:
    """Read/write files on Nutstore via WebDAV.

    Uses ``requests`` + HTTPBasicAuth directly for full control over
    PROPFIND / PUT / GET / DELETE / MKCOL operations, avoiding the
    quirks of the ``webdavclient3`` library for edge cases.
    """

    WEBDAV_URL = "https://dav.jianguoyun.com/dav/"

    def __init__(
        self,
        username: str,
        app_password: str,
        root_path: str = "/",
        *,
        rate_limiter: _RateLimiter | None = None,
    ) -> None:
        self._username = username
        self._password = app_password
        self._root = root_path.rstrip("/") or ""
        self._auth = HTTPBasicAuth(username, app_password)
        self._limiter = rate_limiter or _RateLimiter()
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.headers.update({"Accept": "application/json"})

    # ── Internal helpers ───────────────────────────────────────

    def _full_path(self, path: str) -> str:
        """Build absolute WebDAV path from a relative path."""
        clean = path.strip("/")
        parts = [p for p in (self._root, clean) if p]
        return "/" + "/".join(parts) + "/"

    def _url(self, path: str) -> str:
        return self.WEBDAV_URL + self._full_path(path).lstrip("/")

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:  # type: ignore[no-untyped-def]
        self._limiter.wait_if_needed()
        url = self._url(path)
        resp = self._session.request(method, url, timeout=30, **kwargs)
        if resp.status_code >= 400:
            logger.error("WebDAV %s %s returned %d", method, url, resp.status_code)
        return resp

    # ── Protocol implementation ────────────────────────────────

    def list_directory(self, path: str) -> list[CloudFileInfo]:
        """List immediate children using PROPFIND Depth:1."""
        url = self._url(path)
        self._limiter.wait_if_needed()
        resp = self._session.request(
            "PROPFIND",
            url,
            headers={"Depth": "1"},
            timeout=30,
        )
        if resp.status_code == 404:
            return []
        if resp.status_code >= 400:
            logger.error("PROPFIND %s returned %d", url, resp.status_code)
            return []

        return self._parse_propfind_response(resp.text, path)

    def _parse_propfind_response(self, xml_text: str, base_path: str) -> list[CloudFileInfo]:
        """Parse PROPFIND XML response into CloudFileInfo list."""
        from xml.etree import ElementTree

        results: list[CloudFileInfo] = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return results

        # Strip namespace prefixes for easier XPath
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
                        href = child.text or ""
                    elif tag == "propstat":
                        for prop in child:
                            prop_tag = prop.tag.split("}")[-1] if "}" in prop.tag else prop.tag
                            if prop_tag == "prop":
                                for p in prop:
                                    p_tag = p.tag.split("}")[-1] if "}" in p.tag else p.tag
                                    if p_tag == "resourcetype":
                                        # Check for <d:collection/>
                                        for collection in p.iter():
                                            c_tag = collection.tag.split("}")[-1] if "}" in collection.tag else collection.tag
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
                    # Normalize: strip trailing slash, extract name
                    href_clean = href.rstrip("/")
                    name = href_clean.split("/")[-1] if href_clean else ""
                    # Skip the base directory itself
                    if href_clean.rstrip("/") == base_href.rstrip("/"):
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
        results = self.list_directory(path)
        # If we can list it, it's a directory
        url = self._url(path)
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
