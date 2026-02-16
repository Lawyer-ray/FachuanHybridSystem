"""
案件模块类型存根文件

为 Django ORM 动态属性提供类型定义，解决 mypy [attr-defined] 错误。
Requirements: 3.4
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db import models
from django.db.models import Manager, QuerySet
from django.db.models.fields.files import FieldFile

from apps.client.models import Client
from apps.contracts.models import Contract
from apps.core.enums import (
    AuthorityType,
    CaseLogReminderType,
    CaseStage,
    CaseStatus,
    CaseType,
    ChatPlatform,
    LegalStatus,
    SimpleCaseType,
)
from apps.organization.models import Lawyer

# 重新导出枚举（向后兼容）
__all__ = [
    "CaseStage",
    "CaseStatus",
    "CaseType",
    "LegalStatus",
    "SimpleCaseType",
    "Case",
    "CaseNumber",
    "SupervisingAuthority",
    "CaseParty",
    "CaseAssignment",
    "CaseAccessGrant",
    "CaseLog",
    "CaseLogAttachment",
    "CaseLogVersion",
    "CaseChat",
    "ChatAuditLog",
    "CaseMaterialCategory",
    "CaseMaterialSide",
    "CaseMaterialType",
    "CaseMaterial",
    "CaseMaterialGroupOrder",
    "CaseFolderBinding",
    "BindingSource",
    "CaseTemplateBinding",
]

class Case(models.Model):
    # 主键
    id: int

    # 字段
    contract_id: int | None
    contract: Contract | None
    is_archived: bool
    name: str
    status: str
    start_date: date
    effective_date: date | None
    cause_of_action: str | None
    target_amount: Decimal | None
    case_type: str | None
    current_stage: str | None

    # 反向关系
    case_numbers: Manager[CaseNumber]
    supervising_authorities: Manager[SupervisingAuthority]
    parties: Manager[CaseParty]
    assignments: Manager[CaseAssignment]
    access_grants: Manager[CaseAccessGrant]
    logs: Manager[CaseLog]
    chats: Manager[CaseChat]
    chat_audit_logs: Manager[ChatAuditLog]
    evidence_lists: Manager[Any]  # documents.EvidenceList
    generation_tasks: Manager[Any]  # documents.GenerationTask

    # Meta
    objects: Manager[Case]

    def __str__(self) -> str: ...
    def clean(self) -> None: ...
    def get_status_display(self) -> str | None: ...
    def get_current_stage_display(self) -> str | None: ...

class CaseNumber(models.Model):
    # 主键
    id: int

    # 字段
    case_id: int
    case: Case
    number: str
    remarks: str | None
    created_at: datetime

    # Meta
    objects: Manager[CaseNumber]

    def __str__(self) -> str: ...
    def save(self, *args: Any, **kwargs: Any) -> None: ...

class SupervisingAuthority(models.Model):
    # 主键
    id: int

    # 字段
    case_id: int
    case: Case
    name: str | None
    authority_type: str | None
    created_at: datetime

    # Meta
    objects: Manager[SupervisingAuthority]

    def __str__(self) -> str: ...
    def get_authority_type_display(self) -> str: ...

class CaseParty(models.Model):
    # 主键
    id: int

    # 字段
    case_id: int
    case: Case
    client_id: int
    client: Client
    legal_status: str | None

    # Meta
    objects: Manager[CaseParty]

    def __str__(self) -> str: ...
    def get_legal_status_display(self) -> str | None: ...

class CaseAssignment(models.Model):
    # 主键
    id: int

    # 字段
    case_id: int
    case: Case
    lawyer_id: int
    lawyer: Lawyer

    # Meta
    objects: Manager[CaseAssignment]

    def __str__(self) -> str: ...

class CaseAccessGrant(models.Model):
    # 主键
    id: int

    # 字段
    case_id: int
    case: Case
    grantee_id: int
    grantee: Lawyer
    created_at: datetime

    # Meta
    objects: Manager[CaseAccessGrant]

    def __str__(self) -> str: ...

class CaseLog(models.Model):
    # 主键
    id: int

    # 字段
    case_id: int
    case: Case
    content: str
    reminder_type: str | None
    reminder_time: datetime | None
    actor_id: int
    actor: Lawyer
    created_at: datetime
    updated_at: datetime

    # 反向关系
    attachments: Manager[CaseLogAttachment]
    versions: Manager[CaseLogVersion]
    reminders: Manager[Any]  # reminders.Reminder

    # Meta
    objects: Manager[CaseLog]

    def __str__(self) -> str: ...

class CaseLogAttachment(models.Model):
    # 主键
    id: int

    # 字段
    log_id: int
    log: CaseLog
    file: FieldFile
    uploaded_at: datetime

    # Meta
    objects: Manager[CaseLogAttachment]

class CaseLogVersion(models.Model):
    # 主键
    id: int

    # 字段
    log_id: int
    log: CaseLog
    content: str
    version_at: datetime
    actor_id: int
    actor: Lawyer

    # Meta
    objects: Manager[CaseLogVersion]

    def __str__(self) -> str: ...

class CaseChat(models.Model):
    # 主键
    id: int

    # 字段
    case_id: int
    case: Case
    platform: str
    chat_id: str
    name: str
    is_active: bool
    owner_id: str | None
    owner_verified: bool
    owner_verified_at: datetime | None
    creation_audit_log: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    # 反向关系
    audit_logs: Manager[ChatAuditLog]

    # Meta
    objects: Manager[CaseChat]

    def __str__(self) -> str: ...
    def get_platform_display(self) -> str: ...
    def get_owner_display(self) -> str: ...
    def is_owner_verified_recently(self, hours: int = 24) -> bool: ...
    def get_creation_summary(self) -> str: ...
    def update_owner_verification(self, verified: bool = True, save: bool = True) -> None: ...
    def add_creation_audit_entry(self, action: str, details: dict[str, Any], save: bool = True) -> None: ...

class ChatAuditLog(models.Model):
    # 主键
    id: int

    # 字段
    chat_id: int | None
    chat: CaseChat | None
    case_id: int | None
    case: Case | None
    action: str
    details: dict[str, Any]
    timestamp: datetime
    success: bool
    error_message: str
    external_chat_id: str
    platform: str
    audit_version: str

    # Meta
    objects: Manager[ChatAuditLog]

    def __str__(self) -> str: ...
    def get_action_display(self) -> str: ...
    def get_formatted_details(self) -> str: ...
    def get_summary(self) -> str: ...
    def is_recent(self, hours: int = 24) -> bool: ...

# Material models
class CaseMaterialCategory(models.TextChoices):
    PARTY: str
    NON_PARTY: str

class CaseMaterialSide(models.TextChoices):
    OUR: str
    OPPONENT: str

class CaseMaterialType(models.Model):
    id: int
    category: str
    name: str
    law_firm_id: int | None
    is_active: bool
    created_at: datetime

    objects: Manager[CaseMaterialType]

    def __str__(self) -> str: ...
    def get_category_display(self) -> str: ...

class CaseMaterial(models.Model):
    id: int
    case_id: int
    case: Case
    category: str
    type_id: int | None
    type: CaseMaterialType | None
    type_name: str
    source_attachment_id: int | None
    side: str | None
    supervising_authority_id: int | None
    supervising_authority: SupervisingAuthority | None
    created_at: datetime

    objects: Manager[CaseMaterial]

    def __str__(self) -> str: ...
    def get_category_display(self) -> str: ...
    def get_side_display(self) -> str: ...

class CaseMaterialGroupOrder(models.Model):
    id: int
    case_id: int
    case: Case
    category: str
    side: str | None
    supervising_authority_id: int | None
    supervising_authority: SupervisingAuthority | None
    type_id: int
    type: CaseMaterialType
    sort_index: int

    objects: Manager[CaseMaterialGroupOrder]

    def __str__(self) -> str: ...

class CaseFolderBinding(models.Model):
    id: int
    case_id: int
    case: Case
    folder_path: str
    created_at: datetime
    updated_at: datetime

    objects: Manager[CaseFolderBinding]

    def __str__(self) -> str: ...
    @property
    def folder_path_display(self) -> str: ...

# Template binding models
class BindingSource(models.TextChoices):
    AUTO_RECOMMENDED: str
    MANUAL_BOUND: str

class CaseTemplateBinding(models.Model):
    id: int
    case_id: int
    case: Case
    template_id: int
    binding_source: str
    created_at: datetime

    objects: Manager[CaseTemplateBinding]

    def __str__(self) -> str: ...
    def get_binding_source_display(self) -> str: ...
