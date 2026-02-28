from __future__ import annotations

from ninja import Router

from .filing_api import router as filing_router

router = Router()
router.add_router("", filing_router, tags=["OA立案"])

__all__: list[str] = ["router"]
