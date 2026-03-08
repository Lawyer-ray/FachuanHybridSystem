"""HTTP 客户端 - 封装 httpx，自动处理 JWT 认证和 token 刷新"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from . import config


class FachuanClient:
    def __init__(self) -> None:
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._expires_at: float = 0.0
        self._lock = threading.Lock()
        self._http = httpx.Client(base_url=config.BASE_URL, timeout=30)

    def _obtain_token(self) -> None:
        resp = self._http.post(
            "/token/pair",
            json={"username": config.USERNAME, "password": config.PASSWORD},
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access"]
        self._refresh_token = data["refresh"]
        self._expires_at = time.time() + 270  # 提前 30s 刷新

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
