from __future__ import annotations

import inspect
import logging
import random
import time
from typing import Any

from apps.legal_research.services.sources import CaseDetail

logger = logging.getLogger(__name__)


class ExecutorSourceGatewayMixin:  # pragma: no cover
    SEARCH_RETRY_ATTEMPTS: int
    DETAIL_RETRY_ATTEMPTS: int
    DOWNLOAD_RETRY_ATTEMPTS: int
    RETRY_BACKOFF_SECONDS: float
    RETRY_BACKOFF_MAX_SECONDS: float
    PAGE_SIZE_HINT: int
    MAX_PAGE_WINDOW: int

    @classmethod
    def _fetch_candidate_batch(
        cls,
        *,
        source_client: Any,
        session: Any,
        keyword: str,
        offset: int,
        batch_size: int,
        advanced_query: list[dict[str, str]] | None = None,
        court_filter: str = "",
        cause_of_action_filter: str = "",
        date_from: str = "",
        date_to: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> list[Any]:
        """拉取一批候选案例：按数据源客户端**实际支持的参数**自适应透传。

        三个来源客户端的 ``search_cases`` 签名并不一致（``base.CaseSourceClient``
        只有 offset/raw_payload，威科多出 advanced_query/法院/案由/日期筛选），
        所以这里先 ``inspect.signature`` 取参数名，只透传对端认识的字段；
        对端没有 ``offset`` 时退回「取窗口 + 切片」。

        注意：本方法必须是 ``classmethod`` —— 调用方 ``_fetch_candidate_batch_with_retry``
        也是 classmethod，写 ``cls._fetch_candidate_batch(...)``；若本方法退回实例方法，
        运行时会抛 ``missing 1 required positional argument: 'self'``（v27.2.8 起任务式
        检索 100% 失败的根因）。
        """
        search_cases = source_client.search_cases
        params = inspect.signature(search_cases).parameters
        max_pages = cls._estimate_max_pages(offset=offset, batch_size=batch_size)

        optional_kwargs: dict[str, Any] = {
            "advanced_query": advanced_query,
            "court_filter": court_filter,
            "cause_of_action_filter": cause_of_action_filter,
            "date_from": date_from,
            "date_to": date_to,
            "raw_payload": raw_payload,
        }
        extra_kwargs = {name: value for name, value in optional_kwargs.items() if name in params}

        if "offset" in params:
            # ``list(...)`` 而不是直接 return：三个数据源的 ``search_cases`` 都没有
            # 严格返回类型（鸭子类型客户端，mypy 看到的是 Any），直接 return 会被
            # ``no-any-return`` 判错——这个错误会被 CI 的 mypy 全量棘轮记一笔。
            # 顺带把「返回 list」这件事钉死：调用方按 ``list[Any]`` 消费。
            return list(
                search_cases(
                    session=session,
                    keyword=keyword,
                    max_candidates=batch_size,
                    max_pages=max_pages,
                    offset=offset,
                    **extra_kwargs,
                )
            )

        window = search_cases(
            session=session,
            keyword=keyword,
            max_candidates=offset + batch_size,
            max_pages=max_pages,
            **extra_kwargs,
        )
        return list(window[offset : offset + batch_size])

    @classmethod
    def _fetch_candidate_batch_with_retry(  # pragma: no cover
        cls,
        *,
        source_client: Any,
        session: Any,
        keyword: str,
        offset: int,
        batch_size: int,
        task_id: str,
        advanced_query: list[dict[str, str]] | None = None,
        court_filter: str = "",
        cause_of_action_filter: str = "",
        date_from: str = "",
        date_to: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> list[Any]:
        for attempt in range(1, cls.SEARCH_RETRY_ATTEMPTS + 1):
            try:
                return cls._fetch_candidate_batch(
                    source_client=source_client,
                    session=session,
                    keyword=keyword,
                    offset=offset,
                    batch_size=batch_size,
                    advanced_query=advanced_query,
                    court_filter=court_filter,
                    cause_of_action_filter=cause_of_action_filter,
                    date_from=date_from,
                    date_to=date_to,
                    raw_payload=raw_payload,
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
    def _fetch_case_detail_with_retry(  # pragma: no cover
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
                return source_client.fetch_case_detail(session=session, item=item)  # type: ignore[no-any-return]
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
    def _download_pdf_with_retry(  # pragma: no cover
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
                    return pdf  # type: ignore[no-any-return]

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
                    raise RuntimeError(str(exc)) from exc
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
    def _sleep_for_retry(cls, *, attempt: int) -> None:  # pragma: no cover
        if cls.RETRY_BACKOFF_SECONDS <= 0:
            return
        base = float(cls.RETRY_BACKOFF_SECONDS)
        growth = 2 ** max(0, int(attempt) - 1)
        delay = base * growth
        max_delay = max(base, float(getattr(cls, "RETRY_BACKOFF_MAX_SECONDS", 6.0)))
        delay = min(delay, max_delay)
        jitter = random.uniform(0.0, delay * 0.25)
        time.sleep(delay + jitter)

    @classmethod
    def _estimate_max_pages(cls, *, offset: int, batch_size: int) -> int:  # pragma: no cover
        required = ((offset + batch_size - 1) // cls.PAGE_SIZE_HINT) + 1
        return max(10, min(cls.MAX_PAGE_WINDOW, required + 2))
