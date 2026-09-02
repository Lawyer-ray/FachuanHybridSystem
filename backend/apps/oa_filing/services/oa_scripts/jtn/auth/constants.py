"""金诚同达 OA 公共常量。

所有子模块（filing / case_import / client_import）共享的常量集中在此，
避免重复定义。
"""

from __future__ import annotations

# ============================================================
# URL
# ============================================================
_LOGIN_URL = "https://ims.jtn.com/member/login.aspx"

# ============================================================
# HTTP
# ============================================================
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_DEFAULT_HTTP_TIMEOUT = 20

# ============================================================
# Cookie 持久化
# ============================================================
import re
from pathlib import Path


def cookie_path(account: str) -> Path:
    """返回指定金诚同达账号专属的 cookie 缓存文件路径。

    Cookie 缓存必须按 OA 账号隔离，避免不同律师复用彼此的登录态。
    """
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", account or "")
    return Path.home() / ".fachuan" / f"jtn_cookies_{safe or 'default'}.json"
