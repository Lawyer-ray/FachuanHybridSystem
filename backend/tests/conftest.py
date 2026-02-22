"""
Root conftest.py — Django 6 compatibility fixes for async test connections.
"""

import os
from typing import Any

from django.db.backends.base.base import BaseDatabaseWrapper

_original_connect = BaseDatabaseWrapper.connect

_CONNECTION_DEFAULTS: dict[str, Any] = {
    "ATOMIC_REQUESTS": False,
    "AUTOCOMMIT": True,
    "CONN_MAX_AGE": 0,
    "CONN_HEALTH_CHECKS": False,
    "OPTIONS": {},
    "TIME_ZONE": None,
}


def _patched_connect(self: BaseDatabaseWrapper) -> None:
    """Ensure all required keys exist in settings_dict before connect().

    Django 6 reads settings_dict keys directly in connect(), but async worker
    threads may get a fresh connection object whose settings_dict was not
    processed by ensure_defaults().
    """
    sd = self.settings_dict
    for key, default in _CONNECTION_DEFAULTS.items():
        if key not in sd:
            sd[key] = default
    _original_connect(self)


BaseDatabaseWrapper.connect = _patched_connect  # type: ignore[method-assign]

# 测试环境下允许在 async 上下文中调用同步 ORM，避免 SynchronousOnlyOperation
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
