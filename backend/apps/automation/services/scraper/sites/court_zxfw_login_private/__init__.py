"""Stub: http_login plugin has been moved to plugins/court_automation/login/http_login/

This file re-exports from the plugin for backward compatibility.
"""

try:
    from plugins.court_automation.login.http_login import *
    from plugins.court_automation.login.http_login import CourtZxfwHttpLoginService, is_available

except ImportError:  # CI/类型检查环境无 plugins 子模块
    is_available = None  # type: ignore[assignment]
    CourtZxfwHttpLoginService = None  # type: ignore[assignment,misc]
