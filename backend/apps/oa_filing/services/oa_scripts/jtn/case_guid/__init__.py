"""金诚同达 OA 案号查 GUID（案件选择对话框 GET 搜索，纯 HTTP 只读）。"""

from __future__ import annotations

from ..http_session import is_oa_login_page
from .service import JtnCaseGuidScript, dialog_search_url, extract_dialog_guids

__all__ = [
    "JtnCaseGuidScript",
    "dialog_search_url",
    "extract_dialog_guids",
    "is_oa_login_page",
]
