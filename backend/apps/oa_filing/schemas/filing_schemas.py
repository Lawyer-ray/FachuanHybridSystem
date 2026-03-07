from __future__ import annotations

from datetime import datetime

from ninja import Schema


class ExecuteFilingIn(Schema):
    site_name: str
    contract_id: int
    case_id: int | None = None


class SessionOut(Schema):
    id: int
    status: str
    error_message: str
    created_at: datetime


class OAConfigOut(Schema):
    id: str
    oa_system_name: str
    has_credential: bool
