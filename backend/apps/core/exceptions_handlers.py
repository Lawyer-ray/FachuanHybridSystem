"""
兼容层 - 已废弃，请使用 apps.core.exceptions.handlers

Deprecated: This module is a compatibility shim.
Use `from apps.core.exceptions import register_exception_handlers` instead.
"""
# DEPRECATED: This file is a compatibility shim for backward compatibility.
# All exception handlers have been migrated to apps.core.exceptions.handlers.
# This file will be removed in a future version.

from apps.core.exceptions.handlers import register_exception_handlers as register_exception_handlers

__all__ = ["register_exception_handlers"]
