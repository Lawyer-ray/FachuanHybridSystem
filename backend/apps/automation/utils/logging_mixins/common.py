"""Utility functions."""

from __future__ import annotations

import logging
from typing import cast


def get_logger() -> logging.Logger:
    import importlib

    module = importlib.import_module("apps.automation.utils.logging")
    return cast(logging.Logger, module.logger)


def utc_now_iso() -> str:
    from apps.core.telemetry.time import utc_now_iso as _utc_now_iso
    from typing import cast

    return cast(str, _utc_now_iso())


def stable_hash(value: str) -> str:
    import hashlib
    import hmac

    from django.conf import settings

    v = (value or "").strip().encode("utf-8")
    secret = (getattr(settings, "SECRET_KEY", "") or "").encode("utf-8")
    digest = hmac.new(secret, v, hashlib.sha256).hexdigest()
    return digest[:32]


def mask_account(value: str, *, keep_last: int = 4) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if "@" in s:
        local, domain = s.split("@", 1)
        if len(local) <= 1:
            return f"*@{domain}"
        if len(local) == 2:
            return f"{local[0]}*@{domain}"
        return f"{local[0]}***{local[-1]}@{domain}"

    keep_last = max(0, min(int(keep_last), len(s)))
    tail = s[-keep_last:] if keep_last else ""
    return f"***{tail}"


def sanitize_url(url: str, *, max_length: int = 200) -> str:
    if not url:
        return ""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    safe_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    if len(safe_url) > max_length:
        return f"{safe_url[:max_length]}..."
    return safe_url


def normalize_cache_key_component(value: str, *, max_len: int = 64) -> str:
    import re

    raw = (value or "").strip()
    if not raw:
        return "empty"

    normalized = raw.lower()
    if re.fullmatch(r"[a-z0-9._-]+", normalized) and len(normalized) <= max_len:
        return normalized

    cleaned = re.sub(r"[^a-z0-9._-]+", "-", normalized).strip("-._")
    if not cleaned:
        cleaned = "x"

    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("-._") or "x"

    return f"{cleaned}-{stable_hash(raw)}"
