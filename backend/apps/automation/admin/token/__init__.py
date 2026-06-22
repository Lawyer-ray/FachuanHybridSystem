"""Stub: Token admin modules have been moved to plugins/court_automation/token_admin/

This file re-exports from the plugin for backward compatibility.
"""

try:
    from plugins.court_automation.token_admin import *
    from plugins.court_automation.token_admin import CourtTokenAdmin, TokenAcquisitionHistoryAdmin

except ImportError:
    CourtTokenAdmin = None  # type: ignore[assignment]
    TokenAcquisitionHistoryAdmin = None  # type: ignore[assignment]
