"""Stub: court_zxfw service has been moved to plugins/court_automation/login/court_zxfw_service.py

This file re-exports from the plugin for backward compatibility.
"""

try:
    from plugins.court_automation.login.court_zxfw_service import *  # noqa: F403
    from plugins.court_automation.login.court_zxfw_service import CourtZxfwService

except ImportError:
    CourtZxfwService = None  # type: ignore[assignment]
