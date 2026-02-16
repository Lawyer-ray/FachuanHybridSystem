"""Module for moonshot files."""

from __future__ import annotations

import logging
from typing import Any, Protocol, cast

import httpx

from apps.core.httpx_clients import get_async_http_client, get_sync_http_client
from apps.core.llm.exceptions import LLMAPIError
from apps.core.path import Path

logger = logging.getLogger("apps.core.llm.backends.moonshot")


class _MoonshotBackendDeps(Protocol):
    base_url: str
    timeout: float

    def _get_headers(self) -> dict[str, str]: ...

    def _handle_http_error(self, error: httpx.HTTPStatusError, action: str) -> None: ...

    def _handle_connect_error(self, error: httpx.ConnectError) -> None: ...

    def _handle_timeout_error(self, error: httpx.TimeoutException, timeout: float) -> None: ...


class MoonshotFilesClient:
    def __init__(self, backend: _MoonshotBackendDeps) -> None:
        self._backend = backend

    def upload_file(self, file_path: str) -> dict[str, Any]:
        url = f"{self._backend.base_url}/files"
        p = Path(file_path)

        try:
            with p.open("rb") as f:
                files = {"file": (p.name, f)}
                client = get_sync_http_client()
                resp = client.post(
                    url,
                    headers=self._backend._get_headers(),
                    files=files,
                    timeout=self._backend.timeout,
                )
                resp.raise_for_status()
                return cast(dict[str, Any], resp.json())

        except httpx.HTTPStatusError as e:
            self._backend._handle_http_error(e, "upload_file")
        except httpx.ConnectError as e:
            self._backend._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._backend._handle_timeout_error(e, self._backend.timeout)
        except FileNotFoundError:
            logger.warning("Moonshot 上传文件不存在", extra={"file_path": file_path})
            raise LLMAPIError(message=f"文件不存在: {file_path}", errors={"file_path": file_path}) from None
        except Exception as e:
            logger.warning("Moonshot 上传文件异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(message=f"上传文件时发生错误: {e!s}", errors={"detail": str(e)}) from e

        return {}

    async def aupload_file(self, file_path: str) -> dict[str, Any]:
        url = f"{self._backend.base_url}/files"
        p = Path(file_path)

        try:
            with p.open("rb") as f:
                files = {"file": (p.name, f)}
                client = get_async_http_client()
                resp = await client.post(
                    url,
                    headers=self._backend._get_headers(),
                    files=files,
                    timeout=self._backend.timeout,
                )
                resp.raise_for_status()
                return cast(dict[str, Any], resp.json())

        except httpx.HTTPStatusError as e:
            self._backend._handle_http_error(e, "aupload_file")
        except httpx.ConnectError as e:
            self._backend._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._backend._handle_timeout_error(e, self._backend.timeout)
        except FileNotFoundError:
            logger.warning("Moonshot 上传文件不存在", extra={"file_path": file_path})
            raise LLMAPIError(message=f"文件不存在: {file_path}", errors={"file_path": file_path}) from None
        except Exception as e:
            logger.warning("Moonshot 异步上传文件异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(message=f"上传文件时发生错误: {e!s}", errors={"detail": str(e)}) from e

        return {}

    def list_files(self) -> dict[str, Any]:
        url = f"{self._backend.base_url}/files"

        try:
            client = get_sync_http_client()
            resp = client.get(url, headers=self._backend._get_headers(), timeout=self._backend.timeout)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

        except httpx.HTTPStatusError as e:
            self._backend._handle_http_error(e, "list_files")
        except httpx.ConnectError as e:
            self._backend._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._backend._handle_timeout_error(e, self._backend.timeout)
        except Exception as e:
            logger.warning("Moonshot 列出文件异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(message=f"列出文件时发生错误: {e!s}", errors={"detail": str(e)}) from e

        return {}

    async def alist_files(self) -> dict[str, Any]:
        url = f"{self._backend.base_url}/files"

        try:
            client = get_async_http_client()
            resp = await client.get(url, headers=self._backend._get_headers(), timeout=self._backend.timeout)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

        except httpx.HTTPStatusError as e:
            self._backend._handle_http_error(e, "alist_files")
        except httpx.ConnectError as e:
            self._backend._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._backend._handle_timeout_error(e, self._backend.timeout)
        except Exception as e:
            logger.warning("Moonshot 异步列出文件异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(message=f"列出文件时发生错误: {e!s}", errors={"detail": str(e)}) from e

        return {}

    def retrieve_file(self, file_id: str) -> dict[str, Any]:
        url = f"{self._backend.base_url}/files/{file_id}"

        try:
            client = get_sync_http_client()
            resp = client.get(url, headers=self._backend._get_headers(), timeout=self._backend.timeout)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

        except httpx.HTTPStatusError as e:
            self._backend._handle_http_error(e, "retrieve_file")
        except httpx.ConnectError as e:
            self._backend._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._backend._handle_timeout_error(e, self._backend.timeout)
        except Exception as e:
            logger.warning(
                "Moonshot 检索文件异常",
                extra={"error": str(e), "error_type": type(e).__name__, "file_id": file_id},
            )
            raise LLMAPIError(
                message=f"检索文件时发生错误: {e!s}", errors={"detail": str(e), "file_id": file_id}
            ) from e

        return {}

    async def aretrieve_file(self, file_id: str) -> dict[str, Any]:
        url = f"{self._backend.base_url}/files/{file_id}"

        try:
            client = get_async_http_client()
            resp = await client.get(url, headers=self._backend._get_headers(), timeout=self._backend.timeout)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

        except httpx.HTTPStatusError as e:
            self._backend._handle_http_error(e, "aretrieve_file")
        except httpx.ConnectError as e:
            self._backend._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._backend._handle_timeout_error(e, self._backend.timeout)
        except Exception as e:
            logger.warning(
                "Moonshot 异步检索文件异常",
                extra={"error": str(e), "error_type": type(e).__name__, "file_id": file_id},
            )
            raise LLMAPIError(
                message=f"检索文件时发生错误: {e!s}", errors={"detail": str(e), "file_id": file_id}
            ) from e

        return {}

    def extract_result(self, file_id: str) -> dict[str, Any]:
        url = f"{self._backend.base_url}/files/{file_id}/extraction"

        try:
            client = get_sync_http_client()
            resp = client.get(url, headers=self._backend._get_headers(), timeout=self._backend.timeout)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

        except httpx.HTTPStatusError as e:
            self._backend._handle_http_error(e, "extract_result")
        except httpx.ConnectError as e:
            self._backend._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._backend._handle_timeout_error(e, self._backend.timeout)
        except Exception as e:
            logger.warning(
                "Moonshot 提取文件内容异常",
                extra={"error": str(e), "error_type": type(e).__name__, "file_id": file_id},
            )
            raise LLMAPIError(
                message=f"提取文件内容时发生错误: {e!s}", errors={"detail": str(e), "file_id": file_id}
            ) from e

        return {}

    async def aextract_result(self, file_id: str) -> dict[str, Any]:
        url = f"{self._backend.base_url}/files/{file_id}/extraction"

        try:
            client = get_async_http_client()
            resp = await client.get(url, headers=self._backend._get_headers(), timeout=self._backend.timeout)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

        except httpx.HTTPStatusError as e:
            self._backend._handle_http_error(e, "aextract_result")
        except httpx.ConnectError as e:
            self._backend._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._backend._handle_timeout_error(e, self._backend.timeout)
        except Exception as e:
            logger.warning(
                "Moonshot 异步提取文件内容异常",
                extra={"error": str(e), "error_type": type(e).__name__, "file_id": file_id},
            )
            raise LLMAPIError(
                message=f"提取文件内容时发生错误: {e!s}", errors={"detail": str(e), "file_id": file_id}
            ) from e

        return {}
