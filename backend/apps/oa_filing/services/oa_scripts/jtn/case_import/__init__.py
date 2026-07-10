"""金诚同达 OA 案件导入脚本（包）。"""

from __future__ import annotations

# re-export 数据结构（保持外部 import 兼容）
from .models import (
    CaseListFormState,
    CaseSearchItem,
    OACaseCustomerData,
    OACaseData,
    OACaseInfoData,
    OAConflictData,
    OAListCaseCandidate,
)

# re-export facade
from .service import JtnCaseImportScript

__all__ = [
    "JtnCaseImportScript",
    "OAConflictData",
    "OACaseCustomerData",
    "OACaseData",
    "OACaseInfoData",
    "OAListCaseCandidate",
    "CaseListFormState",
    "CaseSearchItem",
]
