from __future__ import annotations

from datetime import datetime

from ninja import Schema


class ExecuteFilingIn(Schema):
    oa_config_id: int
    contract_id: int
    case_id: int


class SessionOut(Schema):
    id: int
    status: str
    error_message: str
    created_at: datetime


class OAConfigOut(Schema):
    id: int
    oa_system_name: str
    has_credential: bool
