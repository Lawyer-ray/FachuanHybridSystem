"""Module for metrics."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


DEFAULT_BUCKETS_MS: tuple[int, ...] = (
    5,
    10,
    25,
    50,
    100,
    250,
    500,
    1000,
    2000,
    5000,
    10000,
    30000,
)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_HEX_RE = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
_LABEL_SAFE_RE = re.compile(r"[^a-z0-9_-]+", re.IGNORECASE)


def _minute_id(dt: Any | None = None) -> str:
    if dt is None:
        from django.utils import timezone as tz

        dt = tz.now()
    return str(dt.strftime("%Y%m%d%H%M"))


def _last_minutes(*, window_minutes: int) -> list[str]:
    window = int(window_minutes or 1)
    now = timezone.now()
    minutes: list[str] = []
    from datetime import timedelta

    for i in range(max(1, window)):
        minutes.append(_minute_id(now - timedelta(minutes=i)))
    minutes.reverse()
    return minutes


def _stable_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _normalize_label(value: str, *, default: str, max_len: int) -> str:
    v = str(value or "").strip().lower()
    if not v:
        return default
    v = _LABEL_SAFE_RE.sub("_", v)
    v = v.strip("_")
    if not v:
        return default
    return v[: max(1, int(max_len or 1))]


def _set_meta_once(*, kind: str, suffix: str, meta: dict[str, Any], timeout: int) -> None:
    key = f"metrics:meta:{kind}:{suffix}"
    try:
        cache.add(key, json.dumps(meta, ensure_ascii=False, separators=(",", ":")), timeout=timeout)
    except Exception:
        logger.exception("操作失败")

        return


def _get_meta(*, kind: str, suffix: str) -> dict[str, Any] | None:
    key = f"metrics:meta:{kind}:{suffix}"
    raw = cache.get(key)
    if not raw:
        return None
    try:
        if isinstance(raw, str):
            return dict(json.loads(raw))
        return dict(raw)
    except Exception:
        logger.exception("操作失败")

        return None


def normalize_path_group(path: str, *, max_segments: int = 3) -> str:
    parts = [p for p in (path or "").split("/") if p]
    normalized: list[str] = []
    for p in parts[: max(1, int(max_segments or 1))]:
        if p.isdigit() or _UUID_RE.match(p) or _HEX_RE.match(p):
            normalized.append(":id")
        else:
            normalized.append(p[:64])
    return "/" + "/".join(normalized) if normalized else "/"


def _status_class(status_code: int) -> str:
    try:
        return f"{int(status_code) // 100}xx"
    except Exception:
        logger.exception("操作失败")

        return "unknown"


def _incr(key: str, delta: int, *, timeout: int) -> int:
    cache.add(key, 0, timeout=timeout)
    return int(cache.incr(key, delta))


def _add_to_index(index_key: str, value: str, *, timeout: int) -> None:
    try:
        existing = cache.get(index_key)
        if not existing:
            cache.set(index_key, json.dumps([value], ensure_ascii=False), timeout=timeout)
            return
        items = json.loads(existing) if isinstance(existing, str) else list(existing)
        if value in items:
            return
        items.append(value)
        if len(items) > 200:
            items = items[-200:]
        cache.set(index_key, json.dumps(items, ensure_ascii=False), timeout=timeout)
    except Exception:
        logger.exception("操作失败")

        return


@dataclass(frozen=True)
class Histogram:
    buckets_ms: tuple[int, ...]
    counts: dict[int, int]
    total_count: int
    total_sum_ms: int

    def quantile_ms(self, q: float) -> int:
        if self.total_count <= 0:
            return 0
        target = max(1, int(self.total_count * float(q)))
        running = 0
        for b in self.buckets_ms:
            running += int(self.counts.get(b, 0))
            if running >= target:
                return int(b)
        return int(self.buckets_ms[-1]) if self.buckets_ms else 0

    @property
    def avg_ms(self) -> float:
        if self.total_count <= 0:
            return 0.0
        return float(self.total_sum_ms) / float(self.total_count)


def _merge_histograms(histograms: list[Histogram], *, buckets_ms: tuple[int, ...]) -> Histogram:
    total_count = sum(h.total_count for h in histograms)
    total_sum_ms = sum(h.total_sum_ms for h in histograms)
    counts: dict[int, int] = {int(b): 0 for b in buckets_ms}
    for h in histograms:
        for b in buckets_ms:
            counts[int(b)] += int(h.counts.get(int(b), 0))
    return Histogram(buckets_ms=buckets_ms, counts=counts, total_count=total_count, total_sum_ms=total_sum_ms)


def record_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: int,
    window_minutes: int = 10,
    buckets_ms: tuple[int, ...] = DEFAULT_BUCKETS_MS,
) -> None:
    minute = _minute_id()
    method_u = (method or "UNKNOWN").upper()
    status_group = _status_class(status_code)
    path_group = normalize_path_group(path, max_segments=3)

    ttl = max(60, int(window_minutes or 10) * 90)
    suffix = _stable_hash({"kind": "req", "method": method_u, "status": status_group, "group": path_group})
    key_prefix = f"metrics:req:{minute}:{suffix}"

    _add_to_index(f"metrics:index:req:{minute}", suffix, timeout=ttl)
    _set_meta_once(
        kind="req",
        suffix=suffix,
        meta={"method": method_u, "status": status_group, "group": path_group},
        timeout=ttl,
    )

    _incr(f"{key_prefix}:count", 1, timeout=ttl)
    _incr(f"{key_prefix}:sum_ms", max(0, int(duration_ms or 0)), timeout=ttl)
    if int(status_code or 0) >= 500:
        _incr(f"{key_prefix}:errors_5xx", 1, timeout=ttl)

    upper = buckets_ms[-1]
    for b in buckets_ms:
        if int(duration_ms or 0) <= b:
            upper = b
            break
    _incr(f"{key_prefix}:bucket:{upper}", 1, timeout=ttl)


def record_httpx(
    *,
    host: str,
    method: str,
    status_code: int | None,
    duration_ms: int,
    window_minutes: int = 10,
    buckets_ms: tuple[int, ...] = DEFAULT_BUCKETS_MS,
) -> None:
    minute = _minute_id()
    method_u = (method or "UNKNOWN").upper()
    status_group = _status_class(int(status_code or 0)) if status_code is not None else "error"
    host_norm = (host or "unknown").split(":")[0].lower()[:128]

    ttl = max(60, int(window_minutes or 10) * 90)
    suffix = _stable_hash({"kind": "httpx", "method": method_u, "status": status_group, "host": host_norm})
    key_prefix = f"metrics:httpx:{minute}:{suffix}"

    _add_to_index(f"metrics:index:httpx:{minute}", suffix, timeout=ttl)
    _set_meta_once(
        kind="httpx",
        suffix=suffix,
        meta={"method": method_u, "status": status_group, "host": host_norm},
        timeout=ttl,
    )

    _incr(f"{key_prefix}:count", 1, timeout=ttl)
    _incr(f"{key_prefix}:sum_ms", max(0, int(duration_ms or 0)), timeout=ttl)
    if status_code is None or int(status_code) >= 500:
        _incr(f"{key_prefix}:errors_5xx", 1, timeout=ttl)

    upper = buckets_ms[-1]
    for b in buckets_ms:
        if int(duration_ms or 0) <= b:
            upper = b
            break
    _incr(f"{key_prefix}:bucket:{upper}", 1, timeout=ttl)


def record_cache_access(
    *,
    cache_kind: str,
    name: str,
    hit: bool,
    window_minutes: int = 10,
) -> None:
    record_cache_result(
        cache_kind=cache_kind,
        name=name,
        result="hit" if bool(hit) else "miss",
        window_minutes=window_minutes,
    )


def record_cache_result(
    *,
    cache_kind: str,
    name: str,
    result: str,
    window_minutes: int = 10,
) -> None:
    minute = _minute_id()
    kind_norm = _normalize_label(cache_kind, default="unknown", max_len=32)
    name_norm = _normalize_label(name, default="unknown", max_len=32)
    result_norm = _normalize_label(result, default="unknown", max_len=16)

    ttl = max(60, int(window_minutes or 10) * 90)
    suffix = _stable_hash({"kind": "cache", "cache_kind": kind_norm, "name": name_norm, "result": result_norm})
    key_prefix = f"metrics:cache:{minute}:{suffix}"

    _add_to_index(f"metrics:index:cache:{minute}", suffix, timeout=ttl)
    _set_meta_once(
        kind="cache",
        suffix=suffix,
        meta={"cache_kind": kind_norm, "name": name_norm, "result": result_norm},
        timeout=ttl,
    )
    _incr(f"{key_prefix}:count", 1, timeout=ttl)


def _load_histogram(
    *,
    minute: str,
    kind: str,
    suffix: str,
    buckets_ms: tuple[int, ...],
) -> Histogram:
    key_prefix = f"metrics:{kind}:{minute}:{suffix}"
    count = int(cache.get(f"{key_prefix}:count") or 0)
    sum_ms = int(cache.get(f"{key_prefix}:sum_ms") or 0)
    counts: dict[int, int] = {}
    for b in buckets_ms:
        counts[int(b)] = int(cache.get(f"{key_prefix}:bucket:{b}") or 0)
    return Histogram(buckets_ms=buckets_ms, counts=counts, total_count=count, total_sum_ms=sum_ms)


def _load_counter(*, minute: str, kind: str, suffix: str) -> int:
    key_prefix = f"metrics:{kind}:{minute}:{suffix}"
    return int(cache.get(f"{key_prefix}:count") or 0)


def _iter_suffixes(index_key: str) -> Iterable[str]:
    raw = cache.get(index_key)
    if not raw:
        return []
    try:
        if isinstance(raw, str):
            values = json.loads(raw)
        else:
            values = list(raw)
        return [str(v) for v in values if v]
    except Exception:
        logger.exception("操作失败")

        return []


def snapshot(
    *,
    window_minutes: int = 10,
    top: int = 10,
    buckets_ms: tuple[int, ...] = DEFAULT_BUCKETS_MS,
) -> dict[str, Any]:
    minutes = _last_minutes(window_minutes=window_minutes)
    top_n = max(1, min(int(top or 10), 50))

    req_merged, req_total = _collect_histogram_data(minutes, "req", buckets_ms)
    httpx_merged, httpx_total = _collect_histogram_data(minutes, "httpx", buckets_ms)
    cache_access_by_kind = _collect_cache_data(minutes)

    req_rows = _build_histogram_rows(req_merged, "req", ("group", "route_group"))
    httpx_rows = _build_histogram_rows(httpx_merged, "httpx", ("host", "host"))

    return {
        "window_minutes": int(window_minutes or 10),
        "requests": _histogram_summary(req_total),
        "requests_top_slowest": _top_slowest(req_rows, top_n),
        "requests_top_errors": _top_errors(req_rows, top_n),
        "httpx": _histogram_summary(httpx_total),
        "httpx_top_slowest": _top_slowest(httpx_rows, top_n),
        "httpx_top_errors": _top_errors(httpx_rows, top_n, include_error_class=True),
        "cache_access": cache_access_by_kind,
        "automation_token_cache": cache_access_by_kind.get("automation_token") or {},
    }


def _collect_histogram_data(
    minutes: list[str], kind: str, buckets_ms: tuple[int, ...]
) -> tuple[dict[str, Histogram], Histogram]:
    by_suffix: dict[str, list[Histogram]] = {}
    for m in minutes:
        for s in _iter_suffixes(f"metrics:index:{kind}:{m}"):
            by_suffix.setdefault(s, []).append(_load_histogram(minute=m, kind=kind, suffix=s, buckets_ms=buckets_ms))
    merged = {s: _merge_histograms(hs, buckets_ms=buckets_ms) for s, hs in by_suffix.items()}
    total = _merge_histograms(list(merged.values()), buckets_ms=buckets_ms)
    return merged, total


def _collect_cache_data(minutes: list[str]) -> dict[str, Any]:
    cache_by_suffix: dict[str, list[int]] = {}
    for m in minutes:
        for s in _iter_suffixes(f"metrics:index:cache:{m}"):
            cache_by_suffix.setdefault(s, []).append(_load_counter(minute=m, kind="cache", suffix=s))

    cache_access_by_kind: dict[str, Any] = {}
    for s, counts in cache_by_suffix.items():
        meta = _get_meta(kind="cache", suffix=s) or {}
        cache_kind = str(meta.get("cache_kind") or "unknown")
        name = str(meta.get("name") or "unknown")
        result = str(meta.get("result") or "miss")
        count = int(sum(int(c or 0) for c in counts))

        kind_entry = cache_access_by_kind.setdefault(
            cache_kind, {"total": 0, "hits": 0, "misses": 0, "hit_rate": 0.0, "by_name": {}}
        )
        kind_entry["total"] += count
        if result == "hit":
            kind_entry["hits"] += count
        else:
            kind_entry["misses"] += count

        name_entry = kind_entry["by_name"].setdefault(name, {"total": 0, "hits": 0, "misses": 0, "hit_rate": 0.0})
        name_entry["total"] += count
        if result == "hit":
            name_entry["hits"] += count
        else:
            name_entry["misses"] += count

    _finalize_cache_hit_rates(cache_access_by_kind)
    return cache_access_by_kind


def _finalize_cache_hit_rates(cache_access_by_kind: dict[str, Any]) -> None:
    for kind_entry in cache_access_by_kind.values():
        total = int(kind_entry.get("total") or 0)
        hits = int(kind_entry.get("hits") or 0)
        kind_entry["hit_rate"] = float(hits) / float(total) if total > 0 else 0.0
        by_name: dict[str, Any] = kind_entry.get("by_name") or {}
        for name_entry in by_name.values():
            n_total = int(name_entry.get("total") or 0)
            n_hits = int(name_entry.get("hits") or 0)
            name_entry["hit_rate"] = float(n_hits) / float(n_total) if n_total > 0 else 0.0
        kind_entry["by_name"] = sorted(
            [{"name": n, **v} for n, v in by_name.items()], key=lambda r: int(r.get("total") or 0), reverse=True
        )


def _build_histogram_rows(
    merged: dict[str, Histogram], kind: str, group_field: tuple[str, str]
) -> list[dict[str, Any]]:
    meta_key, row_key = group_field
    rows: list[dict[str, Any]] = []
    for s, h in merged.items():
        meta = _get_meta(kind=kind, suffix=s) or {}
        rows.append(
            {
                row_key: meta.get(meta_key) or "",
                "method": meta.get("method") or "",
                "status_class": meta.get("status") or "",
                "count": h.total_count,
                "avg_ms": h.avg_ms,
                "p95_ms": h.quantile_ms(0.95),
                "p99_ms": h.quantile_ms(0.99),
            }
        )
    return rows


def _histogram_summary(h: Histogram) -> dict[str, Any]:
    return {
        "count": h.total_count,
        "avg_ms": h.avg_ms,
        "p50_ms": h.quantile_ms(0.5),
        "p95_ms": h.quantile_ms(0.95),
        "p99_ms": h.quantile_ms(0.99),
    }


def _top_slowest(rows: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (float(r.get("p95_ms") or 0), int(r.get("count") or 0)), reverse=True)[:top_n]


def _top_errors(rows: list[dict[str, Any]], top_n: int, *, include_error_class: bool = False) -> list[dict[str, Any]]:
    def is_error(r: dict[str, Any]) -> bool:
        sc = str(r.get("status_class") or "")
        return sc.startswith("5") or (include_error_class and sc == "error")

    return sorted(
        [r for r in rows if is_error(r)],
        key=lambda r: (int(r.get("count") or 0), float(r.get("p95_ms") or 0)),
        reverse=True,
    )[:top_n]


def snapshot_prometheus(*, window_minutes: int = 10, buckets_ms: tuple[int, ...] = DEFAULT_BUCKETS_MS) -> str:
    s = snapshot(window_minutes=window_minutes, buckets_ms=buckets_ms)
    req = s.get("requests") or {}
    httpx = s.get("httpx") or {}
    cache_access = s.get("cache_access") or {}
    lines = [
        "# TYPE fachuan_requests_total counter",
        f"fachuan_requests_total {int(req.get('count') or 0)}",
        "# TYPE fachuan_requests_latency_ms gauge",
        f'fachuan_requests_latency_ms{{quantile="0.50"}} {int(req.get("p50_ms") or 0)}',
        f'fachuan_requests_latency_ms{{quantile="0.95"}} {int(req.get("p95_ms") or 0)}',
        f'fachuan_requests_latency_ms{{quantile="0.99"}} {int(req.get("p99_ms") or 0)}',
        "# TYPE fachuan_httpx_total counter",
        f"fachuan_httpx_total {int(httpx.get('count') or 0)}",
        "# TYPE fachuan_httpx_latency_ms gauge",
        f'fachuan_httpx_latency_ms{{quantile="0.50"}} {int(httpx.get("p50_ms") or 0)}',
        f'fachuan_httpx_latency_ms{{quantile="0.95"}} {int(httpx.get("p95_ms") or 0)}',
        f'fachuan_httpx_latency_ms{{quantile="0.99"}} {int(httpx.get("p99_ms") or 0)}',
    ]

    if cache_access:
        lines.append("# TYPE fachuan_cache_access_total counter")
    for cache_kind, kind_entry in sorted(cache_access.items(), key=lambda kv: kv[0]):
        by_name = kind_entry.get("by_name") or []
        for name_entry in by_name:
            name = str(name_entry.get("name") or "unknown")
            hits = int(name_entry.get("hits") or 0)
            misses = int(name_entry.get("misses") or 0)
            lines.append(f'fachuan_cache_access_total{{cache_kind="{cache_kind}",name="{name}",result="hit"}} {hits}')
            lines.append(
                f'fachuan_cache_access_total{{cache_kind="{cache_kind}",name="{name}",result="miss"}} {misses}'
            )
    return "\n".join(lines) + "\n"
