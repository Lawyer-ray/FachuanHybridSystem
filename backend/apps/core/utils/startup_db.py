"""Suppress Django's startup-time DB access RuntimeWarning for intentional routines.

Django 6.1 raises ``Accessing the database during app initialization is
discouraged`` for any DB query executed while the app registry is not yet ready.

Some boot-time routines are intentionally idempotent and *must* run on every
process start (e.g. django-q schedule registration, OAuth device-code poll
recovery). They cannot be moved out of ``AppConfig.ready()``, so they need the
DB connection during initialization. This context manager scopes the warning
suppression to exactly those call sites instead of silencing it globally.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from contextlib import contextmanager

_DJANGO_STARTUP_DB_MSG = "Accessing the database during app initialization is discouraged"


@contextmanager
def allow_startup_db() -> Iterator[None]:
    """Temporarily suppress the startup-DB RuntimeWarning for intentional boot syncs."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=_DJANGO_STARTUP_DB_MSG, category=RuntimeWarning)
        yield
