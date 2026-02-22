"""Module for scrub."""

from __future__ import annotations

import hashlib
import re
from typing import Any

_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9]{12,})"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{12,})"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(token\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(authorization\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(password\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(secret\s*[:=]\s*)(\S+)"),
]

_LIKELY_TOKEN_PATTERNS = [
    re.compile(r"^(sk-[A-Za-z0-9]{12,})$"),
    re.compile(r"^[A-Za-z0-9._\-]{24,}$"),
]

_SENSITIVE_ATTR_NAMES = {
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "app_secret",
    "client_secret",
    "account",
}


def _mask_match(match: re.Match[str]) -> str:
    groups = match.groups()
    if len(groups) == 2:
        return groups[0] + mask_secret(groups[1])
    return mask_secret(groups[0])


def is_sensitive_key_name(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in ("token", "key", "secret", "password", "auth", "credential"))


def looks_like_token(value: str) -> bool:
    return any(p.match(value) for p in _LIKELY_TOKEN_PATTERNS)


def mask_value_for_key(key: str, value: Any) -> Any:
    if isinstance(value, str):
        return mask_secret(value)
    return value


def fingerprint_sha256(value: str) -> str:
    v = (value or "").encode("utf-8")
    return hashlib.sha256(v).hexdigest()


def mask_secret(secret: str) -> str:
    s = str(secret)
    if len(s) <= 6:
        return "***"
    return s[:2] + "***" + s[-2:]


def scrub_text(text: str) -> str:
    value = text
    for pattern in _PATTERNS:
        value = pattern.sub(_mask_match, value)
    return value


def scrub_obj(obj: Any, *, key_hint: str = "", depth: int = 0) -> Any:
    if depth >= 6:
        return obj

    if obj is None:
        return obj

    if isinstance(obj, str):
        if looks_like_token(obj) or is_sensitive_key_name(key_hint):
            return mask_secret(obj)
        return scrub_text(obj)

    if isinstance(obj, dict):
        scrubbed: dict[Any, Any] = {}
        for k, v in obj.items():
            key_name = str(k).lower() if k is not None else ""
            if key_name in _SENSITIVE_ATTR_NAMES or is_sensitive_key_name(key_name):
                scrubbed[k] = mask_value_for_key(key_name, v)
            else:
                scrubbed[k] = scrub_obj(v, key_hint=key_name, depth=depth + 1)
        return scrubbed

    if isinstance(obj, list):
        return [scrub_obj(v, key_hint=key_hint, depth=depth + 1) for v in obj]

    if isinstance(obj, tuple):
        return tuple(scrub_obj(v, key_hint=key_hint, depth=depth + 1) for v in obj)

    return obj


def scrub_for_storage(value: Any) -> Any:
    return scrub_obj(value, key_hint="", depth=0)
