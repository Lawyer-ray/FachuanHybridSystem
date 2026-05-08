"""Contacts App API 模块."""

from __future__ import annotations

from ninja import Router

from .contact_api import router as contact_router

router = Router()
router.add_router("", contact_router, tags=["案件工作人员"])

__all__ = ["router"]
