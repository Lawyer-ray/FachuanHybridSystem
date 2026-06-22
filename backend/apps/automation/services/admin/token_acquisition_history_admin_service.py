"""Stub: TokenAcquisitionHistoryAdminService has been moved to plugins/court_automation/token_admin/token_acquisition_history_admin_service.py

This file re-exports from the plugin for backward compatibility.
"""

try:
    from plugins.court_automation.token_admin.token_acquisition_history_admin_service import *  # noqa: F403
    from plugins.court_automation.token_admin.token_acquisition_history_admin_service import TokenAcquisitionHistoryAdminService

except ImportError:
    TokenAcquisitionHistoryAdminService = None  # type: ignore[assignment]
