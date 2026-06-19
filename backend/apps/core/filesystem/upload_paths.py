"""统一的 upload_to 路径工厂函数。

所有新 FileField/ImageField 应使用本模块提供的工厂函数生成 upload_to，
确保文件路径按 `{app_entity}/YYYY/MM/` 规范组织。

用法示例::

    from apps.core.filesystem.upload_paths import DatedUUIDPath

    class MyModel(models.Model):
        file = FileField(upload_to=DatedUUIDPath("my_entity"))
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

# ┌─────────────────────────────────────────────────────────────┐
# │ MEDIA PATH FACTORY - UNIFIED DIRECTORY NAMING              │
# │                                                            │
# │ 所有 FileField 的 upload_to 必须使用本模块的工厂类。         │
# │ 新增目录名必须在下方 MEDIA_ENTITIES 中注册。                │
# │ 禁止在 Model 或 Service 中硬编码路径字符串。                │
# │ 详见 CLAUDE.md「Media 文件管理规范」。                      │
# └─────────────────────────────────────────────────────────────┘

from django.db.models.fields.files import FieldFile


def sanitize_filename(name: str, *, allow_chinese: bool = True) -> str:
    """
    统一的文件名清洗函数。

    - allow_chinese=True: 保留中文字符（默认，适用于大多数场景）
    - allow_chinese=False: 不允许中文（适用于某些外部系统）

    规则：
    - 保留字母、数字、中文（可选）、点、下划线、连字符
    - 其余字符替换为下划线
    - 去除首尾的下划线和点
    - 截断至 200 字符
    """
    pattern = r"[^0-9A-Za-z一-鿿._-]+" if allow_chinese else r"[^0-9A-Za-z._-]+"
    return re.sub(pattern, "_", name).strip("_.")[:200]


def _sanitize(filename: str) -> str:
    """清理文件名，去除危险字符，保留中文。委托给 sanitize_filename。"""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return sanitize_filename(name) or "file"


# ─── Media 目录 entity 常量 ────────────────────────────────────
# 所有 DatedUUIDPath / EntityIdPath / DatedOriginalPath 的 entity 参数
# 必须使用以下常量，禁止硬编码字符串。
# 新增模块时请在此处注册。


class MediaEntity:
    """media 目录 entity 常量，用于 upload_to 工厂类。"""

    # ── 案件 ──
    CASE_LOGS = "case_logs"
    CASE_DOCUMENTS = "case_documents"
    EVIDENCE_FILES = "evidence/files"
    EVIDENCE_MERGED = "evidence/merged"

    # ── 合同 ──
    CONTRACT_PAYMENTS = "contracts/payments"
    CONTRACT_FINALIZED = "contracts/finalized"
    CONTRACT_INVOICES = "contracts/invoices"
    CONTRACT_EDITED = "contracts/edited"

    # ── 客户 ──
    CLIENT_DOCS = "client_docs"
    CLIENT_ID_CARDS = "client_id_cards"
    AVATARS = "avatars"
    LAWYER_LICENSES = "lawyers/licenses"

    # ── 工具模块 ──
    AUTOMATION_UPLOADS = "automation/uploads"
    AUTOMATION_INVOICES = "automation/invoices"
    AUTOMATION_CAPTCHA = "automation/captcha_pending"
    CONTRACT_REVIEW_UPLOADS = "contract_review/uploads"
    CONTRACT_REVIEW_CACHE = "contract_review/pdf_cache"
    DOCUMENT_PARSING_UPLOADS = "document_parsing/uploads"
    PDF_SPLITTING = "pdf_splitting"
    DOC_CONVERTER_SOURCE = "doc_converter_source"
    DOC_CONVERTER_OUTPUT = "doc_converter_output"
    DOC_CONVERTER_ZIP = "doc_converter_zip"
    IMAGE_ROTATION = "image_rotation"
    EXPRESS_QUERY_WAYBILLS = "express_query/waybills"
    EXPRESS_QUERY_RESULTS = "express_query/results"
    INVOICE_RECOGNITION = "invoice_recognition"
    EVIDENCE_SORTING = "evidence_sorting"
    BATCH_PRINTING = "batch_printing"
    GSXT_REPORTS = "gsxt_reports"

    # ── 文书 ──
    GENERATED_DOCUMENTS = "generated_documents"
    EXTERNAL_TEMPLATES = "documents/external_templates"

    # ── 消息 ──
    COURT_INBOX = "messages/court_inbox"
    IMAP = "messages/imap"

    # ── 工作台 ──
    WORKBENCH_BATCH = "workbench_batch"
    WORKBENCH_SUMMARY = "workbench_summary"
    WORKBENCH_DETAIL = "workbench_detail"

    # ── 聊天记录 ──
    CHAT_RECORDINGS = "chat_records/recordings"
    CHAT_SCREENSHOTS = "chat_records/screenshots"
    CHAT_EXPORTS = "chat_records/exports"

    # ── 法律检索 ──
    LEGAL_RESEARCH = "legal_research"
    LEGAL_SOLUTION = "legal_solution"

    # ── 其他 ──
    OA_IMPORTS = "oa_imports"
    PROPERTY_CLUE_ATTACHMENTS = "property_clue_attachments"
    CANVAS_FILES = "canvas_files"


class DatedUUIDPath:
    """生成 `{entity}/YYYY/MM/{uuid_hex}{ext}` 路径。

    适用于需要匿名存储、防冲突的场景。
    """

    def __init__(self, entity: str) -> None:
        self.entity = entity

    def __call__(self, instance: Any, filename: str) -> str:
        now = datetime.now()
        ext = ""
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        return f"{self.entity}/{now:%Y/%m}/{uuid.uuid4().hex}{ext}"

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return (
            "apps.core.filesystem.upload_paths.DatedUUIDPath",
            (self.entity,),
            {},
        )


class DatedOriginalPath:
    """生成 `{entity}/YYYY/MM/{sanitized_name}` 路径。

    适用于需要保留原始文件名可读性的场景。
    """

    def __init__(self, entity: str) -> None:
        self.entity = entity

    def __call__(self, instance: Any, filename: str) -> str:
        now = datetime.now()
        safe_name = _sanitize(filename)
        return f"{self.entity}/{now:%Y/%m}/{safe_name}"

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return (
            "apps.core.filesystem.upload_paths.DatedOriginalPath",
            (self.entity,),
            {},
        )


class EntityIdPath:
    """生成 `{entity}/{instance_id}/{sanitized_name}` 路径。

    适用于按业务对象（如案件、任务）组织文件的场景。
    """

    def __init__(self, entity: str, id_attr: str = "pk") -> None:
        self.entity = entity
        self.id_attr = id_attr

    def __call__(self, instance: Any, filename: str) -> str:
        obj_id = getattr(instance, self.id_attr, None) or "unsaved"
        safe_name = _sanitize(filename)
        return f"{self.entity}/{obj_id}/{safe_name}"

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return (
            "apps.core.filesystem.upload_paths.EntityIdPath",
            (self.entity, self.id_attr),
            {},
        )


class EntitySubPath:
    """生成固定路径 `{entity}/{sub}/`。

    适用于无需动态计算的简单场景。
    """

    def __init__(self, entity: str, sub: str) -> None:
        self.entity = entity
        self.sub = sub

    def __call__(self, instance: Any, filename: str) -> str:
        return f"{self.entity}/{self.sub}/"

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return (
            "apps.core.filesystem.upload_paths.EntitySubPath",
            (self.entity, self.sub),
            {},
        )
