"""OneDrive (Microsoft Graph API) storage provider."""

from __future__ import annotations

import io
import logging
import time
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .protocols import CloudFileInfo

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
DEVICE_CODE_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/devicecode"
SCOPES = "Files.ReadWrite offline_access"


@dataclass
class _TokenData:
    access_token: str
    refresh_token: str
    expires_at: datetime


class OAuthTokenManager:
    """Manages OneDrive OAuth2 token lifecycle (device code flow + auto-refresh)."""

    def __init__(self, account: Any) -> None:
        self._account = account

    def _tenant_id(self) -> str:
        return getattr(self._account, "onedrive_tenant_id", None) or "consumers"

    def _client_id(self) -> str:
        return getattr(self._account, "onedrive_client_id", "")

    def _token_url(self) -> str:
        return TOKEN_URL_TEMPLATE.format(tenant_id=self._tenant_id())

    def _device_code_url(self) -> str:
        return DEVICE_CODE_URL_TEMPLATE.format(tenant_id=self._tenant_id())

    def get_valid_token(self) -> str:
        """Return a valid access_token, refreshing if necessary."""
        token = self._account.get_decrypted_onedrive_access_token()
        expires_at = getattr(self._account, "onedrive_token_expires_at", None)

        if token and expires_at and expires_at > datetime.now(UTC) + timedelta(minutes=5):
            return str(token)

        refresh_token = self._account.get_decrypted_onedrive_refresh_token()
        if refresh_token:
            try:
                return self._refresh_token(refresh_token)
            except Exception as e:
                raise RuntimeError(
                    "OneDrive 授权已过期（refresh_token 无效），请在 Admin 后台 -> 云存储账号 "
                    "中重新点击「获取授权」按钮完成授权。"
                ) from e

        raise RuntimeError(
            "OneDrive 未授权。请在 Admin 后台 -> 云存储账号 中点击「获取授权」按钮完成授权。"
        )

    def _refresh_token(self, refresh_token: str) -> str:
        resp = httpx.post(
            self._token_url(),
            data={
                "client_id": self._client_id(),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "scope": SCOPES,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        token_data = _TokenData(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 3600)),
        )
        self._save_token(token_data)
        return token_data.access_token

    def _save_token(self, token_data: _TokenData) -> None:
        from apps.core.security.secret_codec import SecretCodec

        codec = SecretCodec()
        self._account.onedrive_access_token = codec.encrypt(token_data.access_token)
        self._account.onedrive_refresh_token = codec.encrypt(token_data.refresh_token)
        self._account.onedrive_token_expires_at = token_data.expires_at
        self._account.save(
            update_fields=["onedrive_access_token", "onedrive_refresh_token", "onedrive_token_expires_at", "updated_at"]
        )

    @staticmethod
    def start_device_code_flow(account: Any) -> dict[str, Any]:
        """Initiate device code flow. Returns dict with user_code, verification_uri, device_code."""
        tenant_id = getattr(account, "onedrive_tenant_id", None) or "consumers"
        client_id = getattr(account, "onedrive_client_id", "")
        if not client_id:
            raise ValueError("请先配置 Azure AD Client ID")

        resp = httpx.post(
            DEVICE_CODE_URL_TEMPLATE.format(tenant_id=tenant_id),
            data={
                "client_id": client_id,
                "scope": SCOPES,
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

    def complete_device_code_flow(self, device_code: str) -> str:
        """Poll token endpoint until user completes authorization. Returns access_token."""
        import time as _time

        tenant_id = self._tenant_id()
        client_id = self._client_id()
        max_attempts = 60  # ~5 minutes with 5s interval

        for _ in range(max_attempts):
            _time.sleep(5)
            resp = httpx.post(
                TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id),
                data={
                    "client_id": client_id,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                },
                timeout=30,
            )
            data = resp.json()

            if "access_token" in data:
                token_data = _TokenData(
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token", ""),
                    expires_at=datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 3600)),
                )
                self._save_token(token_data)
                return token_data.access_token

            error = data.get("error", "")
            if error == "authorization_pending":
                continue
            if error == "authorization_declined":
                raise RuntimeError("用户拒绝了授权请求")
            if error == "expired_token":
                raise RuntimeError("设备码已过期，请重新发起授权")
            if error == "slow_down":
                _time.sleep(5)
                continue

            raise RuntimeError(f"授权失败: {error} - {data.get('error_description', '')}")

        raise RuntimeError("授权超时，请重试")


