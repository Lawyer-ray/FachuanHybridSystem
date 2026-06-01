from __future__ import annotations

from typing import Any

from .constants import _BASE

class HttpTransportMixin:
    async def _get(self: Any, path: str, **params: Any) -> Any:
        r = await self._client.get(f"{_BASE}{path}", params=params or None)
        r.raise_for_status()
        body = r.json()
        if body.get("code") != 200:
            raise RuntimeError(f"GET {path} 失败: {body.get('message')}")
        return body.get("data")

    async def _post(self: Any, path: str, payload: dict[str, Any]) -> Any:
        r = await self._client.post(f"{_BASE}{path}", json=payload)
        if r.status_code >= 400:
            try:
                err_body = r.json()
            except Exception:
                err_body = r.text
            raise RuntimeError(f"POST {path} 失败 [{r.status_code}]: {err_body}")
        body = r.json()
        if body.get("code") != 200:
            raise RuntimeError(f"POST {path} 失败: {body.get('message')} | {payload}")
        return body.get("data")

    async def _patch(self: Any, path: str, payload: dict[str, Any]) -> Any:
        r = await self._client.patch(f"{_BASE}{path}", json=payload)
        r.raise_for_status()
        body = r.json()
        if body.get("code") != 200:
            raise RuntimeError(f"PATCH {path} 失败: {body.get('message')}")
        return body.get("data")
