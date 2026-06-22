"""Stub: http_login plugin has been moved to plugins/court_automation/login/http_login/

This file re-exports from the plugin for backward compatibility.
"""

try:
    from plugins.court_automation.login.http_login import *
    from plugins.court_automation.login.http_login import is_available

except ImportError:
    is_available = None  # type: ignore[assignment]
