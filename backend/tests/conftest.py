"""
Root conftest.py — Django 6 compatibility fixes for async test connections.
"""
from django.db.backends.base.base import BaseDatabaseWrapper

_original_connect = BaseDatabaseWrapper.connect

_CONNECTION_DEFAULTS: dict = {
    "ATOMIC_REQUESTS": False,
    "AUTOCOMMIT": True,
    "CONN_MAX_AGE": 0,
    "CONN_HEALTH_CHECKS": False,
    "OPTIONS": {},
    "TIME_ZONE": None,
}


def _patched_connect(self: BaseDatabaseWrapper) -> None:  # type: ignore[override]
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
