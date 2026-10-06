"""金诚同达 OA 案号查 GUID（案件管理页搜索，纯 HTTP 只读）。"""

from __future__ import annotations

from ..http_session import is_oa_login_page
from .service import JtnCaseGuidScript, extract_case_guids, extract_viewstate_fields

__all__ = [
    "JtnCaseGuidScript",
    "extract_case_guids",
    "extract_viewstate_fields",
    "is_oa_login_page",
]
