"""API endpoints."""

from typing import Any

from apps.core.exceptions import NetworkError

from .court_document_api_exceptions import ApiResponseError, TokenExpiredError
from .court_document_http_client import CourtDocumentHttpClient
from .court_document_response_parser import CourtDocumentResponseParser


class CourtDocumentApiCoordinator:
    def __init__(
        self,
        *,
        http_client: CourtDocumentHttpClient,
        parser: CourtDocumentResponseParser,
        retry_count: int,
    ) -> None:
        self.http_client = http_client
        self.parser = parser
        self.retry_count = retry_count

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": token, "Content-Type": "application/json"}

    def post_with_retry(self, *, url: str, token: str, json_data: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self.retry_count + 1):
            try:
                return self.http_client.post_json(url=url, headers=self._auth_headers(token), json_data=json_data)
            except NetworkError:
                if attempt < self.retry_count:
                    continue
                raise
            except (TokenExpiredError, ApiResponseError):
                raise

        raise NetworkError(message="请求失败", errors={"url": url})

    def fetch_document_list(self, *, url: str, token: str, page_num: int, page_size: int) -> Any:
        payload: dict[str, Any] = {"pageNum": page_num, "pageSize": page_size}
        response_json = self.post_with_retry(url=url, token=token, json_data=payload)
        return self.parser.parse_document_list(response_json)

    def fetch_document_details(self, *, url: str, token: str, sdbh: str, sdsin: str, mm: str) -> Any:
        payload: dict[str, Any] = {"sdbh": sdbh, "sdsin": sdsin, "mm": mm}
        response_json = self.post_with_retry(url=url, token=token, json_data=payload)
        return self.parser.parse_document_details(response_json)

    def download_bytes(self, *, url: str) -> bytes:
        for attempt in range(self.retry_count + 1):
            try:
                return self.http_client.get_bytes(url=url, timeout_seconds=self.http_client.timeout_seconds * 2)
            except NetworkError:
                if attempt < self.retry_count:
                    continue
                raise
            except ApiResponseError:
                raise

        raise NetworkError(message="请求失败", errors={"url": url})
