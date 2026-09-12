"""金诚同达 OA 利益冲突信息预检页面自动化。"""

from __future__ import annotations

from .playwright_conflict_check import PlaywrightConflictCheckMixin
from .service import JtnConflictCheckScript

__all__ = ["JtnConflictCheckScript"]
