"""Stub: CookieService has been moved to plugins/court_automation/login/cookie_service.py

This file re-exports from the plugin for backward compatibility.
"""

try:
    from plugins.court_automation.login.cookie_service import *  # noqa: F403
    from plugins.court_automation.login.cookie_service import CookieService

except ImportError:
    CookieService = None  # type: ignore[assignment]
