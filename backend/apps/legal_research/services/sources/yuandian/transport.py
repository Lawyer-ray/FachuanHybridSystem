"""元典 REST 传输层：``X-API-Key`` 鉴权、超时、429 退避、响应信封校验。

URL 形如 ``https://open.chineselaw.com/open/<routeKey>``；响应恒为
``{status, code, message, data}``，``code == 200`` 才算成功（实测错误码：
401 key 缺失/无效 · 403 内部鉴权 · 404 接口不存在 · 422 参数校验 · 429 限流 · 5xx 服务/上游）。
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from .config import key_label
from .types import YuandianSession

logger = logging.getLogger(__name__)

#: 实测关键词检索首次 6.76s（疑冷启动）、详情 0.83s，超时按 ≥60s 设。
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 6.0
RATE_LIMIT_STATUS = 429
SUCCESS_CODE = "200"
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class YuandianRequestError(RuntimeError):
    """元典接口调用失败：网络异常、HTTP 错误码、业务 ``code`` 非 200、响应结构不符。"""


class YuandianTransport:
    """同步 httpx 封装。每个会话持有一个 :class:`httpx.Client`（``close()`` 时释放）。"""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        http_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = float(timeout_seconds)
        self._max_attempts = max(1, int(max_attempts))
        self._http_transport = http_transport

    def open_client(self) -> httpx.Client:
        timeout = httpx.Timeout(self._timeout_seconds, connect=DEFAULT_CONNECT_TIMEOUT_SECONDS)
        return httpx.Client(transport=self._http_transport, timeout=timeout, follow_redirects=True)

    def request_json(
        self,
        *,
        session: YuandianSession,
        route_key: str,
        method: str = "POST",
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """调用一个元典接口并返回校验过的响应信封。

        429/5xx 与网络异常按 ``max_attempts`` 退避重试，且**每次重试换下一把 key**
        （``session.next_api_key``）——限流是按 key 计还是按 IP 计都吃得下。
        """
        url = f"{session.base_url.rstrip('/')}/open/{route_key.strip('/')}"
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            api_key = session.next_api_key()
            try:
                with session.key_slot(api_key):
                    response = self._send(
                        session=session,
                        url=url,
                        method=method,
                        params=params,
                        json_body=json_body,
                        api_key=api_key,
                    )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self._max_attempts:
                    break
                logger.warning(
                    "元典接口请求异常，准备重试",
                    extra={
                        "route_key": route_key,
                        "method": method,
                        "attempt": attempt,
                        "max_attempts": self._max_attempts,
                        "key": key_label(api_key),
                        "error_type": type(exc).__name__,
                    },
                )
                _sleep_for_retry(attempt=attempt)
                continue

            status = response.status_code
            if status in RETRYABLE_STATUSES and attempt < self._max_attempts:
                logger.warning(
                    "元典接口返回可重试状态码，准备重试",
                    extra={
                        "route_key": route_key,
                        "method": method,
                        "status": status,
                        "attempt": attempt,
                        "max_attempts": self._max_attempts,
                        "key": key_label(api_key),
                    },
                )
                _sleep_for_retry(attempt=attempt, retry_after=_retry_after_seconds(response))
                continue

            return _decode_envelope(response=response, route_key=route_key, api_key=api_key)

        raise YuandianRequestError(f"元典接口 {route_key} 请求失败：{type(last_error).__name__}") from last_error

    def _send(
        self,
        *,
        session: YuandianSession,
        url: str,
        method: str,
        params: dict[str, str] | None,
        json_body: dict[str, Any] | None,
        api_key: str,
    ) -> httpx.Response:
        client = session.http_client
        if client is None:
            client = self.open_client()
            session.http_client = client
        headers = {"X-API-Key": api_key, "Accept": "application/json"}
        return client.request(method.upper(), url, params=params, json=json_body, headers=headers)


def _decode_envelope(*, response: httpx.Response, route_key: str, api_key: str) -> dict[str, Any]:
    status = response.status_code
    if status >= 400:
        raise YuandianRequestError(_redact(f"元典接口 {route_key} 返回 HTTP {status}{_body_hint(response)}", api_key))

    try:
        payload = response.json()
    except ValueError as exc:
        raise YuandianRequestError(f"元典接口 {route_key} 返回非 JSON 响应") from exc
    if not isinstance(payload, dict):
        raise YuandianRequestError(f"元典接口 {route_key} 响应结构不是对象: {type(payload).__name__}")

    code = payload.get("code")
    if code is not None and str(code).strip() != SUCCESS_CODE:
        message = _redact(str(payload.get("message") or "").strip(), api_key)
        raise YuandianRequestError(f"元典接口 {route_key} 返回错误 code={code} message={message}")
    return payload


def _body_hint(response: httpx.Response) -> str:
    try:
        text = (response.text or "").strip()
    except (httpx.HTTPError, ValueError, AttributeError):
        return ""
    if not text:
        return ""
    return f" body={text[:200]}"


def _redact(text: str, api_key: str) -> str:
    """上游若在错误体里回显了我们的 key，一律换成进程内别名。"""
    secret = (api_key or "").strip()
    if not secret or secret not in text:
        return text
    return text.replace(secret, key_label(secret))


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = (response.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return max(0.0, min(value, BACKOFF_MAX_SECONDS))


def _sleep_for_retry(*, attempt: int, retry_after: float | None = None) -> None:
    base = float(BACKOFF_BASE_SECONDS)
    delay = min(base * (2 ** max(0, int(attempt) - 1)), max(base, BACKOFF_MAX_SECONDS))
    if retry_after is not None:
        delay = max(delay, retry_after)
    time.sleep(delay + random.uniform(0.0, delay * 0.25))
