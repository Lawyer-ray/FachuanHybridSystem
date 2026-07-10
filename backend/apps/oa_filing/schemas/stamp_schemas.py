"""盖章申请 API schema。"""

from __future__ import annotations

from datetime import datetime

from ninja import Schema


class StampApplyIn(Schema):
    file_path: str
    site_name: str = "金诚同达OA"


class StampLookupOut(Schema):
    contract_id: int
    oa_case_number: str
    contract_name: str
    file_path: str


class StampSessionOut(Schema):
    id: int
    oa_case_number: str
    file_path: str
    status: str
    error_message: str
    created_at: datetime
