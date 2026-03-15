from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterable
from typing import Any

from .types import WeikeSession

logger = logging.getLogger(__name__)


class WeikeTransportMixin:
    DEFAULT_RETRYABLE_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

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

    def _request_get_with_retry(
        self,
        *,
        session: WeikeSession,
        url: str,
        timeout: int,
        max_attempts: int = 3,
        retry_statuses: Iterable[int] | None = None,
        backoff_seconds: float = 0.8,
    ) -> Any:
        return self._request_with_retry(
            request_fn=lambda: self._request_get(session=session, url=url, timeout=timeout),
            method="GET",
            url=url,
            max_attempts=max_attempts,
            retry_statuses=retry_statuses,
            backoff_seconds=backoff_seconds,
        )

    def _request_post_json_with_retry(
        self,
        *,
        session: WeikeSession,
        url: str,
        payload: dict[str, Any],
        timeout: int,
        max_attempts: int = 3,
        retry_statuses: Iterable[int] | None = None,
        backoff_seconds: float = 0.8,
    ) -> Any:
        return self._request_with_retry(
            request_fn=lambda: self._request_post_json(session=session, url=url, payload=payload, timeout=timeout),
            method="POST",
            url=url,
            max_attempts=max_attempts,
            retry_statuses=retry_statuses,
            backoff_seconds=backoff_seconds,
        )

    def _request_with_retry(
        self,
        *,
        request_fn: Callable[[], Any],
        method: str,
        url: str,
        max_attempts: int,
        retry_statuses: Iterable[int] | None,
        backoff_seconds: float,
    ) -> Any:
        attempts = max(1, int(max_attempts))
        statuses = {int(s) for s in (retry_statuses or self.DEFAULT_RETRYABLE_STATUSES)}
        last_response: Any | None = None
        last_exception: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = request_fn()
                last_response = response
            except Exception as exc:
                last_exception = exc
                if attempt >= attempts:
                    raise
                logger.warning(
                    "wk请求异常，准备重试",
                    extra={
                        "method": method,
                        "url": url,
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "error": str(exc),
                    },
                )
                self._sleep_for_retry(attempt=attempt, base_seconds=backoff_seconds)
                continue

            status = self._response_status(response)
            if status in statuses and attempt < attempts:
                logger.warning(
                    "wk请求返回可重试状态码，准备重试",
                    extra={
                        "method": method,
                        "url": url,
                        "status": status,
                        "attempt": attempt,
                        "max_attempts": attempts,
                    },
                )
                self._sleep_for_retry(attempt=attempt, base_seconds=backoff_seconds)
                continue

            return response

        if last_response is not None:
            return last_response
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("wk请求重试失败")

    @staticmethod
    def _sleep_for_retry(*, attempt: int, base_seconds: float) -> None:
        if base_seconds <= 0:
            return
        time.sleep(base_seconds * max(1, attempt))

    @staticmethod
    def _response_status(response: Any) -> int:
        status_code = getattr(response, "status_code", None)
        if status_code is not None:
            return int(status_code)
        status = getattr(response, "status", None)
        if status is not None:
            return int(status)
        return 0

    @classmethod
    def _response_json(cls, response: Any) -> dict[str, Any]:
        try:
            data = response.json()
        except Exception:
            data = None

        normalized = cls._coerce_json_dict(data)
        if normalized is not None:
            return normalized

        body = cls._response_body(response)
        if not body:
            return {}
        decoded = cls._decode_response_body(body)
        return cls._parse_json_from_text(decoded)

    @staticmethod
    def _response_headers(response: Any) -> dict[str, str]:
        headers = getattr(response, "headers", None)
        if headers is None:
            return {}
        return dict(headers)

    @staticmethod
    def _coerce_json_dict(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    @staticmethod
    def _decode_response_body(body: bytes) -> str:
        if not body:
            return ""
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return body.decode(encoding)
            except UnicodeDecodeError:
                continue
        return body.decode("latin-1", errors="ignore")

    @classmethod
    def _parse_json_from_text(cls, text: str) -> dict[str, Any]:
        candidate = (text or "").strip()
        if not candidate:
            return {}

        direct = cls._coerce_json_dict(candidate)
        if direct is not None:
            return direct

        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            return {}

        clipped = candidate[start : end + 1]
        repaired = cls._coerce_json_dict(clipped)
        if repaired is not None:
            return repaired
        return {}

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
