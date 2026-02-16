"""Module for documents."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentTemplateDTO:
    id: int
    name: str
    function_code: str
    file_path: str | None = None
    template_type: str | None = None
    case_sub_type: str | None = None
    case_types: list[str] = field(default_factory=list)
    case_stages: list[str] = field(default_factory=list)
    legal_statuses: list[str] = field(default_factory=list)
    legal_status_match_mode: str | None = None
    case_type: str | None = None
    is_active: bool = True
    description: str | None = None


@dataclass
class GenerationTaskDTO:
    id: int
    status: str
    created_at: Any
    created_by_id: int | None = None
    document_name: str | None = None
    document_url: str | None = None


@dataclass
class EvidenceItemDigestDTO:
    id: int
    order: int
    name: str
    purpose: str
    page_start: int | None = None
    page_end: int | None = None
    file_path: str | None = None
