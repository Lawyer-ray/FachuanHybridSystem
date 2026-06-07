"""Google Drive storage provider using Service Account authentication."""

from __future__ import annotations

import io
import logging
import random
import time
from collections.abc import Iterator
from typing import Any

from .protocols import CloudFileInfo

logger = logging.getLogger(__name__)

GDRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"

# ── Retry helper ─────────────────────────────────────────────

_MAX_RETRIES = 5
_MAX_BACKOFF = 32


def _execute_with_retry(request: Any) -> Any:
    """Execute a Google API request with exponential backoff on 429/5xx."""
    from googleapiclient.errors import HttpError

    for attempt in range(_MAX_RETRIES):
        try:
            return request.execute()
        except HttpError as e:
            if e.resp.status not in (429, 500, 502, 503) or attempt == _MAX_RETRIES - 1:
                raise
            wait = min(2 ** attempt + random.random(), _MAX_BACKOFF)
            logger.warning("Drive API %d, retry %.1fs (attempt %d/%d)", e.resp.status, wait, attempt + 1, _MAX_RETRIES)
            time.sleep(wait)
    raise RuntimeError("unreachable")


# ── Path resolver ─────────────────────────────────────────────

class _PathResolver:
    """Resolves filesystem-like paths to Google Drive file IDs with caching."""

    def __init__(self, service: Any, root_folder_id: str = "root") -> None:
        self._service = service
        self._root_id = root_folder_id
        self._cache: dict[str, str] = {"/": root_folder_id}

    def resolve(self, path: str) -> str | None:
        """Walk from root to resolve path segments to file IDs. Returns None if not found."""
        segments = [s for s in path.strip("/").split("/") if s]
        if not segments:
            return self._root_id

        current_id = self._root_id
        current_path = "/"

        for segment in segments:
            cache_key = f"{current_path.rstrip('/')}/{segment}"
            if cache_key in self._cache:
                current_id = self._cache[cache_key]
                current_path = cache_key
                continue

            request = self._service.files().list(
                q=f"'{current_id}' in parents and name='{_escape_gql(segment)}' and trashed=false",
                fields="files(id, name)",
                pageSize=1,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            results = _execute_with_retry(request)

            files = results.get("files", [])
            if not files:
                return None

            current_id = files[0]["id"]
            self._cache[cache_key] = current_id
            current_path = cache_key

        return current_id

    def invalidate(self, path: str) -> None:
        """Remove cached entries under path. Preserves root mapping."""
        prefix = path.strip("/")
        if not prefix:
            return
        keys_to_remove = [k for k in self._cache if k.startswith(f"/{prefix}")]
        for k in keys_to_remove:
            self._cache.pop(k, None)


def _escape_gql(value: str) -> str:
    """Escape special characters for Google Drive query strings."""
    return value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')


def _parse_gdrive_time(iso_str: str) -> float:
    """Parse Google Drive ISO 8601 timestamp to epoch float."""
    if not iso_str:
        return 0.0
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


# ── Provider ──────────────────────────────────────────────────

class GDriveProvider:
    """Read/write files on Google Drive using Service Account authentication."""

    def __init__(
        self,
        service_account_json: dict[str, Any],
        root_folder_id: str = "root",
        root_path: str = "",
    ) -> None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_info(
            service_account_json,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        self._service = build("drive", "v3", credentials=credentials)
        self._root = root_path.strip("/")
        self._root_id = root_folder_id
        self._resolver = _PathResolver(self._service, root_folder_id)

        # If root_path is specified, resolve it to a folder ID
        if self._root:
            resolved = self._resolver.resolve(self._root)
            if resolved:
                self._resolver._cache["/"] = resolved
                self._root_id = resolved

    def _resolve(self, path: str) -> str | None:
        """Resolve a path to a Drive file ID."""
        return self._resolver.resolve(path)

    def _find_child(self, parent_id: str, name: str) -> str | None:
        """Find a child by name under parent_id."""
        request = self._service.files().list(
            q=f"'{parent_id}' in parents and name='{_escape_gql(name)}' and trashed=false",
            fields="files(id, name)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        results = _execute_with_retry(request)
        files = results.get("files", [])
        return files[0]["id"] if files else None

    # ── Protocol implementation ────────────────────────────────

    def list_directory(self, path: str) -> list[CloudFileInfo]:
        folder_id = self._resolve(path)
        if not folder_id:
            return []

        results: list[CloudFileInfo] = []
        page_token = None
        while True:
            request = self._service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                pageSize=1000,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            resp = _execute_with_retry(request)
            for f in resp.get("files", []):
                is_folder = f["mimeType"] == GDRIVE_FOLDER_MIME
                name = f["name"]
                rel = f"{path.strip('/')}/{name}".lstrip("/")
                results.append(
                    CloudFileInfo(
                        name=name,
                        path=rel,
                        is_dir=is_folder,
                        size=int(f.get("size", 0)) if not is_folder else 0,
                        modified_at=_parse_gdrive_time(f.get("modifiedTime", "")),
                    )
                )
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        results.sort(key=lambda x: x.name.lower())
        return results

    def read_file(self, path: str) -> bytes:
        from googleapiclient.http import MediaIoBaseDownload

        file_id = self._resolve(path)
        if not file_id:
            raise FileNotFoundError(f"文件不存在: {path}")

        request = self._service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue()

    def write_file(self, path: str, content: bytes) -> None:
        import mimetypes

        from googleapiclient.http import MediaIoBaseUpload

        parts = path.strip("/").split("/")
        file_name = parts[-1]
        parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
        parent_id = self._resolve(parent_path) if parent_path else self._root_id

        if not parent_id:
            raise FileNotFoundError(f"父目录不存在: {parent_path}")

        # 自动检测 MIME 类型
        mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"

        existing_id = self._find_child(parent_id, file_name)
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=True)

        if existing_id:
            request = self._service.files().update(fileId=existing_id, media_body=media)
        else:
            metadata = {"name": file_name, "parents": [parent_id]}
            request = self._service.files().create(body=metadata, media_body=media, fields="id")

        _execute_with_retry(request)
        self._resolver.invalidate(path)

    def mkdir(self, path: str) -> None:
        parts = path.strip("/").split("/")
        current_id = self._root_id
        current_path = ""

        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else f"/{part}"
            existing = self._find_child(current_id, part)
            if existing:
                current_id = existing
            else:
                metadata = {
                    "name": part,
                    "mimeType": GDRIVE_FOLDER_MIME,
                    "parents": [current_id],
                }
                request = self._service.files().create(body=metadata, fields="id", supportsAllDrives=True)
                folder = _execute_with_retry(request)
                current_id = folder["id"]
            self._resolver._cache[current_path] = current_id

    def exists(self, path: str) -> bool:
        return self._resolve(path) is not None

    def is_dir(self, path: str) -> bool:
        file_id = self._resolve(path)
        if not file_id:
            return False
        request = self._service.files().get(fileId=file_id, fields="mimeType", supportsAllDrives=True)
        resp = _execute_with_retry(request)
        is_dir: bool = resp["mimeType"] == GDRIVE_FOLDER_MIME
        return is_dir

    def delete_file(self, path: str) -> None:
        file_id = self._resolve(path)
        if file_id:
            request = self._service.files().delete(fileId=file_id, supportsAllDrives=True)
            _execute_with_retry(request)
            self._resolver.invalidate(path)

    def get_file_info(self, path: str) -> CloudFileInfo | None:
        file_id = self._resolve(path)
        if not file_id:
            return None

        request = self._service.files().get(
            fileId=file_id, fields="name, mimeType, size, modifiedTime", supportsAllDrives=True,
        )
        resp = _execute_with_retry(request)

        is_folder: bool = resp["mimeType"] == GDRIVE_FOLDER_MIME
        name = resp["name"]
        return CloudFileInfo(
            name=name,
            path=path.strip("/"),
            is_dir=is_folder,
            size=int(resp.get("size", 0)) if not is_folder else 0,
            modified_at=_parse_gdrive_time(resp.get("modifiedTime", "")),
        )

    def walk(self, path: str) -> Iterator[tuple[str, list[str], list[CloudFileInfo]]]:
        yield from self._walk_recursive(path, set())

    def _walk_recursive(self, path: str, visited: set[str]) -> Iterator[tuple[str, list[str], list[CloudFileInfo]]]:
        file_id = self._resolve(path)
        if not file_id or file_id in visited:
            return
        visited.add(file_id)
        children = self.list_directory(path)
        subdirs = [c.name for c in children if c.is_dir]
        files = [c for c in children if not c.is_dir]
        yield (path, subdirs, files)
        for subdir in subdirs:
            sub_path = f"{path.rstrip('/')}/{subdir}"
            yield from self._walk_recursive(sub_path, visited)
