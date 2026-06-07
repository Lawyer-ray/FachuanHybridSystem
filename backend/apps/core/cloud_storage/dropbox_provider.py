"""Dropbox storage provider with OAuth2 device code flow."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .protocols import CloudFileInfo

logger = logging.getLogger(__name__)

DEVICE_CODE_URL = "https://api.dropboxapi.com/oauth2/device/code"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
SCOPE = "files.content.write files.content.read files.metadata.read"


@dataclass
class _TokenData:
    access_token: str
    refresh_token: str
    expires_at: datetime


class DropboxOAuthTokenManager:
    """Manages Dropbox OAuth2 device code flow and token lifecycle."""

    def __init__(self, account: Any) -> None:
        self._account = account

    def get_valid_token(self) -> str:
        """Return a valid access_token, refreshing if necessary."""
        token = self._account.get_decrypted_dropbox_access_token()
        expires_at = getattr(self._account, "dropbox_token_expires_at", None)

        if token and expires_at and expires_at > datetime.now(UTC) + timedelta(minutes=5):
            return str(token)

        refresh_token = self._account.get_decrypted_dropbox_refresh_token()
        if refresh_token:
            try:
                return self._refresh_token(refresh_token)
            except Exception as e:
                raise RuntimeError(
                    "Dropbox 授权已过期（refresh_token 无效），请在 Admin 后台 -> 云存储账号 "
                    "中重新点击「获取授权」按钮完成授权。"
                ) from e

        raise RuntimeError("Dropbox 未授权。请在 Admin 后台 -> 云存储账号 中点击「获取授权」按钮完成授权。")

    def _refresh_token(self, refresh_token: str) -> str:
        resp = httpx.post(
            TOKEN_URL,
            data={
                "client_id": self._account.dropbox_app_key,
                "client_secret": self._account.get_decrypted_dropbox_app_secret(),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        token_data = _TokenData(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 14400)),
        )
        self._save_token(token_data)
        return token_data.access_token

    def _save_token(self, token_data: _TokenData) -> None:
        from apps.core.security.secret_codec import SecretCodec

        codec = SecretCodec()
        self._account.dropbox_access_token = codec.encrypt(token_data.access_token)
        self._account.dropbox_refresh_token = codec.encrypt(token_data.refresh_token)
        self._account.dropbox_token_expires_at = token_data.expires_at
        self._account.save(
            update_fields=["dropbox_access_token", "dropbox_refresh_token", "dropbox_token_expires_at", "updated_at"]
        )

    @staticmethod
    def start_device_code_flow(account: Any) -> dict[str, Any]:
        """Initiate Dropbox device code flow. Returns dict with user_code, verification_uri, device_code."""
        app_key = account.dropbox_app_key
        if not app_key:
            raise ValueError("请先配置 Dropbox App Key")

        resp = httpx.post(
            DEVICE_CODE_URL,
            json={
                "client_id": app_key,
                "scope": SCOPE,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "user_code": data["user_code"],
            "verification_uri": data["verification_uri"],
            "device_code": data["device_code"],
            "expires_in": data.get("expires_in", 900),
            "interval": data.get("interval", 5),
        }

    def complete_device_code_flow(self, device_code: str, interval: int = 5) -> str:
        """Poll for token until user authorizes or timeout. Returns access_token."""
        app_key = self._account.dropbox_app_key
        app_secret = self._account.get_decrypted_dropbox_app_secret()
        current_interval = interval

        for i in range(60):
            time.sleep(current_interval)
            resp = httpx.post(
                TOKEN_URL,
                data={
                    "client_id": app_key,
                    "client_secret": app_secret,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if "access_token" in data:
                token_data = _TokenData(
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token", ""),
                    expires_at=datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 14400)),
                )
                self._save_token(token_data)
                return token_data.access_token

            error = data.get("error", "")
            if error in ("access_denied", "expired_token"):
                raise RuntimeError("授权被拒绝或已过期，请重试")
            if error == "slow_down":
                current_interval += 5

        raise RuntimeError("授权超时，请重试")


class DropboxProvider:
    """Read/write files on Dropbox using the official Python SDK."""

    def __init__(self, access_token: str, app_key: str, app_secret: str, root_path: str = "/") -> None:
        import dropbox

        self._dbx = dropbox.Dropbox(
            oauth2_access_token=access_token,
            app_key=app_key,
            app_secret=app_secret,
        )
        self._root = root_path.strip("/")

    def _full_path(self, path: str) -> str:
        clean = path.strip("/")
        parts = [p for p in (self._root, clean) if p]
        return "/" + "/".join(parts)

    def _parse_entries(self, entries: list[Any], base_path: str) -> list[CloudFileInfo]:
        import dropbox

        results: list[CloudFileInfo] = []
        for entry in entries:
            is_folder = isinstance(entry, dropbox.files.FolderMetadata)
            name = entry.name
            rel = f"{base_path.strip('/')}/{name}".lstrip("/")
            if is_folder:
                results.append(CloudFileInfo(name=name, path=rel, is_dir=True, size=0, modified_at=0.0))
            else:
                size = getattr(entry, "size", 0) or 0
                modified = entry.server_modified.timestamp() if hasattr(entry, "server_modified") else 0.0
                results.append(CloudFileInfo(name=name, path=rel, is_dir=False, size=size, modified_at=modified))
        return results

    # ── Protocol implementation ────────────────────────────────

    def list_directory(self, path: str) -> list[CloudFileInfo]:
        import dropbox

        dbx_path = self._full_path(path)
        results: list[CloudFileInfo] = []
        try:
            res = self._dbx.files_list_folder(dbx_path)
            results.extend(self._parse_entries(res.entries, path))
            while res.has_more:
                res = self._dbx.files_list_folder_continue(res.cursor)
                results.extend(self._parse_entries(res.entries, path))
        except dropbox.exceptions.ApiError as e:
            if e.error.is_path() and e.error.get_path().is_not_found():
                return []
            raise
        results.sort(key=lambda x: x.name.lower())
        return results

    def read_file(self, path: str) -> bytes:
        dbx_path = self._full_path(path)
        _metadata, res = self._dbx.files_download(dbx_path)
        return res.content  # type: ignore[no-any-return]

    def write_file(self, path: str, content: bytes) -> None:
        import dropbox

        parent = "/".join(path.strip("/").split("/")[:-1])
        if parent:
            self.mkdir(parent)
        dbx_path = self._full_path(path)
        self._dbx.files_upload(content, dbx_path, mode=dropbox.files.WriteMode.overwrite)

    def mkdir(self, path: str) -> None:
        import dropbox

        parts = path.strip("/").split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else f"/{part}"
            try:
                self._dbx.files_get_metadata(current)
            except dropbox.exceptions.ApiError:
                try:
                    self._dbx.files_create_folder_v2(current)
                except dropbox.exceptions.ApiError as e:
                    # 只忽略 "路径已存在" 错误，其他错误向上传播
                    if e.error.is_path() and e.error.get_path().is_conflict():
                        pass
                    else:
                        raise

    def exists(self, path: str) -> bool:
        import dropbox

        dbx_path = self._full_path(path)
        try:
            self._dbx.files_get_metadata(dbx_path)
            return True
        except dropbox.exceptions.ApiError as e:
            if e.error.is_path() and e.error.get_path().is_not_found():
                return False
            raise

    def is_dir(self, path: str) -> bool:
        import dropbox

        dbx_path = self._full_path(path)
        try:
            meta = self._dbx.files_get_metadata(dbx_path)
            return isinstance(meta, dropbox.files.FolderMetadata)
        except dropbox.exceptions.ApiError:
            return False

    def delete_file(self, path: str) -> None:
        import dropbox

        dbx_path = self._full_path(path)
        try:
            self._dbx.files_delete_v2(dbx_path)
        except dropbox.exceptions.ApiError as e:
            if e.error.is_path_lookup() and e.error.get_path_lookup().is_not_found():
                return
            raise

    def get_file_info(self, path: str) -> CloudFileInfo | None:
        import dropbox

        dbx_path = self._full_path(path)
        try:
            meta = self._dbx.files_get_metadata(dbx_path)
        except dropbox.exceptions.ApiError:
            return None
        name = meta.name
        rel = path.strip("/")
        if isinstance(meta, dropbox.files.FolderMetadata):
            return CloudFileInfo(name=name, path=rel, is_dir=True, size=0, modified_at=0.0)
        return CloudFileInfo(
            name=name,
            path=rel,
            is_dir=False,
            size=getattr(meta, "size", 0) or 0,
            modified_at=meta.server_modified.timestamp() if hasattr(meta, "server_modified") else 0.0,
        )

    def walk(self, path: str) -> Iterator[tuple[str, list[str], list[CloudFileInfo]]]:
        children = self.list_directory(path)
        subdirs = [c.name for c in children if c.is_dir]
        files = [c for c in children if not c.is_dir]
        yield (path, subdirs, files)
        for subdir in subdirs:
            sub_path = f"{path.rstrip('/')}/{subdir}"
            yield from self.walk(sub_path)
