from __future__ import annotations

from ninja import Router

from .case_import_api import router as case_import_router
from .filing_api import router as filing_router

router = Router()
router.add_router("", filing_router, tags=["OA立案"])
router.add_router("/case-import", case_import_router, tags=["案件导入"])

__all__: list[str] = ["router"]
