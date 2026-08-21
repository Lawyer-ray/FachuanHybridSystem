#!/usr/bin/env python3
"""access_token 获取与本地缓存。"""

import json
import time

from formats import APPID, APPSECRET, TOKEN_CACHE_FILE, TOKEN_URL
from utils import client_kwargs, parse_wechat_response

_cached_token: str | None = None
_cached_expires_at: float = 0.0


def _load_disk_cache() -> tuple[str, float] | None:
    if not TOKEN_CACHE_FILE.exists():
        return None
    try:
        cache = json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
        token = cache.get("access_token")
        expires_at = cache.get("expires_at", 0)
        if token and expires_at > time.time():
            return token, expires_at
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_disk_cache(token: str, expires_in: int) -> None:
    cache = {
        "access_token": token,
        "expires_at": time.time() + expires_in - 120,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        TOKEN_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def get_access_token(force_refresh: bool = False) -> str:
    """获取 access_token：内存缓存 → 磁盘缓存 → 新请求。"""
    global _cached_token, _cached_expires_at

    if not force_refresh:
        if _cached_token and _cached_expires_at > time.time():
            return _cached_token
        disk = _load_disk_cache()
        if disk:
            _cached_token, _cached_expires_at = disk
            return _cached_token

    if not APPID or not APPSECRET:
        from pathlib import Path

        raise RuntimeError(
            "缺少 WECHAT_APPID / WECHAT_APPSECRET 环境变量，"
            f"请在 {TOKEN_CACHE_FILE.parent / '.env'} 中配置"
        )

    import httpx

    params = {"grant_type": "client_credential", "appid": APPID, "secret": APPSECRET}
    kwargs = client_kwargs(http_proxy=None, timeout=15)

    with httpx.Client(**kwargs) as client:
        resp = client.get(TOKEN_URL, params=params)
        resp.raise_for_status()
        data = parse_wechat_response(resp.json())

    token: str = data["access_token"]
    expires_in: int = data.get("expires_in", 7200)

    _cached_token = token
    _cached_expires_at = time.time() + expires_in - 120
    _save_disk_cache(token, expires_in)
    return token
