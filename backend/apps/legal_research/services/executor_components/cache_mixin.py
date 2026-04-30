"""缓存管理：案例详情两级缓存（内存 + Django cache）。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from apps.legal_research.services.sources import CaseDetail


class ExecutorCacheMixin:
    DETAIL_CACHE_TTL_SECONDS = 21600

    @classmethod
    def _reserve_new_items(cls, *, items: list[Any], seen_doc_ids: set[str]) -> tuple[list[Any], int]:
        unique_items: list[Any] = []
        duplicate_in_batch = 0
        for item in items:
            doc_id = cls._extract_item_doc_id(item)
            if doc_id and doc_id in seen_doc_ids:
                duplicate_in_batch += 1
                continue
            if doc_id:
                seen_doc_ids.add(doc_id)
            unique_items.append(item)
        return unique_items, duplicate_in_batch

    @classmethod
    def _fetch_case_detail_with_cache(
        cls,
        *,
        source_client: Any,
        session: Any,
        source: str,
        item: Any,
        task_id: str,
        local_cache: dict[str, CaseDetail],
        ttl_seconds: int,
    ) -> CaseDetail | None:
        doc_id = cls._extract_item_doc_id(item)
        cache_key = cls._build_case_detail_cache_key(source=source, doc_id=doc_id)
        if cache_key:
            cached = local_cache.get(cache_key)
            if cached is not None:
                return cached
            persistent = cls._load_case_detail_cache(cache_key)
            if persistent is not None:
                local_cache[cache_key] = persistent
                return persistent

        detail = cls._fetch_case_detail_with_retry(  # type: ignore[attr-defined]
            source_client=source_client,
            session=session,
            item=item,
            task_id=task_id,
        )
        if detail is None:
            return None
        if cache_key:
            local_cache[cache_key] = detail
            cls._save_case_detail_cache(cache_key=cache_key, detail=detail, ttl_seconds=ttl_seconds)
        return detail  # type: ignore[no-any-return]

    @classmethod
    def _build_case_detail_cache_key(cls, *, source: str, doc_id: str) -> str:
        source_name = str(source or "").strip().lower()
        doc_id_norm = str(doc_id or "").strip()
        if not source_name or not doc_id_norm:
            return ""
        return f"legal_research:detail:{source_name}:{doc_id_norm}"

    @classmethod
    def _load_case_detail_cache(cls, cache_key: str) -> CaseDetail | None:
        try:
            from django.core.cache import cache

            payload = cache.get(cache_key)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return cls._deserialize_case_detail_payload(payload)

    @classmethod
    def _save_case_detail_cache(cls, *, cache_key: str, detail: CaseDetail, ttl_seconds: int) -> None:
        payload = cls._serialize_case_detail(detail)
        if not payload:
            return
        try:
            from django.core.cache import cache

            cache.set(cache_key, payload, timeout=max(60, int(ttl_seconds)))
        except Exception:
            return

    @staticmethod
    def _serialize_case_detail(detail: CaseDetail) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "doc_id_raw": str(getattr(detail, "doc_id_raw", "") or ""),
            "doc_id_unquoted": str(getattr(detail, "doc_id_unquoted", "") or ""),
            "detail_url": str(getattr(detail, "detail_url", "") or ""),
            "search_id": str(getattr(detail, "search_id", "") or ""),
            "module": str(getattr(detail, "module", "") or ""),
            "title": str(getattr(detail, "title", "") or ""),
            "court_text": str(getattr(detail, "court_text", "") or ""),
            "document_number": str(getattr(detail, "document_number", "") or ""),
            "judgment_date": str(getattr(detail, "judgment_date", "") or ""),
            "case_digest": str(getattr(detail, "case_digest", "") or ""),
            "content_text": str(getattr(detail, "content_text", "") or ""),
        }
        raw_meta = getattr(detail, "raw_meta", None)
        if isinstance(raw_meta, dict):
            payload["raw_meta"] = raw_meta
        return payload

    @staticmethod
    def _deserialize_case_detail_payload(payload: dict[str, Any]) -> CaseDetail | None:
        doc_id_raw = str(payload.get("doc_id_raw", "") or "")
        doc_id_unquoted = str(payload.get("doc_id_unquoted", "") or "")
        if not doc_id_raw and not doc_id_unquoted:
            return None
        return SimpleNamespace(
            doc_id_raw=doc_id_raw,
            doc_id_unquoted=doc_id_unquoted,
            detail_url=str(payload.get("detail_url", "") or ""),
            search_id=str(payload.get("search_id", "") or ""),
            module=str(payload.get("module", "") or ""),
            title=str(payload.get("title", "") or ""),
            court_text=str(payload.get("court_text", "") or ""),
            document_number=str(payload.get("document_number", "") or ""),
            judgment_date=str(payload.get("judgment_date", "") or ""),
            case_digest=str(payload.get("case_digest", "") or ""),
            content_text=str(payload.get("content_text", "") or ""),
            raw_meta=payload.get("raw_meta", {}),
        )

    @staticmethod
    def _extract_item_doc_id(item: Any) -> str:
        return str(getattr(item, "doc_id_unquoted", "") or getattr(item, "doc_id_raw", "")).strip()