class OneDriveProvider:
    """Read/write files on OneDrive via Microsoft Graph API."""

    def __init__(self, access_token: str, root_path: str = "/") -> None:
        self._token = access_token
        self._root = root_path.strip("/")
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._client = httpx.Client(timeout=60, headers=self._headers)

    def _item_path(self, path: str) -> str:
        """Build Graph API item path from relative path."""
        clean = path.strip("/")
        parts = [p for p in (self._root, clean) if p]
        return "/".join(parts)

    def _item_url(self, path: str) -> str:
        item_path = urllib.parse.quote(self._item_path(path), safe="/:")
        return f"{GRAPH_BASE}/me/drive/root:/{item_path}"

    def _children_url(self, path: str) -> str:
        item_path = urllib.parse.quote(self._item_path(path), safe="/:")
        return f"{GRAPH_BASE}/me/drive/root:/{item_path}:/children"

    # ── Protocol implementation ────────────────────────────────

    def list_directory(self, path: str) -> list[CloudFileInfo]:
        url = self._children_url(path) if path.strip("/") else f"{GRAPH_BASE}/me/drive/root/children"
        results: list[CloudFileInfo] = []
        next_url: str | None = url

        while next_url:
            resp = self._client.get(next_url, headers=self._headers)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("value", []):
                name = item.get("name", "")
                is_folder = "folder" in item
                size = item.get("size", 0) if not is_folder else 0
                modified_str = item.get("lastModifiedDateTime", "")
                try:
                    modified_at = datetime.fromisoformat(modified_str.replace("Z", "+00:00")).timestamp()
                except (ValueError, AttributeError):
                    modified_at = 0.0

                rel_path = f"{path.strip('/')}/{name}" if path.strip("/") else name
                results.append(
                    CloudFileInfo(
                        name=name,
                        path=rel_path,
                        is_dir=is_folder,
                        size=size,
                        modified_at=modified_at,
                    )
                )

            next_url = data.get("@odata.nextLink")

        results.sort(key=lambda x: x.name.lower())
        return results

    def read_file(self, path: str) -> bytes:
        url = f"{self._item_url(path)}:/content"
        resp = self._client.get(url, headers=self._headers, follow_redirects=True)
        resp.raise_for_status()
        return resp.content

    def write_file(self, path: str, content: bytes) -> None:
        # Ensure parent directory exists
        parts = path.strip("/").split("/")
        if len(parts) > 1:
            parent = "/".join(parts[:-1])
            self.mkdir(parent)

        url = f"{self._item_url(path)}:/content"
        resp = self._client.put(url, content=content, headers=self._headers)
        resp.raise_for_status()

    def mkdir(self, path: str) -> None:
        if self.exists(path):
            return
        parts = path.strip("/").split("/")
        if len(parts) > 1:
            parent = "/".join(parts[:-1])
            self.mkdir(parent)

        parent_url = (
            self._children_url("/".join(parts[:-1])) if len(parts) > 1 else f"{GRAPH_BASE}/me/drive/root/children"
        )
        folder_name = parts[-1]
        resp = self._client.post(
            parent_url,
            headers={**self._headers, "Content-Type": "application/json"},
            json={"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
        )
        # 409 = already exists, that's fine
        if resp.status_code not in (201, 409):
            logger.warning("mkdir %s returned %d: %s", path, resp.status_code, resp.text[:200])

    def exists(self, path: str) -> bool:
        url = self._item_url(path)
        resp = self._client.get(url, headers=self._headers)
        return resp.status_code == 200

    def is_dir(self, path: str) -> bool:
        url = self._item_url(path)
        resp = self._client.get(url, headers=self._headers)
        if resp.status_code != 200:
            return False
        return "folder" in resp.json()

    def delete_file(self, path: str) -> None:
        url = self._item_url(path)
        resp = self._client.delete(url, headers=self._headers)
        if resp.status_code not in (200, 204, 404):
            logger.warning("DELETE %s returned %d", path, resp.status_code)

    def get_file_info(self, path: str) -> CloudFileInfo | None:
        url = self._item_url(path)
        resp = self._client.get(url, headers=self._headers)
        if resp.status_code != 200:
            return None

        item = resp.json()
        name = item.get("name", "")
        is_folder = "folder" in item
        size = item.get("size", 0) if not is_folder else 0
        modified_str = item.get("lastModifiedDateTime", "")
        try:
            modified_at = datetime.fromisoformat(modified_str.replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            modified_at = 0.0

        return CloudFileInfo(
            name=name,
            path=path.strip("/"),
            is_dir=is_folder,
            size=size,
            modified_at=modified_at,
        )

    def walk(self, path: str) -> Iterator[tuple[str, list[str], list[CloudFileInfo]]]:
        children = self.list_directory(path)
        subdirs = [c.name for c in children if c.is_dir]
        files = [c for c in children if not c.is_dir]
        yield (path, subdirs, files)
        for subdir in subdirs:
            sub_path = f"{path.rstrip('/')}/{subdir}"
            yield from self.walk(sub_path)
