"""Stub: TokenService has been moved to plugins/court_automation/login/token_service.py

This file re-exports from the plugin for backward compatibility.
"""

try:
    from plugins.court_automation.login.token_service import *  # noqa: F403
    from plugins.court_automation.login.token_service import TokenService, TokenServiceAdapter

except ImportError:
    TokenService = None  # type: ignore[assignment]
    TokenServiceAdapter = None  # type: ignore[assignment]
