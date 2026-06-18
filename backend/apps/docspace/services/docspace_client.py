"""OnlyOffice DocSpace REST API 客户端。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass(frozen=True)
class DocSpaceFile:
    """DocSpace 文件元信息。"""

    id: int
    title: str
    folder_id: int
    file_ext: str
    content_length: int
    web_url: str  # 编辑器 URL
    download_url: str  # 下载 URL


class DocSpaceClient:
    """OnlyOffice DocSpace REST API 客户端。"""

    def __init__(self, portal_url: str, api_token: str) -> None:
        self._base = portal_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_token}"}

    # ── 上传 ──────────────────────────────────────────────

    def upload_file(self, folder_id: int, filename: str, file_content: bytes) -> DocSpaceFile:
        """上传文件到指定文件夹。"""
        url = f"{self._base}/api/2.0/files/{folder_id}/upload"
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                url,
                headers=self._headers,
                files={"file": (filename, file_content)},
            )
            resp.raise_for_status()
        data = resp.json()
        items: list[dict[str, Any]] = data.get("response", [])
        if not items:
            raise ValueError("DocSpace 上传失败：返回空结果")
        return _parse_file_entry(items[0])

    # ── 查询 ──────────────────────────────────────────────

    def get_file_info(self, file_id: int) -> DocSpaceFile:
        """获取文件元信息。"""
        url = f"{self._base}/api/2.0/files/file/{file_id}"
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url, headers=self._headers)
            resp.raise_for_status()
        data = resp.json()
        return _parse_file_entry(data["response"])

    def list_files(self, folder_id: int) -> list[DocSpaceFile]:
        """列出文件夹下的文件（仅文件，不含子文件夹）。"""
        url = f"{self._base}/api/2.0/files/{folder_id}"
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url, headers=self._headers)
            resp.raise_for_status()
        data = resp.json()
        files_raw = data.get("response", {}).get("files", [])
        return [_parse_file_entry(f) for f in files_raw]

    # ── 下载 ──────────────────────────────────────────────

    def download_file(self, file_id: int) -> tuple[bytes, str]:
        """下载文件，返回 (content, filename)。"""
        url = f"{self._base}/filehandler.ashx?action=download&fileid={file_id}"
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=self._headers)
            resp.raise_for_status()
        # 从 Content-Disposition 提取文件名
        cd = resp.headers.get("content-disposition", "")
        filename = _extract_filename(cd) or f"file_{file_id}"
        return resp.content, filename

    # ── 删除 ──────────────────────────────────────────────

    def delete_file(self, file_id: int) -> None:
        """删除 DocSpace 上的文件。"""
        url = f"{self._base}/api/2.0/files/file/{file_id}"
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.delete(url, headers=self._headers)
            resp.raise_for_status()


# ── 内部工具 ──────────────────────────────────────────────


def _parse_file_entry(raw: dict[str, Any]) -> DocSpaceFile:
    """将 DocSpace API 返回的文件 JSON 解析为 DocSpaceFile。"""
    return DocSpaceFile(
        id=raw["id"],
        title=raw.get("title", ""),
        folder_id=raw.get("folderId", 0),
        file_ext=raw.get("fileExst", ""),
        content_length=raw.get("pureContentLength", 0),
        web_url=raw.get("webUrl", ""),
        download_url=raw.get("viewUrl", ""),
    )


def _extract_filename(content_disposition: str) -> str:
    """从 Content-Disposition header 提取文件名。"""
    import re

    match = re.search(r"filename\*?=(?:UTF-8''|\"?)([^\";\s]+)", content_disposition, re.IGNORECASE)
    if match:
        from urllib.parse import unquote

        return unquote(match.group(1).strip('"'))
    return ""
