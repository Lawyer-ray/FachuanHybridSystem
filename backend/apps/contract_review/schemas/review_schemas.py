from __future__ import annotations

from typing import Literal
from uuid import UUID

from ninja import Schema


class ConfirmPartyIn(Schema):
    represented_party: Literal["party_a", "party_b", "party_c", "party_d"]
    reviewer_name: str = ""
    selected_steps: list[str] = []


class TaskCreatedOut(Schema):
    task_id: UUID
    status: str
    contract_title: str | None = None
    parties: dict[str, str] = {}


class TaskStatusOut(Schema):
    task_id: UUID
    status: str
    current_step: str | None = None
    error_message: str | None = None
    output_filename: str | None = None
