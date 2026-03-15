from __future__ import annotations

import inspect
import logging
import time
from typing import Any

from apps.legal_research.services.sources import CaseDetail

logger = logging.getLogger(__name__)


class ExecutorSourceGatewayMixin:
    @classmethod
    def _fetch_candidate_batch_with_retry(
        cls,
        *,
        source_client: Any,
        session: Any,
        keyword: str,
        offset: int,
        batch_size: int,
        task_id: str,
    ) -> list[Any]:
        for attempt in range(1, cls.SEARCH_RETRY_ATTEMPTS + 1):
            try:
                return cls._fetch_candidate_batch(
                    source_client=source_client,
                    session=session,
                    keyword=keyword,
                    offset=offset,
                    batch_size=batch_size,
                )
            except Exception as exc:
                if attempt >= cls.SEARCH_RETRY_ATTEMPTS:
                    raise
                logger.warning(
                    "候选案例检索失败，准备重试",
                    extra={
                        "task_id": task_id,
                        "offset": offset,
                        "batch_size": batch_size,
                        "attempt": attempt,
                        "max_attempts": cls.SEARCH_RETRY_ATTEMPTS,
                        "error": str(exc),
                    },
                )
                cls._sleep_for_retry(attempt=attempt)
        return []

    @classmethod
    def _fetch_case_detail_with_retry(
        cls,
        *,
        source_client: Any,
        session: Any,
        item: Any,
        task_id: str,
    ) -> CaseDetail | None:
        doc_id = str(getattr(item, "doc_id_unquoted", "") or getattr(item, "doc_id_raw", ""))
        for attempt in range(1, cls.DETAIL_RETRY_ATTEMPTS + 1):
            try:
                return source_client.fetch_case_detail(session=session, item=item)
            except Exception as exc:
                if attempt >= cls.DETAIL_RETRY_ATTEMPTS:
                    logger.warning(
                        "案例详情获取失败，已跳过该案例",
                        extra={
                            "task_id": task_id,
                            "doc_id": doc_id,
                            "attempt": attempt,
                            "max_attempts": cls.DETAIL_RETRY_ATTEMPTS,
                            "error": str(exc),
                        },
                    )
                    return None
                logger.warning(
                    "案例详情获取失败，准备重试",
                    extra={
                        "task_id": task_id,
                        "doc_id": doc_id,
                        "attempt": attempt,
                        "max_attempts": cls.DETAIL_RETRY_ATTEMPTS,
                        "error": str(exc),
                    },
                )
                cls._sleep_for_retry(attempt=attempt)
        return None

    @classmethod
    def _download_pdf_with_retry(
        cls,
        *,
        source_client: Any,
        session: Any,
        detail: CaseDetail,
        task_id: str,
    ) -> tuple[bytes, str] | None:
        doc_id = str(detail.doc_id_unquoted or detail.doc_id_raw)
        for attempt in range(1, cls.DOWNLOAD_RETRY_ATTEMPTS + 1):
            try:
                pdf = source_client.download_pdf(session=session, detail=detail)
                if pdf is not None:
                    return pdf

                if attempt >= cls.DOWNLOAD_RETRY_ATTEMPTS:
                    return None
                logger.info(
                    "PDF下载返回空结果，准备重试",
                    extra={
                        "task_id": task_id,
                        "doc_id": doc_id,
                        "attempt": attempt,
                        "max_attempts": cls.DOWNLOAD_RETRY_ATTEMPTS,
                    },
                )
                cls._sleep_for_retry(attempt=attempt)
            except Exception as exc:
                if "C_001_009" in str(exc):
                    raise RuntimeError("wk会话被限制访问(C_001_009)，请稍后重试") from exc
                if attempt >= cls.DOWNLOAD_RETRY_ATTEMPTS:
                    logger.warning(
                        "PDF下载失败，已跳过该案例",
                        extra={
                            "task_id": task_id,
                            "doc_id": doc_id,
                            "attempt": attempt,
                            "max_attempts": cls.DOWNLOAD_RETRY_ATTEMPTS,
                            "error": str(exc),
                        },
                    )
                    return None
                logger.warning(
                    "PDF下载失败，准备重试",
                    extra={
                        "task_id": task_id,
                        "doc_id": doc_id,
                        "attempt": attempt,
                        "max_attempts": cls.DOWNLOAD_RETRY_ATTEMPTS,
                        "error": str(exc),
                    },
                )
                cls._sleep_for_retry(attempt=attempt)
        return None

    @classmethod
    def _sleep_for_retry(cls, *, attempt: int) -> None:
        if cls.RETRY_BACKOFF_SECONDS <= 0:
            return
        time.sleep(cls.RETRY_BACKOFF_SECONDS * max(1, attempt))

    @classmethod
    def _fetch_candidate_batch(
        cls,
        *,
        source_client: Any,
        session: Any,
        keyword: str,
        offset: int,
        batch_size: int,
    ) -> list[Any]:
        search_cases = source_client.search_cases
        max_pages = cls._estimate_max_pages(offset=offset, batch_size=batch_size)
        signature = inspect.signature(search_cases)
        if "offset" in signature.parameters:
            return search_cases(
                session=session,
                keyword=keyword,
                max_candidates=batch_size,
                max_pages=max_pages,
                offset=offset,
            )

        # 兼容尚未实现 offset 的旧检索源：扩大上限后截取窗口。
        window = search_cases(
            session=session,
            keyword=keyword,
            max_candidates=offset + batch_size,
            max_pages=max_pages,
        )
        return window[offset : offset + batch_size]

    @classmethod
    def _estimate_max_pages(cls, *, offset: int, batch_size: int) -> int:
        required = ((offset + batch_size - 1) // cls.PAGE_SIZE_HINT) + 1
        return max(10, min(cls.MAX_PAGE_WINDOW, required + 2))
