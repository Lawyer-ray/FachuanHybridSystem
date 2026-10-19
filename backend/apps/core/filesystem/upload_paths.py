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
from typing import Any

from django.utils import timezone

# ┌─────────────────────────────────────────────────────────────┐
# │ MEDIA PATH FACTORY - UNIFIED DIRECTORY NAMING              │
# │                                                            │
# │ 所有 FileField 的 upload_to 必须使用本模块的工厂类。         │
# │ 新增目录名必须在下方 MEDIA_ENTITIES 中注册。                │
# │ 禁止在 Model 或 Service 中硬编码路径字符串。                │
# │ 详见 CLAUDE.md「Media 文件管理规范」。                      │
# └─────────────────────────────────────────────────────────────┘


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


# ─── 展示型名称 / ZIP 条目名清洗 ──────────────────────────────────
# 解耦（2026-10-19）：以下 safe_name / safe_arcname 由
# documents/services/generation/path_utils.py 原样上提（该模块已成事实 core，
# 被多个 app 引用）；path_utils 保留同名兼容别名，新代码请直接从本模块引入。
# 与上方 sanitize_filename（白名单替换为下划线并截断 200）策略不同：这里是
# 「尽量保留可读性」的黑名单替换，不截断、不处理扩展名。


def safe_name(name: str, *, collapse_whitespace: bool = False) -> str:
    """面向展示的名称清洗：路径分隔符换全角，换行/回车/制表换空格，空值回退「未命名」。

    ``collapse_whitespace=True`` 额外把连续空白压成单个空格再去首尾空白——这是
    cases ``CaseTemplateGenerationService._safe_name`` 原有的差异化行为，以参数保留；
    默认关闭，保证 documents 侧既有调用输出逐字不变。
    """
    value = (name or "").strip()
    value = value.replace("/", "／").replace("\\", "＼")
    value = value.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    if collapse_whitespace:
        value = re.sub(r"\s+", " ", value).strip()
    return value or "未命名"


def safe_arcname(name: str) -> str:
    """ZIP 条目名清洗：逐段 ``safe_name``，剔除 ""/"."/".." 片段与 Windows 盘符前缀。

    安全审计（2026-10-19）要点原样保留：".." 片段剔除防解压路径穿越；剥掉盘符前缀
    （如 ``C:\\evil``）阻断绝对路径形态；前导 "/" 经去空段后自然变为相对路径。
    """
    safe = (name or "").replace("\\", "/")
    safe = re.sub(r"^[A-Za-z]:(?=/|$)", "", safe)
    parts = [safe_name(part) for part in safe.split("/") if part not in ("", ".", "..")]
    return "/".join(parts)


# ─── 下载文件名 / 文书重命名片段清洗 ──────────────────────────────
# 解耦（2026-10-19）：收敛 automation 下两组逐字相同的本地实现。

_ILLEGAL_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|\n\r\t]+')


def replace_illegal_filename_chars(name: str, *, replacement: str = "_") -> str:
    """把文件名非法字符（``\\ / : * ? " < > |`` 及换行/回车/制表）的连续段替换为 ``replacement``，再去首尾空白。

    解耦（2026-10-19）：收敛法院文书爬虫 jysd / sfdw / daolv 各自的 ``_safe_filename`` 正则。
    清洗后为空时返回空串，兜底文件名由调用方决定——各爬虫的兜底带时间戳与平台前缀，
    留在调用方以维持原有的惰性求值与实例依赖（daolv 取 ``self._DOMAIN``）。
    """
    return _ILLEGAL_FILENAME_CHARS_RE.sub(replacement, name).strip()


_FILENAME_PART_ILLEGAL_RE = re.compile(r'[<>:"|?*\\/]')
_FILENAME_PART_ASCII_PARENS_RE = re.compile(r"[()]")
_FILENAME_PART_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_filename_part(text: str) -> str:
    """文书重命名「片段」清洗：删除（而非替换）Windows 非法字符、英文括号与控制字符，再去首尾空格/点号。

    解耦（2026-10-19）：收敛 automation/services/sms 下 ``DocumentRenamer`` 与
    ``DocumentAttachmentService`` 逐字相同的 ``_sanitize_filename_part``。
    用于标题 / 案件名等将被套入文件名模板的片段：空输入返回空串，不做扩展名与长度处理；
    英文括号一并删除是为避免与模板自带的中文括号混淆。
    """
    if not text:
        return ""
    text = _FILENAME_PART_ILLEGAL_RE.sub("", text)
    text = _FILENAME_PART_ASCII_PARENS_RE.sub("", text)
    text = _FILENAME_PART_CONTROL_RE.sub("", text)
    return text.strip(" .")


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
    CONTRACT_CLIENT_PAYMENTS = "contracts/client_payments"

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
    CONTRACT_REVIEW_OUTPUT = "contract_review/output"
    DOCUMENT_PARSING_UPLOADS = "document_parsing/uploads"
    PDF_SPLITTING = "pdf_splitting"
    DOC_CONVERTER_SOURCE = "doc_converter_source"
    DOC_CONVERTER_OUTPUT = "doc_converter_output"
    DOC_CONVERTER_ZIP = "doc_converter_zip"
    DOC_CONVERT_OUTPUT = "doc_convert/output"
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

    # ── 劳动仲裁文书爬虫 ──
    LABOR_ARBITRATION_DOCS = "labor_arbitration/docs"


class DatedUUIDPath:
    """生成 `{entity}/YYYY/MM/{uuid_hex}{ext}` 路径。

    适用于需要匿名存储、防冲突的场景。
    """

    def __init__(self, entity: str) -> None:
        self.entity = entity

    def __call__(self, instance: Any, filename: str) -> str:
        now = timezone.now()
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
        now = timezone.now()
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
