"""API schemas and serializers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ninja import ModelSchema, Schema
from pydantic import field_validator

from apps.cases.models import (
    Case,
    CaseAccessGrant,
    CaseAssignment,
    CaseFolderBinding,
    CaseLog,
    CaseLogAttachment,
    CaseNumber,
    CaseParty,
    SupervisingAuthority,
)
from apps.core.api.schemas import SchemaMixin
from apps.core.api.schemas_shared import ClientIdentityDocLiteOut as ClientIdentityDocOut
from apps.core.api.schemas_shared import ClientLiteOut as ClientOut
from apps.core.api.schemas_shared import ReminderLiteOut as ReminderOut

__all__: list[str] = [
    "Any",
    "Case",
    "CaseAccessGrant",
    "CaseAssignment",
    "CaseFolderBinding",
    "CaseLog",
    "CaseLogAttachment",
    "CaseNumber",
    "CaseParty",
    "ClientIdentityDocOut",
    "ClientOut",
    "ModelSchema",
    "ReminderOut",
    "Schema",
    "SchemaMixin",
    "SupervisingAuthority",
    "datetime",
    "field_validator",
]
