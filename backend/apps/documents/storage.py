"""Module for storage."""

from __future__ import annotations

"""
文书模板智能存储系统

实现智能文件管理:
1. 如果上传的文件已存在于docx_templates目录,直接引用(不复制)
2. 如果是外部文件,保存到 0-用户自定义模板 目录统一管理
"""

from typing import Any

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

from apps.core.path import Path

# 用户自定义模板目录名称
USER_CUSTOM_TEMPLATE_DIR = "0-用户自定义模板"


def get_docx_templates_root() -> Any:
    """获取docx_templates根目录"""
    base_path = Path(settings.BASE_DIR).parent / "apps" / "documents" / "docx_templates"
    return base_path


@deconstructible
class DocumentTemplateStorage(FileSystemStorage):
    """
    文书模板智能存储类

    统一管理所有文书模板文件到 docx_templates 目录
    外部上传的文件统一放到 0-用户自定义模板 子目录
    """

    def __init__(self) -> None:
        # 使用 Path 处理路径,跨平台兼容
        # BASE_DIR 是 backend/apiSystem,需要用 parent 获取 backend 目录
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
            import logging

            logging.getLogger(__name__).warning(f"上传的文件 {name} 不是docx格式")

        # 清理文件名(移除可能的前缀)
        clean_name = Path(name).name if name else "unnamed.docx"

        # 将文件名添加到用户自定义模板目录
        name = f"{USER_CUSTOM_TEMPLATE_DIR}/{clean_name}"

        return super().save(name, content, max_length)

    def _is_in_docx_templates(self, file_path: Path) -> bool:
        """检查文件是否已在docx_templates目录中"""
        try:
            file_path.resolve().relative_to(self.docx_templates_root.resolve())
            return True
        except ValueError:
            return False

    def url(self, name: str | None) -> str:
        """返回文件URL - 返回绝对路径供下载"""
        # 返回 media URL 或直接返回文件路径
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
    列出docx_templates目录下所有的docx文件

    Returns:
        list of (relative_path, display_name) tuples
    """
    root = get_docx_templates_root()
    if not root.exists():
        return []

    files: list[Any] = []
    for docx_file in root.rglob("*.docx"):
        relative_path = docx_file.relative_to(root).as_posix()
        # 跳过用户自定义模板目录中的文件(这些是上传的)
        if relative_path.startswith(USER_CUSTOM_TEMPLATE_DIR):
            continue
        display_name = relative_path
        files.append((relative_path, display_name))

    # 按路径排序
    files.sort(key=lambda x: x[0])
    return files
