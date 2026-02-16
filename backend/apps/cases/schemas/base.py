"""API schemas and serializers."""

from datetime import datetime
from typing import Any, Optional

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
from apps.core.schemas import SchemaMixin
from apps.core.schemas_shared import ClientIdentityDocLiteOut as ClientIdentityDocOut
from apps.core.schemas_shared import ClientLiteOut as ClientOut
from apps.core.schemas_shared import ReminderLiteOut as ReminderOut

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
    "Optional",
    "ReminderOut",
    "Schema",
    "SchemaMixin",
    "SupervisingAuthority",
    "datetime",
    "field_validator",
]
