"""API endpoints."""

import logging
from typing import Any

from apps.automation.services.document_delivery.data_classes import DocumentDetail, DocumentListResponse, DocumentRecord

from .court_document_api_exceptions import ApiResponseError

logger = logging.getLogger("apps.automation")


class CourtDocumentResponseParser:
    def parse_document_list(self, response_json: dict[str, Any]) -> DocumentListResponse:
        code = response_json.get("code")
        if code != 200:
            raise ApiResponseError(
                message=f"API 返回错误: {response_json.get('msg', '未知错误')}", response_code=code, errors={}
            )

        response_data = response_json.get("data", {}) or {}
        total = response_data.get("total", 0) or 0
        documents_data = response_data.get("data", []) or []

        documents: list[DocumentRecord] = []
        for doc_data in documents_data:
            if not isinstance(doc_data, dict):
                continue
            if not doc_data.get("ah") or not doc_data.get("sdbh") or not doc_data.get("fssj"):
                continue
            try:
                documents.append(DocumentRecord.from_api_response(doc_data))
            except Exception:
                logger.warning(f"解析文书记录失败: data={doc_data}")
                continue

        return DocumentListResponse(total=int(total), documents=documents)

    def parse_document_details(self, response_json: dict[str, Any]) -> list[DocumentDetail]:
        code = response_json.get("code")
        if code != 200:
            raise ApiResponseError(
                message=f"API 返回错误: {response_json.get('msg', '未知错误')}", response_code=code, errors={}
            )

        documents_data = response_json.get("data", []) or []
        details: list[DocumentDetail] = []
        for doc_data in documents_data:
            if not isinstance(doc_data, dict):
                continue
            try:
                detail = DocumentDetail.from_api_response(doc_data)
            except Exception:
                logger.warning(f"解析文书详情失败: data={doc_data}")
                continue

            if not detail.wjlj:
                continue
            details.append(detail)

        return details
