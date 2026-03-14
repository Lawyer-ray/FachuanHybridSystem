from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

from .types import WeikeCaseDetail, WeikeSearchItem, WeikeSession


class WeikeDocumentMixin:
    DETAIL_RETRY_ATTEMPTS = 3
    DETAIL_RETRY_HTTP_STATUSES = frozenset({400, 408, 409, 425, 429, 500, 502, 503, 504})
    DOWNLOAD_RETRY_ATTEMPTS = 3
    DOWNLOAD_RETRY_HTTP_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

    def fetch_case_detail(self, *, session: WeikeSession, item: WeikeSearchItem) -> WeikeCaseDetail:
        errors: list[str] = []
        for doc_id in self._detail_doc_id_candidates(item):
            meta_url = f"https://law.wkinfo.com.cn/csi/document/{doc_id}?indexId=law.case"
            html_url = (
                f"https://law.wkinfo.com.cn/csi/document/{doc_id}/html"
                "?indexId=law.case&print=false&fromType=&useBalance=true&module="
            )

            meta_payload: dict[str, Any] | None = None
            html_payload: dict[str, Any] | None = None

            try:
                meta_resp = self._request_get_with_retry(
                    session=session,
                    url=meta_url,
                    timeout=30000,
                    max_attempts=self.DETAIL_RETRY_ATTEMPTS,
                    retry_statuses=self.DETAIL_RETRY_HTTP_STATUSES,
                )
                meta_status = self._response_status(meta_resp)
                if meta_status != 200:
                    errors.append(f"docId={doc_id} 元信息 HTTP {meta_status}")
                    continue
                meta_payload = self._response_json(meta_resp)
            except Exception as exc:
                errors.append(f"docId={doc_id} 元信息异常: {self._compact_error(exc)}")
                continue

            try:
                html_resp = self._request_get_with_retry(
                    session=session,
                    url=html_url,
                    timeout=30000,
                    max_attempts=self.DETAIL_RETRY_ATTEMPTS,
                    retry_statuses=self.DETAIL_RETRY_HTTP_STATUSES,
                )
                html_status = self._response_status(html_resp)
                if html_status != 200:
                    errors.append(f"docId={doc_id} 正文 HTTP {html_status}")
                    continue
                html_payload = self._response_json(html_resp)
            except Exception as exc:
                errors.append(f"docId={doc_id} 正文异常: {self._compact_error(exc)}")
                continue

            current_doc = (meta_payload or {}).get("currentDoc") or {}
            additional = current_doc.get("additionalFields") or {}
            html_content = str((html_payload or {}).get("content") or "")
            title = str(current_doc.get("title") or additional.get("title") or item.title_hint or "")
            case_digest = str(additional.get("caseDigest") or current_doc.get("summary") or "")

            return WeikeCaseDetail(
                doc_id_raw=item.doc_id_raw,
                doc_id_unquoted=item.doc_id_unquoted,
                detail_url=item.detail_url,
                search_id=item.search_id,
                module=item.module,
                title=title,
                court_text=str(additional.get("courtText") or ""),
                document_number=str(additional.get("documentNumber") or ""),
                judgment_date=str(additional.get("judgmentDate") or ""),
                case_digest=case_digest,
                content_text=self._html_to_text(html_content),
                raw_meta=meta_payload or {},
            )

        error_text = "；".join(errors[:4])
        raise RuntimeError(f"获取案例详情失败: {error_text or '未知错误'}")

    def download_pdf(self, *, session: WeikeSession, detail: WeikeCaseDetail) -> tuple[bytes, str] | None:
        # 与前端真实调用保持一致：优先使用 unquoted docId + showType=0 + filename。
        filename = self._build_download_filename(detail)
        attempts = [
            {
                "docId": detail.doc_id_unquoted,
                "showType": 0,
                "module": detail.module,
            },
            {
                "docId": detail.doc_id_unquoted,
                "showType": 0,
                "module": "",
            },
            {
                "docId": detail.doc_id_raw,
                "showType": 0,
                "module": detail.module,
            },
        ]

        for attempt in attempts:
            limit_payload = {
                "indexId": "law.case",
                "fileType": "pdf",
                "docId": attempt["docId"],
                "showType": attempt["showType"],
                "module": attempt["module"],
                "cellList": None,
            }

            limit_resp = self._request_post_json_with_retry(
                session=session,
                url="https://law.wkinfo.com.cn/csi/document/downloadLimit",
                payload=limit_payload,
                timeout=30000,
                max_attempts=self.DOWNLOAD_RETRY_ATTEMPTS,
                retry_statuses=self.DOWNLOAD_RETRY_HTTP_STATUSES,
            )
            if self._response_status(limit_resp) != 200:
                continue

            try:
                limit_payload_json = self._response_json(limit_resp)
            except Exception:
                continue

            if not bool(limit_payload_json.get("result")):
                continue

            path_payload = {
                "indexId": "law.case",
                "fileType": "pdf",
                "docId": attempt["docId"],
                "showType": attempt["showType"],
                "filename": filename,
                "module": attempt["module"],
            }
            if detail.search_id:
                path_payload["searchId"] = detail.search_id

            path_resp = self._request_post_json_with_retry(
                session=session,
                url="https://law.wkinfo.com.cn/csi/document/downloadPath",
                payload=path_payload,
                timeout=30000,
                max_attempts=self.DOWNLOAD_RETRY_ATTEMPTS,
                retry_statuses=self.DOWNLOAD_RETRY_HTTP_STATUSES,
            )

            response_json: dict[str, Any] = {}
            try:
                response_json = self._response_json(path_resp)
            except Exception:
                response_json = {}

            path_status = self._response_status(path_resp)
            if path_status == 400 and response_json.get("code") == "C_001_009":
                raise RuntimeError("wk会话被限制访问(C_001_009)，请稍后重试")

            if path_status != 200:
                continue

            key = str((response_json.get("data") or {}).get("key") or "")
            if not key:
                continue

            response_filename = str((response_json.get("data") or {}).get("filename") or "")
            if response_filename:
                filename = response_filename

            pdf_resp = self._request_get_with_retry(
                session=session,
                url=f"https://law.wkinfo.com.cn/api/download?key={key}",
                timeout=30000,
                max_attempts=self.DOWNLOAD_RETRY_ATTEMPTS,
                retry_statuses=self.DOWNLOAD_RETRY_HTTP_STATUSES,
            )
            if self._response_status(pdf_resp) != 200:
                continue

            headers = self._response_headers(pdf_resp)
            content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
            pdf_bytes = self._response_body(pdf_resp)
            if pdf_bytes and ("pdf" in content_type or pdf_bytes.startswith(b"%PDF")):
                return pdf_bytes, filename

        return None

    @staticmethod
    def _detail_doc_id_candidates(item: WeikeSearchItem) -> list[str]:
        candidates: list[str] = []
        for value in (item.doc_id_raw, item.doc_id_unquoted):
            normalized = str(value or "").strip()
            if not normalized:
                continue
            if normalized in candidates:
                continue
            candidates.append(normalized)
        return candidates

    @staticmethod
    def _compact_error(exc: Exception, *, max_len: int = 120) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        if len(message) <= max_len:
            return message
        return f"{message[: max_len - 3]}..."

    @staticmethod
    def _build_download_filename(detail: WeikeCaseDetail) -> str:
        title = re.sub(r'[\\\\/:*?"<>|]+', "_", detail.title or "").strip("._ ")
        if not title:
            title = detail.doc_id_unquoted or "weike_case"
        date_tag = datetime.now().strftime("%Y%m%d")
        return f"{title}_{date_tag}下载.pdf"

    @staticmethod
    def _html_to_text(html_content: str) -> str:
        text = re.sub(r"<script[\\s\\S]*?</script>", " ", html_content, flags=re.I)
        text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<br\\s*/?>", "\\n", text, flags=re.I)
        text = re.sub(r"</p>", "\\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"[\\t\\r ]+", " ", text)
        text = re.sub(r"\\n{3,}", "\\n\\n", text)
        return text.strip()
