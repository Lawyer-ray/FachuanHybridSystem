"""API Key 池管理。"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from django.core.cache import cache

_PREFERRED_KEY_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
_AUTH_BLOCK_TTL_SECONDS = 60 * 60
_RATE_LIMIT_BLOCK_TTL_SECONDS = 2 * 60


class McpApiKeyPool:
    """为同一 provider 管理多个 API Key 的优先级与短期熔断。"""

    def __init__(self, *, provider_name: str, api_keys: Iterable[str]) -> None:
        self._provider_name = str(provider_name or "").strip().lower()
        self._api_keys = self._normalize_api_keys(api_keys)

    @property
    def size(self) -> int:
        return len(self._api_keys)

    def ordered_keys(self) -> list[str]:
        if len(self._api_keys) <= 1:
            return list(self._api_keys)

        preferred = str(cache.get(self._preferred_cache_key()) or "").strip()
        available = [key for key in self._api_keys if not self._is_blocked(key)]
        blocked = [key for key in self._api_keys if self._is_blocked(key)]
        ordered_available = self._order_with_preferred(available, preferred)
        ordered_blocked = self._order_with_preferred(blocked, preferred)
        return ordered_available + ordered_blocked

    def mark_success(self, api_key: str) -> None:
        fingerprint = self.fingerprint(api_key)
        if not fingerprint:
            return
        cache.set(self._preferred_cache_key(), fingerprint, timeout=_PREFERRED_KEY_CACHE_TTL_SECONDS)
        cache.delete(self._block_cache_key(api_key))

    def mark_auth_failed(self, api_key: str) -> None:
        self._block(api_key, ttl_seconds=_AUTH_BLOCK_TTL_SECONDS)

    def mark_rate_limited(self, api_key: str) -> None:
        self._block(api_key, ttl_seconds=_RATE_LIMIT_BLOCK_TTL_SECONDS)

    def fingerprint(self, api_key: str) -> str:
        normalized = str(api_key or "").strip()
        if not normalized:
            return ""
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return digest[:16]

    @staticmethod
    def _normalize_api_keys(api_keys: Iterable[str]) -> tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in api_keys:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            normalized.append(value)
            seen.add(value)
        return tuple(normalized)

    def _block(self, api_key: str, *, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        cache.set(self._block_cache_key(api_key), True, timeout=ttl_seconds)

    def _is_blocked(self, api_key: str) -> bool:
        return bool(cache.get(self._block_cache_key(api_key)))

    def _preferred_cache_key(self) -> str:
        return f"enterprise_data:api_key_pool:{self._provider_name}:preferred"

    def _block_cache_key(self, api_key: str) -> str:
        return f"enterprise_data:api_key_pool:{self._provider_name}:blocked:{self.fingerprint(api_key)}"

    def _order_with_preferred(self, keys: list[str], preferred_fingerprint: str) -> list[str]:
        if len(keys) <= 1 or not preferred_fingerprint:
            return list(keys)
        for index, key in enumerate(keys):
            if self.fingerprint(key) != preferred_fingerprint:
                continue
            return [keys[index], *keys[:index], *keys[index + 1 :]]
        return list(keys)
