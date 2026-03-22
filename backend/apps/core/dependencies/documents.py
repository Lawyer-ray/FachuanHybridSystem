"""Module for documents."""

from __future__ import annotations

"""文档依赖聚合入口 — 按功能拆分为 query / generation 子模块,此文件保留为 re-export 入口."""


from .documents_generation import (
    build_contract_generation_service,
    build_contract_generation_service_with_deps,
    build_generation_task_service,
    build_supplementary_agreement_generation_service,
    build_supplementary_agreement_generation_service_with_deps,
)
from .documents_query import (
    build_document_service,
    build_document_template_binding_service,
    build_evidence_list_placeholder_service,
    build_evidence_query_service,
    build_folder_template_service,
)

__all__: list[str] = [
    "build_contract_generation_service",
    "build_contract_generation_service_with_deps",
    "build_document_service",
    "build_document_template_binding_service",
    "build_evidence_list_placeholder_service",
    "build_evidence_query_service",
    "build_folder_template_service",
    "build_generation_task_service",
    "build_supplementary_agreement_generation_service",
    "build_supplementary_agreement_generation_service_with_deps",
]
