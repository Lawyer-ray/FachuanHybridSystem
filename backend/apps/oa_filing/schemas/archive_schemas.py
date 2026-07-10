"""归档材料提交 API schema。"""

from __future__ import annotations

from datetime import datetime

from ninja import Schema


class ArchiveApplyIn(Schema):
    file_paths: list[str]
    site_name: str = "金诚同达OA"


class OpenOAIn(Schema):
    contract_id: int
    description: str = "详见卷宗"
    site_name: str = "金诚同达OA"


class ArchiveLookupOut(Schema):
    contract_id: int
    oa_case_number: str
    contract_name: str
    file_path: str


class ArchiveSessionOut(Schema):
    id: int
    oa_case_number: str
    file_paths: list[str]
    status: str
    error_message: str
    created_at: datetime
