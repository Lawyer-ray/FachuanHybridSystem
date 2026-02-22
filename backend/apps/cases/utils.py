"""Utility functions."""

from __future__ import annotations

CASE_LOG_ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".jpg",
    ".jpeg",
    ".png",
}

CASE_LOG_MAX_FILE_SIZE = 50 * 1024 * 1024


def _basename(filename: str) -> str:
    name = str(filename or "")
    name = name.replace("\\", "/")
    return name.split("/")[-1]


def get_file_extension_lower(filename: str) -> str:
    base = _basename(filename).strip()
    if not base or base in {".", ".."}:
        return ""
    if "." not in base:
        return ""
    return "." + base.rsplit(".", 1)[-1].lower()


def validate_case_log_attachment(filename: str, size: int | None) -> tuple[bool, str | None]:
    ext = get_file_extension_lower(filename)
    if ext not in CASE_LOG_ALLOWED_EXTENSIONS:
        return False, "不支持的文件类型"
    if size and size > CASE_LOG_MAX_FILE_SIZE:
        return False, "文件大小超过50MB限制"
    return True, None


def normalize_case_number(number: str, ensure_hao: bool = False) -> str:
    if not number:
        return ""

    result = str(number)
    result = result.replace("(", "（").replace(")", "）")
    result = result.replace("〔", "（").replace("〕", "）")
    result = result.replace("[", "（").replace("]", "）")
    result = result.replace(" ", "").replace("\u3000", "")

    if ensure_hao and result and not result.endswith("号"):
        result += "号"

    return result
