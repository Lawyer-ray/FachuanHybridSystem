from __future__ import annotations

from typing import Any

from .types import WeikeSession


class WeikeTransportMixin:
    def _request_get(self, *, session: WeikeSession, url: str, timeout: int) -> Any:
        if session.http_client is not None:
            return session.http_client.get(url, timeout=max(1.0, timeout / 1000))

        self._ensure_playwright_session(session)
        if session.page is None:
            raise RuntimeError("Playwright请求上下文未就绪")
        return session.page.request.get(url, timeout=timeout)

    def _request_post_json(self, *, session: WeikeSession, url: str, payload: dict[str, Any], timeout: int) -> Any:
        if session.http_client is not None:
            return session.http_client.post(url, json=payload, timeout=max(1.0, timeout / 1000))

        self._ensure_playwright_session(session)
        if session.page is None:
            raise RuntimeError("Playwright请求上下文未就绪")
        return session.page.request.post(url, data=payload, timeout=timeout)

    @staticmethod
    def _response_status(response: Any) -> int:
        status_code = getattr(response, "status_code", None)
        if status_code is not None:
            return int(status_code)
        status = getattr(response, "status", None)
        if status is not None:
            return int(status)
        return 0

    @staticmethod
    def _response_json(response: Any) -> dict[str, Any]:
        data = response.json()
        if isinstance(data, dict):
            return data
        return {}

    @staticmethod
    def _response_headers(response: Any) -> dict[str, str]:
        headers = getattr(response, "headers", None)
        if headers is None:
            return {}
        return dict(headers)

    @staticmethod
    def _response_body(response: Any) -> bytes:
        content = getattr(response, "content", None)
        if isinstance(content, (bytes, bytearray)):
            return bytes(content)
        body_fn = getattr(response, "body", None)
        if callable(body_fn):
            return body_fn()
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text.encode("utf-8")
        text_fn = getattr(response, "text", None)
        if callable(text_fn):
            try:
                return str(text_fn()).encode("utf-8")
            except Exception:
                return b""
        return b""
