"""案例相似度 - 缓存读写 / 序列化."""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from typing import Any

from django.core.cache import cache

SIMILARITY_CACHE_PREFIX = "legal_research:similarity"
SIMILARITY_PROMPT_VERSION = "v2-structured"
SIMILARITY_LOCAL_CACHE_MAX_SIZE = 1024
SEMANTIC_EMBEDDING_CACHE_PREFIX = "legal_research:semantic_embedding"
SEMANTIC_VECTOR_LOCAL_CACHE_MAX_SIZE = 2048
SEMANTIC_EMBEDDING_TEXT_MAX_CHARS = 1400


def build_similarity_cache_key(
    *,
    mode: str,
    model: str | None,
    keyword: str,
    case_summary: str,
    title: str,
    case_digest: str,
    candidate_excerpt: str,
    first_score: float | None = None,
    first_reason: str | None = None,
) -> str:
    payload = {
        "v": SIMILARITY_PROMPT_VERSION,
        "mode": mode,
        "model": str(model or "").strip(),
        "keyword": re.sub(r"\s+", " ", (keyword or "")).strip(),
        "case_summary": re.sub(r"\s+", " ", (case_summary or "")).strip(),
        "title": re.sub(r"\s+", " ", (title or "")).strip(),
        "case_digest": re.sub(r"\s+", " ", (case_digest or "")).strip(),
        "candidate_excerpt": re.sub(r"\s+", " ", (candidate_excerpt or "")).strip(),
    }
    if first_score is not None:
        payload["first_score"] = str(round(float(first_score), 4))
    if first_reason:
        payload["first_reason"] = re.sub(r"\s+", " ", first_reason).strip()[:220]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{SIMILARITY_CACHE_PREFIX}:{digest}"


def build_semantic_embedding_cache_key(*, model: str, text: str) -> str:
    raw = f"{model}|{text}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{SEMANTIC_EMBEDDING_CACHE_PREFIX}:{digest}"


def normalize_embedding_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "")).strip()
    if not normalized:
        return ""
    return normalized[:SEMANTIC_EMBEDDING_TEXT_MAX_CHARS]


def serialize_similarity_result(result: Any) -> dict[str, Any]:
    return {
        "score": float(result.score),
        "reason": str(result.reason or ""),
        "model": str(result.model or ""),
        "metadata": result.metadata if isinstance(result.metadata, dict) else {},
    }


def deserialize_similarity_result(payload: dict[str, Any], *, result_class: type) -> Any | None:
    try:
        score = float(payload.get("score", 0.0))
    except (TypeError, ValueError):
        return None
    reason = str(payload.get("reason", "") or "")
    model = str(payload.get("model", "") or "")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    return result_class(
        score=max(0.0, min(1.0, score)),
        reason=reason,
        model=model,
        metadata=metadata,
    )


def coerce_float_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    out: list[float] = []
    for item in value:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            return []
    return out


class SimilarityCacheManager:
    """管理相似度评分的本地缓存 + Django 共享缓存."""

    def __init__(
        self,
        *,
        cache_ttl: int,
        local_cache_max_size: int = SIMILARITY_LOCAL_CACHE_MAX_SIZE,
        result_class: type,
    ) -> None:
        self._cache_ttl = max(60, cache_ttl)
        self._local_cache_max_size = max(32, local_cache_max_size)
        self._local_cache: OrderedDict[str, Any] = OrderedDict()
        self._result_class = result_class

    def load(self, cache_key: str) -> tuple[Any | None, dict[str, str]]:
        if not cache_key:
            return None, {"source": "none", "probe": "empty_key"}
        local = self._read_local(cache_key)
        if local is not None:
            return local, {"source": "local", "probe": "local_hit"}

        try:
            payload = cache.get(cache_key)
        except Exception:
            return None, {"source": "none", "probe": "shared_error"}
        if payload is None:
            return None, {"source": "none", "probe": "shared_miss"}
        if not isinstance(payload, dict):
            return None, {"source": "none", "probe": "shared_invalid_payload"}
        cached = deserialize_similarity_result(payload, result_class=self._result_class)
        if cached is None:
            return None, {"source": "none", "probe": "shared_invalid_result"}
        self._write_local(cache_key=cache_key, result=cached)
        return cached, {"source": "shared", "probe": "shared_hit"}

    def save(self, *, cache_key: str, result: Any) -> None:
        if not cache_key:
            return
        self._write_local(cache_key=cache_key, result=result)
        payload = serialize_similarity_result(result)
        try:
            cache.set(cache_key, payload, timeout=self._cache_ttl)
        except Exception:
            return

    def _read_local(self, cache_key: str) -> Any | None:
        if not cache_key:
            return None
        cached = self._local_cache.get(cache_key)
        if cached is None:
            return None
        self._local_cache.move_to_end(cache_key, last=True)
        return cached

    def _write_local(self, *, cache_key: str, result: Any) -> None:
        if not cache_key:
            return
        self._local_cache[cache_key] = result
        self._local_cache.move_to_end(cache_key, last=True)
        while len(self._local_cache) > self._local_cache_max_size:
            self._local_cache.popitem(last=False)


class SemanticVectorCacheManager:
    """管理语义向量的本地缓存 + Django 共享缓存."""

    def __init__(
        self,
        *,
        cache_ttl: int,
        local_cache_max_size: int = SEMANTIC_VECTOR_LOCAL_CACHE_MAX_SIZE,
    ) -> None:
        self._cache_ttl = max(60, cache_ttl)
        self._local_cache_max_size = max(64, local_cache_max_size)
        self._local_cache: OrderedDict[str, list[float]] = OrderedDict()

    def read_local(self, cache_key: str) -> list[float] | None:
        if not cache_key:
            return None
        cached = self._local_cache.get(cache_key)
        if cached is None:
            return None
        self._local_cache.move_to_end(cache_key, last=True)
        return cached

    def write_local(self, *, cache_key: str, vector: list[float]) -> None:
        if not cache_key:
            return
        self._local_cache[cache_key] = vector
        self._local_cache.move_to_end(cache_key, last=True)
        while len(self._local_cache) > self._local_cache_max_size:
            self._local_cache.popitem(last=False)

    def load_from_django_cache(self, cache_key: str) -> list[float] | None:
        try:
            payload = cache.get(cache_key)
        except Exception:
            return None
        if isinstance(payload, list) and payload:
            vector = coerce_float_list(payload)
            if vector:
                self.write_local(cache_key=cache_key, vector=vector)
                return vector
        return None

    def save_to_django_cache(self, *, cache_key: str, vector: list[float]) -> None:
        self.write_local(cache_key=cache_key, vector=vector)
        try:
            cache.set(cache_key, vector, timeout=self._cache_ttl)
        except Exception:
            pass
