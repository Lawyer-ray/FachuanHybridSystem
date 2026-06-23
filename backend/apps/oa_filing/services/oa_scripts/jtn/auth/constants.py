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
from pathlib import Path

_COOKIE_PATH = Path.home() / ".fachuan" / "jtn_cookies.json"
