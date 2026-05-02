from __future__ import annotations

import html
import logging
import re
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

from .types import WeikeCaseDetail, WeikeSearchItem, WeikeSession

logger = logging.getLogger(__name__)


class WeikeDocumentMixin:
    _request_get_with_retry: Callable[..., Any]
    _request_post_json_with_retry: Callable[..., Any]
    _response_status: Callable[[Any], int]
    _response_json: Callable[[Any], dict[str, Any]]
    _response_headers: Callable[[Any], dict[str, str]]
    _response_body: Callable[[Any], bytes]

    DETAIL_RETRY_ATTEMPTS = 3
    DETAIL_RETRY_HTTP_STATUSES = frozenset({400, 408, 409, 425, 429, 500, 502, 503, 504})
    DOWNLOAD_RETRY_ATTEMPTS = 3
    DOWNLOAD_RETRY_HTTP_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
    DOM_DETAIL_MAX_CHARS = 60000
    SESSION_RESTRICT_CODE = "C_001_009"
    SESSION_RESTRICT_COOLDOWN_SECONDS = 180

    def fetch_case_detail(self, *, session: WeikeSession, item: WeikeSearchItem) -> WeikeCaseDetail:
        self._raise_if_session_restricted(session=session, stage="fetch_case_detail")
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
                meta_started = time.monotonic()
                meta_resp = self._request_get_with_retry(
                    session=session,
                    url=meta_url,
                    timeout=30000,
                    max_attempts=self.DETAIL_RETRY_ATTEMPTS,
                    retry_statuses=self.DETAIL_RETRY_HTTP_STATUSES,
                )
                meta_status = self._response_status(meta_resp)
                meta_payload = self._response_json(meta_resp)
                self._record_detail_event(
                    session=session,
                    interface_name="document_meta",
                    method="GET",
                    url=meta_url,
                    status_code=meta_status,
                    duration_ms=int((time.monotonic() - meta_started) * 1000),
                    success=meta_status == 200,
                    request_summary={"doc_id": doc_id, "url": meta_url},
                    response_summary=self._summarize_meta_payload(meta_payload),
                    error_code="" if meta_status == 200 else f"HTTP_{meta_status}",
                )
                if self._is_session_restricted_response(status=meta_status, payload=meta_payload):
                    self._mark_session_restricted(
                        session=session,
                        stage="detail_meta",
                        status=meta_status,
                        payload=meta_payload,
                    )
                    raise RuntimeError("wk会话被限制访问(C_001_009)，请稍后重试")
                if meta_status != 200:
                    errors.append(f"docId={doc_id} 元信息 HTTP {meta_status}")
                    continue
            except RuntimeError as exc:
                self._record_detail_event(
                    session=session,
                    interface_name="document_meta",
                    method="GET",
                    url=meta_url,
                    duration_ms=0,
                    success=False,
                    error_code="RUNTIME_ERROR",
                    error_message=self._compact_error(exc),
                    request_summary={"doc_id": doc_id, "url": meta_url},
                )
                if self.SESSION_RESTRICT_CODE in str(exc):
                    raise
                errors.append(f"docId={doc_id} 元信息异常: {self._compact_error(exc)}")
                continue
            except Exception as exc:
                self._record_detail_event(
                    session=session,
                    interface_name="document_meta",
                    method="GET",
                    url=meta_url,
                    duration_ms=0,
                    success=False,
                    error_code="REQUEST_ERROR",
                    error_message=self._compact_error(exc),
                    request_summary={"doc_id": doc_id, "url": meta_url},
                )
                errors.append(f"docId={doc_id} 元信息异常: {self._compact_error(exc)}")
                continue

            try:
                html_started = time.monotonic()
                html_resp = self._request_get_with_retry(
                    session=session,
                    url=html_url,
                    timeout=30000,
                    max_attempts=self.DETAIL_RETRY_ATTEMPTS,
                    retry_statuses=self.DETAIL_RETRY_HTTP_STATUSES,
                )
                html_status = self._response_status(html_resp)
                html_payload = self._response_json(html_resp)
                self._record_detail_event(
                    session=session,
                    interface_name="document_html",
                    method="GET",
                    url=html_url,
                    status_code=html_status,
                    duration_ms=int((time.monotonic() - html_started) * 1000),
                    success=html_status == 200,
                    request_summary={"doc_id": doc_id, "url": html_url},
                    response_summary=self._summarize_html_payload(html_payload),
                    error_code="" if html_status == 200 else f"HTTP_{html_status}",
                )
                if self._is_session_restricted_response(status=html_status, payload=html_payload):
                    self._mark_session_restricted(
                        session=session,
                        stage="detail_html",
                        status=html_status,
                        payload=html_payload,
                    )
                    raise RuntimeError("wk会话被限制访问(C_001_009)，请稍后重试")
                if html_status != 200:
                    errors.append(f"docId={doc_id} 正文 HTTP {html_status}")
                    continue
            except RuntimeError as exc:
                self._record_detail_event(
                    session=session,
                    interface_name="document_html",
                    method="GET",
                    url=html_url,
                    duration_ms=0,
                    success=False,
                    error_code="RUNTIME_ERROR",
                    error_message=self._compact_error(exc),
                    request_summary={"doc_id": doc_id, "url": html_url},
                )
                if self.SESSION_RESTRICT_CODE in str(exc):
                    raise
                errors.append(f"docId={doc_id} 正文异常: {self._compact_error(exc)}")
                continue
            except Exception as exc:
                self._record_detail_event(
                    session=session,
                    interface_name="document_html",
                    method="GET",
                    url=html_url,
                    duration_ms=0,
                    success=False,
                    error_code="REQUEST_ERROR",
                    error_message=self._compact_error(exc),
                    request_summary={"doc_id": doc_id, "url": html_url},
                )
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

        fallback_detail = self._fetch_case_detail_via_dom(session=session, item=item, errors=errors)
        if fallback_detail is not None:
            self._record_detail_event(
                session=session,
                interface_name="dom_detail",
                method="GET",
                url=item.detail_url,
                status_code=200,
                success=True,
                request_summary={"doc_id": item.doc_id_unquoted or item.doc_id_raw},
                response_summary={
                    "title": fallback_detail.title,
                    "content_length": len(fallback_detail.content_text or ""),
                },
            )
            return fallback_detail

        error_text = "；".join(errors[:4])
        raise RuntimeError(f"获取案例详情失败: {error_text or '未知错误'}")

    def download_pdf(self, *, session: WeikeSession, detail: WeikeCaseDetail) -> tuple[bytes, str] | None:
        self._raise_if_session_restricted(session=session, stage="download_pdf")
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
            limit_status = self._response_status(limit_resp)
            try:
                limit_payload_json = self._response_json(limit_resp)
            except Exception:
                limit_payload_json = {}
            if self._is_session_restricted_response(status=limit_status, payload=limit_payload_json):
                self._mark_session_restricted(
                    session=session,
                    stage="download_limit",
                    status=limit_status,
                    payload=limit_payload_json,
                )
                raise RuntimeError("wk会话被限制访问(C_001_009)，请稍后重试")
            if limit_status != 200:
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
            if self._is_session_restricted_response(status=path_status, payload=response_json):
                self._mark_session_restricted(
                    session=session,
                    stage="download_path",
                    status=path_status,
                    payload=response_json,
                )
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

    def download_doc(self, *, session: WeikeSession, detail: WeikeCaseDetail) -> tuple[bytes, str] | None:
        """下载 Word 文档（.doc 格式）"""
        self._raise_if_session_restricted(session=session, stage="download_doc")
        filename = self._build_download_filename(detail)
        filename = filename.rsplit(".", 1)[0] + ".doc" if "." in filename else filename + ".doc"

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
                "fileType": "doc",
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
            limit_status = self._response_status(limit_resp)
            try:
                limit_payload_json = self._response_json(limit_resp)
            except Exception:
                limit_payload_json = {}
            if self._is_session_restricted_response(status=limit_status, payload=limit_payload_json):
                self._mark_session_restricted(
                    session=session,
                    stage="download_doc_limit",
                    status=limit_status,
                    payload=limit_payload_json,
                )
                raise RuntimeError("wk会话被限制访问(C_001_009)，请稍后重试")
            if limit_status != 200:
                continue

            if not bool(limit_payload_json.get("result")):
                continue

            path_payload = {
                "indexId": "law.case",
                "fileType": "doc",
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
            if self._is_session_restricted_response(status=path_status, payload=response_json):
                self._mark_session_restricted(
                    session=session,
                    stage="download_doc_path",
                    status=path_status,
                    payload=response_json,
                )
                raise RuntimeError("wk会话被限制访问(C_001_009)，请稍后重试")

            if path_status != 200:
                continue

            key = str((response_json.get("data") or {}).get("key") or "")
            if not key:
                continue

            response_filename = str((response_json.get("data") or {}).get("filename") or "")
            if response_filename:
                filename = response_filename

            doc_resp = self._request_get_with_retry(
                session=session,
                url=f"https://law.wkinfo.com.cn/api/download?key={key}",
                timeout=30000,
                max_attempts=self.DOWNLOAD_RETRY_ATTEMPTS,
                retry_statuses=self.DOWNLOAD_RETRY_HTTP_STATUSES,
            )
            if self._response_status(doc_resp) != 200:
                continue

            headers = self._response_headers(doc_resp)
            doc_bytes = self._response_body(doc_resp)
            if doc_bytes and len(doc_bytes) > 0:
                return doc_bytes, filename

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

    @classmethod
    def _is_session_restricted_response(cls, *, status: int, payload: dict[str, Any] | None) -> bool:
        code = str((payload or {}).get("code") or "").strip().upper()
        if code == cls.SESSION_RESTRICT_CODE:
            return True
        return status == 400 and code == cls.SESSION_RESTRICT_CODE

    def _mark_session_restricted(
        self,
        *,
        session: WeikeSession,
        stage: str,
        status: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        cooldown_seconds = self._resolve_session_restrict_cooldown_seconds()
        session.restricted_until_epoch = time.time() + cooldown_seconds
        logger.warning(
            "wk会话触发访问限制",
            extra={
                "stage": stage,
                "status": int(status or 0),
                "code": str((payload or {}).get("code") or ""),
                "cooldown_seconds": cooldown_seconds,
            },
        )

    def _raise_if_session_restricted(self, *, session: WeikeSession, stage: str) -> None:
        restricted_until = float(getattr(session, "restricted_until_epoch", 0.0) or 0.0)
        now = time.time()
        if restricted_until <= now:
            return
        wait_seconds = max(1, int(restricted_until - now))
        logger.info(
            "wk会话限制冷却中，跳过请求",
            extra={
                "stage": stage,
                "wait_seconds": wait_seconds,
            },
        )
        raise RuntimeError(f"wk会话被限制访问(C_001_009)，请{wait_seconds}秒后重试")

    def _resolve_session_restrict_cooldown_seconds(self) -> int:
        raw = getattr(self, "_session_restrict_cooldown_seconds", self.SESSION_RESTRICT_COOLDOWN_SECONDS)
        try:
            seconds = int(raw)
        except (TypeError, ValueError):
            seconds = self.SESSION_RESTRICT_COOLDOWN_SECONDS
        return max(30, seconds)

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

    def _fetch_case_detail_via_dom(
        self,
        *,
        session: WeikeSession,
        item: WeikeSearchItem,
        errors: list[str],
    ) -> WeikeCaseDetail | None:
        if not item.detail_url:
            return None

        try:
            ensure_playwright = getattr(self, "_ensure_playwright_session", None)
            if callable(ensure_playwright):
                ensure_playwright(session)
            page = session.page
            if page is None:
                return None

            page.goto(item.detail_url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(1200)
            body_text = page.locator("body").inner_text(timeout=60000)
            normalized = self._normalize_dom_text(body_text)
            if not normalized:
                raise RuntimeError("详情页正文为空")
            if "抱歉，此功能需要登录后操作" in normalized:
                raise RuntimeError("详情页提示需要登录")

            title = self._extract_dom_title(body_text=normalized, item=item)
            court_text = self._extract_dom_field(
                text=normalized,
                patterns=(r"(?:审理法院|法院)[:：]\s*([^\n]+)",),
            )
            document_number = self._extract_dom_field(
                text=normalized,
                patterns=(r"(?:案号|文号)[:：]\s*([^\n]+)",),
            )
            judgment_date = self._extract_dom_field(
                text=normalized,
                patterns=(
                    r"(?:裁判日期|判决日期)[:：]\s*([0-9]{4}[年\-/][0-9]{1,2}[月\-/][0-9]{1,2}日?)",
                    r"([0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日)",
                ),
            )
            case_digest = self._build_dom_digest(normalized)
            content_text = normalized[: self.DOM_DETAIL_MAX_CHARS]

            return WeikeCaseDetail(
                doc_id_raw=item.doc_id_raw,
                doc_id_unquoted=item.doc_id_unquoted,
                detail_url=item.detail_url,
                search_id=item.search_id,
                module=item.module,
                title=title,
                court_text=court_text,
                document_number=document_number,
                judgment_date=judgment_date,
                case_digest=case_digest,
                content_text=content_text,
                raw_meta={
                    "detail_source": "playwright_dom_fallback",
                    "fallback_errors": errors[:4],
                },
            )
        except Exception as exc:
            self._record_detail_event(
                session=session,
                interface_name="dom_detail",
                method="GET",
                url=item.detail_url,
                success=False,
                error_code="DOM_DETAIL_ERROR",
                error_message=self._compact_error(exc),
                request_summary={"doc_id": item.doc_id_unquoted or item.doc_id_raw},
                response_summary={"errors": errors[:3]},
            )
            errors.append(f"DOM兜底异常: {self._compact_error(exc)}")
            return None

    @staticmethod
    def _normalize_dom_text(text: str) -> str:
        normalized = str(text or "").replace("\xa0", " ").strip()
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized

    @classmethod
    def _extract_dom_title(cls, *, body_text: str, item: WeikeSearchItem) -> str:
        title = cls._extract_dom_field(
            text=body_text,
            patterns=(
                r"(?:标题|案由)[:：]\s*([^\n]{4,120})",
                r"([^\n]{6,120}?(?:判决书|裁定书|调解书))",
            ),
        )
        if title:
            return title
        if item.title_hint:
            return str(item.title_hint)
        return str(item.doc_id_unquoted or item.doc_id_raw)

    @staticmethod
    def _extract_dom_field(*, text: str, patterns: tuple[str, ...]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return re.sub(r"\s+", " ", match.group(1)).strip()
        return ""

    @staticmethod
    def _build_dom_digest(text: str) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if not compact:
            return ""
        if len(compact) <= 220:
            return compact
        return f"{compact[:220]}..."

    @staticmethod
    def _summarize_meta_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
        current_doc = (payload or {}).get("currentDoc") or {}
        additional = current_doc.get("additionalFields") or {}
        return {
            "title": str(current_doc.get("title") or additional.get("title") or ""),
            "court_text": str(additional.get("courtText") or ""),
            "document_number": str(additional.get("documentNumber") or ""),
            "judgment_date": str(additional.get("judgmentDate") or ""),
        }

    @staticmethod
    def _summarize_html_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
        content = str((payload or {}).get("content") or "")
        return {
            "content_length": len(content),
            "has_content": bool(content),
        }

    @staticmethod
    def _record_detail_event(
        *,
        session: WeikeSession,
        interface_name: str,
        method: str = "",
        url: str = "",
        status_code: int | None = None,
        duration_ms: int = 0,
        success: bool,
        error_code: str = "",
        error_message: str = "",
        request_summary: object = None,
        response_summary: object = None,
    ) -> None:
        LegalResearchTaskEventService.record_event(
            task_id=getattr(session, "task_id", ""),
            stage="detail",
            source="dom" if interface_name == "dom_detail" else "api",
            interface_name=interface_name,
            method=method,
            url=url,
            status_code=status_code,
            duration_ms=duration_ms,
            success=success,
            error_code=error_code,
            error_message=error_message,
            request_summary=request_summary,
            response_summary=response_summary,
        )
