"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


def is_jwt_like(token: str) -> bool:
    s = (token or "").strip()
    return s.startswith("eyJ") and s.count(".") >= 2


def is_hs512_jwt(token: str) -> bool:
    s = (token or "").strip()
    return s.startswith("eyJhbGciOiJIUzUxMiJ9")


def extract_token_from_url_query(url: str, *, param: str = "token") -> str | None | None:
    try:
        parsed = urlparse(url or "")
        params = parse_qs(parsed.query)
        token = params.get(param, [None])[0]
        token = token.strip() if isinstance(token, str) else None
        return token or None
    except Exception:
        logger.exception("操作失败")

        return None


def extract_login_token_from_json(payload: Any) -> str | None | None:
    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    if isinstance(data, dict):
        token = data.get("token") or data.get("access_token") or data.get("accessToken")
        if isinstance(token, str) and token.strip():
            return token.strip()

    token = payload.get("token") or payload.get("access_token") or payload.get("accessToken")
    if isinstance(token, str) and token.strip():
        return token.strip()

    if isinstance(data, str) and data.strip():
        return data.strip()

    result = payload.get("result")
    if isinstance(result, dict):
        token = result.get("token") or result.get("access_token") or result.get("accessToken")
        if isinstance(token, str) and token.strip():
            return token.strip()

    return None


def extract_baoquan_token_from_authorization_json(payload: Any) -> str | None | None:
    token = extract_login_token_from_json(payload)
    if token and is_hs512_jwt(token):
        return token
    return None
