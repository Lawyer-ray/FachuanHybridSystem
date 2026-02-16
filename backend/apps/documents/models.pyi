"""
文档模块类型存根文件

为 Django ORM 动态属性提供类型定义，解决 mypy [attr-defined] 错误。
Requirements: 3.4
"""

from datetime import datetime
from typing import Any

from django.db import models
from django.db.models import Manager, QuerySet
from django.db.models.fields.files import FieldFile

from apps.organization.models import Lawyer

class FolderTemplate(models.Model):
    # 主键
    id: int

    # 字段
    name: str
    template_type: str
    case_types: list[str]
    case_stages: list[str]
    contract_types: list[str]
    legal_statuses: list[str]
    legal_status_match_mode: str
    structure: dict[str, Any]
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # 反向关系
    document_bindings: Manager[DocumentTemplateFolderBinding]

    # Meta
    objects: Manager[FolderTemplate]

    def __str__(self) -> str: ...
    @property
    def template_type_display(self) -> str: ...
    @property
    def case_types_display(self) -> str: ...
    @property
    def case_stages_display(self) -> str: ...
    @property
    def contract_types_display(self) -> str: ...
    @property
    def case_type(self) -> str | None: ...
    @property
    def case_stage(self) -> str | None: ...
    @property
    def legal_statuses_display(self) -> str: ...
    def get_legal_statuses_display(self) -> str: ...
    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]: ...

class DocumentTemplate(models.Model):
    # 主键
    id: int

    # 字段
    name: str
    description: str
    template_type: str
    contract_sub_type: str | None
    case_sub_type: str | None
    file: FieldFile
    file_path: str
    case_types: list[str]
    case_stages: list[str]
    contract_types: list[str]
    legal_statuses: list[str]
    legal_status_match_mode: str
    function_code: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # 反向关系
    folder_bindings: Manager[DocumentTemplateFolderBinding]
    evidence_lists: Manager[EvidenceList]

    # Meta
    objects: Manager[DocumentTemplate]

    def __str__(self) -> str: ...
    def clean(self) -> None: ...
    def get_file_location(self) -> str: ...
    @property
    def template_type_display(self) -> str: ...
    @property
    def case_types_display(self) -> str: ...
    @property
    def case_stages_display(self) -> str: ...
    @property
    def contract_types_display(self) -> str: ...
    def get_legal_statuses_display(self) -> str: ...
    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]: ...

class DocumentTemplateFolderBinding(models.Model):
    # 主键
    id: int

    # 字段
    document_template_id: int
    document_template: DocumentTemplate
    folder_template_id: int
    folder_template: FolderTemplate
    folder_node_id: str
    folder_node_path: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Meta
    objects: Manager[DocumentTemplateFolderBinding]

    def __str__(self) -> str: ...

class EvidenceList(models.Model):
    # 主键
    id: int

    # 字段
    case_id: int
    case: Any  # cases.Case
    list_type: str
    previous_list_id: int | None
    previous_list: EvidenceList | None
    title: str
    order: int
    merged_pdf: FieldFile
    total_pages: int
    export_version: int
    merge_status: str
    merge_error: str
    merge_started_at: datetime | None
    merge_finished_at: datetime | None
    merge_progress: int
    merge_current: int
    merge_total: int
    merge_message: str
    export_template_id: int | None
    export_template: DocumentTemplate | None
    created_by_id: int | None
    created_by: Lawyer | None
    created_at: datetime
    updated_at: datetime

    # 反向关系
    items: Manager[EvidenceItem]
    next_lists: Manager[EvidenceList]

    # Meta
    objects: Manager[EvidenceList]

    def __str__(self) -> str: ...
    @property
    def start_order(self) -> int: ...
    @property
    def start_page(self) -> int: ...
    @property
    def end_page(self) -> int: ...
    @property
    def page_range_display(self) -> str: ...
    @property
    def order_range_display(self) -> str: ...

class EvidenceItem(models.Model):
    # 主键
    id: int

    # 字段
    evidence_list_id: int
    evidence_list: EvidenceList
    order: int
    name: str
    purpose: str
    file: FieldFile
    file_name: str
    file_size: int
    page_count: int
    page_start: int | None
    page_end: int | None
    ai_analysis: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    # Meta
    objects: Manager[EvidenceItem]

    def __str__(self) -> str: ...
    @property
    def page_range_display(self) -> str: ...
    @property
    def file_size_display(self) -> str: ...

class GenerationTask(models.Model):
    # 主键
    id: int

    # 字段
    case_id: int | None
    case: Any  # cases.Case
    contract_id: int | None
    contract: Any  # contracts.Contract
    litigation_session_id: int | None
    litigation_session: Any  # litigation_ai.LitigationSession
    generation_method: str
    document_type: str
    template_id: int | None
    status: str
    result_file: FieldFile
    error_message: str
    metadata: dict[str, Any]
    created_by_id: int | None
    created_by: Lawyer | None
    created_at: datetime
    completed_at: datetime | None

    # Meta
    objects: Manager[GenerationTask]

    def __str__(self) -> str: ...
    def get_status_display(self) -> str: ...
    @property
    def is_ai_generated(self) -> bool: ...
    @property
    def duration_seconds(self) -> int: ...
    @property
    def folder_template_id(self) -> int | None: ...
    @folder_template_id.setter
    def folder_template_id(self, value: int | None) -> None: ...
    @property
    def folder_template(self) -> FolderTemplate | None: ...
    @property
    def output_path(self) -> str | None: ...
    @output_path.setter
    def output_path(self, value: str | None) -> None: ...
    @property
    def generated_files(self) -> list[str]: ...
    @generated_files.setter
    def generated_files(self, value: list[str] | None) -> None: ...
    @property
    def error_logs(self) -> list[str]: ...
    @error_logs.setter
    def error_logs(self, value: list[str] | None) -> None: ...

class GenerationConfig(models.Model):
    # 主键
    id: int

    # 字段
    name: str
    config_type: str
    value: dict[str, Any]
    description: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Meta
    objects: Manager[GenerationConfig]

    def __str__(self) -> str: ...
    @property
    def case_type(self) -> str | None: ...
    @property
    def case_stage(self) -> str | None: ...
    @property
    def document_template_id(self) -> int | None: ...
    @property
    def folder_path(self) -> str | None: ...
    @property
    def priority(self) -> int: ...
    @property
    def condition(self) -> dict[str, Any]: ...

class TemplateAuditLog(models.Model):
    # 主键
    id: int

    # 字段
    template_id: int
    action: str
    actor_id: int | None
    actor: Lawyer | None
    changes: dict[str, Any]
    created_at: datetime

    # Meta
    objects: Manager[TemplateAuditLog]

class Placeholder(models.Model):
    # 主键
    id: int

    # 字段
    key: str
    name: str
    category: str
    format_type: str
    description: str
    example: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Meta
    objects: Manager[Placeholder]

class PromptVersion(models.Model):
    # 主键
    id: int

    # 字段
    name: str
    version: str
    prompt_text: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Meta
    objects: Manager[PromptVersion]

class ProxyMatterRule(models.Model):
    # 主键
    id: int

    # 字段
    case_type: str
    case_stage: str
    legal_status: str
    matters: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Meta
    objects: Manager[ProxyMatterRule]
