"""API endpoints."""

import logging
from typing import Any, cast

import httpx

from apps.automation.utils.logging_mixins.common import sanitize_url
from apps.core.exceptions import NetworkError

from .court_document_api_exceptions import ApiResponseError, CourtApiError, TokenExpiredError

logger = logging.getLogger("apps.automation")


class CourtDocumentHttpClient:
    def __init__(self, *, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds

    def post_json(self, *, url: str, headers: dict[str, str], json_data: dict[str, Any]) -> dict[str, Any]:
        safe_url = sanitize_url(url)
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(url, headers=headers, json=json_data)

            if response.status_code == 401:
                raise TokenExpiredError(message="Token 已过期或无效", errors={"status_code": 401})

            if response.status_code >= 400:
                raise ApiResponseError(
                    message=f"HTTP 错误: {response.status_code}", response_code=response.status_code, errors={}
                )

            return cast(dict[str, Any], response.json())

        except httpx.TimeoutException as e:
            raise NetworkError(
                message=f"请求超时: {e!s}", errors={"url": safe_url, "timeout": self.timeout_seconds}
            ) from e

        except httpx.RequestError as e:
            raise NetworkError(message=f"网络错误: {e!s}", errors={"url": safe_url}) from e

        except (TokenExpiredError, ApiResponseError):
            raise

        except Exception as e:
            logger.error(f"HTTP client 未知错误: url={safe_url}, error={e!s}")
            raise CourtApiError(message=f"API 调用失败: {e!s}", errors={"url": safe_url}) from e

    def get_bytes(self, *, url: str, timeout_seconds: float | None = None) -> bytes:
        safe_url = sanitize_url(url)
        try:
            with httpx.Client(timeout=timeout_seconds or self.timeout_seconds) as client:
                response = client.get(url)

            if response.status_code >= 400:
                raise ApiResponseError(
                    message=f"HTTP 错误: {response.status_code}", response_code=response.status_code, errors={}
                )

            return response.content

        except httpx.TimeoutException as e:
            raise NetworkError(message=f"请求超时: {e!s}", errors={"url": safe_url, "timeout": timeout_seconds}) from e

        except httpx.RequestError as e:
            raise NetworkError(message=f"网络错误: {e!s}", errors={"url": safe_url}) from e

        except ApiResponseError:
            raise

        except Exception as e:
            logger.error(f"HTTP client 未知错误: url={safe_url}, error={e!s}")
            raise CourtApiError(message=f"API 调用失败: {e!s}", errors={"url": safe_url}) from e
