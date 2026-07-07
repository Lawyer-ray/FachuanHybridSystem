from __future__ import annotations

from ninja import Router

from .archive_api import router as archive_router
from .case_import_api import router as case_import_router
from .filing_api import router as filing_router
from .stamp_api import router as stamp_router

router = Router()
router.add_router("", filing_router, tags=["OA立案"])
router.add_router("/case-import", case_import_router, tags=["案件导入"])
router.add_router("/oa-stamp", stamp_router, tags=["OA盖章"])
router.add_router("/oa-archive", archive_router, tags=["OA归档"])

__all__: list[str] = ["router"]
