"""HTTP 客户端 - 封装 httpx，自动处理 JWT 认证和 token 刷新"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

import httpx

from . import config

logger = logging.getLogger(__name__)

_MAX_OBTAIN_RETRIES = 3
_RETRY_BACKOFF = (1.0, 3.0, 5.0)

class FachuanClient:
    def __init__(self) -> None:
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._expires_at: float = 0.0
        self._lock = threading.Lock()
        # trust_env=False: 绕过系统代理，直连后端（避免 macOS 代理工具对 localhost 返回 502）
        self._http = httpx.Client(base_url=config.BASE_URL, timeout=60, trust_env=False)

    def _obtain_token(self) -> None:
        last_exc: Exception | None = None
        for attempt in range(_MAX_OBTAIN_RETRIES):
            try:
                resp = self._http.post(
                    "/token/pair",
                    json={"username": config.USERNAME, "password": config.PASSWORD},
                )
                resp.raise_for_status()
                data = resp.json()
                self._access_token = data["access"]
                self._refresh_token = data["refresh"]
                self._expires_at = time.time() + 270  # 提前 30s 刷新
                return
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                if status < 500:
                    raise  # 4xx 客户端错误直接抛
                logger.warning("token/pair 返回 %d，第 %d 次重试", status, attempt + 1)
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                logger.warning("token/pair 连接失败: %s，第 %d 次重试", exc, attempt + 1)
            if attempt < _MAX_OBTAIN_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF[attempt])
        raise last_exc  # type: ignore[misc]

    def _refresh(self) -> None:
        try:
            resp = self._http.post("/token/refresh", json={"refresh": self._refresh_token})
            resp.raise_for_status()
            self._access_token = resp.json()["access"]
            self._expires_at = time.time() + 270
        except Exception:
            self._obtain_token()

    def _ensure_token(self) -> None:
        with self._lock:
            if not self._access_token:
                self._obtain_token()
            elif time.time() >= self._expires_at:
                self._refresh()

    def _headers(self) -> dict[str, str]:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def get(self, path: str, **kwargs: Any) -> Any:
        resp = self._http.get(path, headers=self._headers(), **kwargs)
        return self._handle(resp)

    def post(self, path: str, **kwargs: Any) -> Any:
        resp = self._http.post(path, headers=self._headers(), **kwargs)
        return self._handle(resp)

    def put(self, path: str, **kwargs: Any) -> Any:
        resp = self._http.put(path, headers=self._headers(), **kwargs)
        return self._handle(resp)

    def delete(self, path: str, **kwargs: Any) -> Any:
        resp = self._http.delete(path, headers=self._headers(), **kwargs)
        return self._handle(resp)

    def upload(
        self,
        path: str,
        files: dict[str, tuple[str, bytes, str]],
        data: dict[str, Any] | None = None,
    ) -> Any:
        """multipart/form-data 上传。files: {field: (filename, content, content_type)}"""
        resp = self._http.post(path, headers=self._headers(), files=files, data=data or {})
        return self._handle(resp)

    def download(self, path: str, **kwargs: Any) -> tuple[bytes, str, str]:
        """下载二进制内容，返回 (content_bytes, filename, content_type)。"""
        resp = self._http.get(path, headers=self._headers(), **kwargs)
        if not resp.is_success:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
        content_type = resp.headers.get("content-type", "application/octet-stream")
        disposition = resp.headers.get("content-disposition", "")
        filename = "download"
        if disposition:
            # 尝试解析 filename*=UTF-8''... 或 filename="..."
            m = re.search(r"filename\*=UTF-8''([^;]+)", disposition)
            if m:
                from urllib.parse import unquote
                filename = unquote(m.group(1))
            else:
                m2 = re.search(r'filename="?([^";]+)"?', disposition)
                if m2:
                    filename = m2.group(1).strip()
        return resp.content, filename, content_type

    @staticmethod
    def _handle(resp: httpx.Response) -> Any:
        if not resp.is_success:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
        if resp.status_code == 204:
            return None
        return resp.json()

# 全局单例
client = FachuanClient()
