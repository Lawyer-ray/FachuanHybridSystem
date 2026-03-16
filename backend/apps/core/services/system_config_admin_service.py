"""Admin-facing helpers for system config defaults.

This compatibility service keeps legacy import paths working while delegating
to the current admin data provider.
"""

from __future__ import annotations

import re
from typing import Any

from apps.core.admin._system_config_data import get_default_configs


class SystemConfigAdminService:
    """Service facade used by tests/admin callers for default config payloads."""

    def get_default_configs(self) -> list[dict[str, Any]]:
        defaults = get_default_configs()
        sanitized: list[dict[str, Any]] = []
        for item in defaults:
            copied = dict(item)
            key = str(copied.get("key") or "")
            is_secret = bool(copied.get("is_secret", False))
            if is_secret or re.search(r"(API_KEY|APP_SECRET|SECRET|TOKEN|PASSWORD)$", key):
                copied["value"] = ""
            sanitized.append(copied)
        return sanitized
