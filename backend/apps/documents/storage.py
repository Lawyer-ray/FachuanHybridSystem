"""Module for storage."""

from __future__ import annotations

import logging
from typing import Any, Final

from django.apps import apps as django_apps
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db.utils import OperationalError, ProgrammingError
from django.utils.deconstruct import deconstructible

from apps.core.utils.path import Path

logger = logging.getLogger(__name__)

# 用户自定义模板目录名称
USER_CUSTOM_TEMPLATE_DIR = "0-用户自定义模板"
PRIVATE_DOCX_ROOT_SETTING: Final[str] = "DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT"
_PRIVATE_DOCX_ROOT_DEFAULT_SENTINEL: Final[str] = "__DOCX_PRIVATE_ROOT_NOT_SET__"


def get_public_docx_templates_root() -> Path:
    """获取仓库内公用 docx_templates 根目录。"""
    base_path = Path(str(settings.BASE_DIR))  # type: ignore[misc].parent / "apps" / "documents" / "docx_templates"
    return Path(str(base_path))


def get_configured_private_docx_templates_root() -> str:
    """获取私有模板根目录配置值（优先系统配置，其次环境变量）。"""
    configured = str(getattr(settings, PRIVATE_DOCX_ROOT_SETTING, "") or "").strip()

    if not django_apps.ready:
        return configured

    try:
        from apps.core.interfaces import ServiceLocator

        system_config_service = ServiceLocator.get_system_config_service()
        runtime_config = str(
            system_config_service.get_value(PRIVATE_DOCX_ROOT_SETTING, _PRIVATE_DOCX_ROOT_DEFAULT_SENTINEL) or ""
        ).strip()
        if runtime_config != _PRIVATE_DOCX_ROOT_DEFAULT_SENTINEL:
            return runtime_config
    except (OperationalError, ProgrammingError):
        logger.debug("系统配置表未就绪，回退环境变量配置", exc_info=True)
    except Exception:
        logger.warning("读取系统配置失败，回退环境变量配置", exc_info=True)

    return configured


def get_private_docx_templates_root() -> Path | None:
    """获取可选私有 docx_templates 根目录（未配置则为 None）。"""
    configured = get_configured_private_docx_templates_root()
    if not configured:
        return None
    return Path(configured).expanduser()  # type: ignore[no-any-return]


def get_docx_templates_source() -> str:
    """返回当前活动模板来源：public/private。"""
    return "private" if get_private_docx_templates_root() else "public"


def get_docx_templates_root() -> Path:
    """获取当前活动 docx_templates 根目录。"""
    private_root = get_private_docx_templates_root()
    if private_root is not None:
        return private_root
    return get_public_docx_templates_root()


def resolve_docx_template_path(file_path: str) -> Path:
    """解析模板路径（支持绝对路径和相对活动根目录路径）。"""
    normalized = file_path.strip()
    candidate = Path(normalized)
    if candidate.is_absolute():
        return candidate

    root = get_docx_templates_root().resolve()
    resolved = (root / candidate).resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("模板路径越界，必须位于当前 docx_templates 根目录内") from exc

    return resolved  # type: ignore[no-any-return]


@deconstructible
class DocumentTemplateStorage(FileSystemStorage):
    """
    文书模板智能存储类

    统一管理所有文书模板文件到 docx_templates 目录
    外部上传的文件统一放到 0-用户自定义模板 子目录
    """

    def __init__(self) -> None:
        # 使用 Path 处理路径,跨平台兼容
        self.docx_templates_root = get_docx_templates_root()
        self.user_custom_dir = self.docx_templates_root / USER_CUSTOM_TEMPLATE_DIR
        super().__init__(location=str(self.docx_templates_root))

    def save(self, name: str | None, content: Any, max_length: int | None = None) -> str:
        """
        智能保存逻辑:
        1. 检查文件名是否表示已在docx_templates目录中的文件(通过特殊前缀标记)
        2. 如果是,直接返回相对路径(不复制)
        3. 如果不是,保存到 0-用户自定义模板 目录

        注意:通过 _EXISTING_: 前缀标记已存在于docx_templates中的文件
        """
        # 确保目录存在
        self.docx_templates_root.mkdir(parents=True, exist_ok=True)
        self.user_custom_dir.mkdir(parents=True, exist_ok=True)

        # 检查是否是已存在于docx_templates中的文件(通过特殊前缀标记)
        if name and name.startswith("_EXISTING_:"):
            # 提取实际的相对路径
            relative_path = name[len("_EXISTING_:") :]
            # 验证文件确实存在
            full_path = self.docx_templates_root / relative_path
            if full_path.exists():
                return relative_path
            # 文件不存在,继续正常保存流程

        # 不在目录中,保存到用户自定义模板目录
        if name and not name.lower().endswith(".docx"):
            logger.warning("上传的文件 %s 不是docx格式", name)

        # 清理文件名(移除可能的前缀)
        clean_name = Path(name).name if name else "unnamed.docx"

        # 将文件名添加到用户自定义模板目录
        name = f"{USER_CUSTOM_TEMPLATE_DIR}/{clean_name}"

        return super().save(name, content, max_length)

    def url(self, name: str | None) -> str:
        """返回文件URL - 返回绝对路径供下载"""
        # 由于是本地文件存储,不提供 HTTP URL
        # 返回空字符串让 Django 不生成链接
        return ""

    def path(self, name: str) -> str:
        """返回文件的绝对路径"""
        return str(self.docx_templates_root / name)

    def exists(self, name: str) -> bool:
        """检查文件是否存在"""
        return bool((self.docx_templates_root / name).exists())

    def size(self, name: str) -> int:
        """返回文件大小"""
        return int((self.docx_templates_root / name).stat().st_size)


# 创建存储实例
document_template_storage = DocumentTemplateStorage()


def list_docx_templates_files() -> list[tuple[str, str]]:
    """
    列出当前活动 docx_templates 目录下所有的 docx 文件

    Returns:
        list of (relative_path, display_name) tuples
    """
    root = get_docx_templates_root()
    if not root.exists():
        return []

    files: list[tuple[str, str]] = []
    for docx_file in root.rglob("*.docx"):
        relative_path = docx_file.relative_to(root).as_posix()
        # 跳过用户自定义模板目录中的文件(这些是上传的)
        if relative_path.startswith(USER_CUSTOM_TEMPLATE_DIR):
            continue
        files.append((relative_path, relative_path))

    files.sort(key=lambda x: x[0])
    return files
