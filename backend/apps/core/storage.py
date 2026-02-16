"""
存储类定义

提供统一的文件存储类,供各模块使用.
"""

from django.core.files.storage import FileSystemStorage


class KeepOriginalNameStorage(FileSystemStorage):
    """
    自定义存储类,保持原文件名(包括括号等特殊字符)
    如果文件名重复,添加序号而不是随机字符
    """

    def generate_filename(self, filename: str) -> str:  # type: ignore
        """
        重写 generate_filename,跳过 get_valid_filename 的清理
        保持原始文件名不变
        """
        import posixpath

        # 不调用 get_valid_filename,直接使用原始文件名
        # 只做基本的路径安全处理
        filename = filename.replace("\\", "/")
        filename = posixpath.basename(filename)
        return filename

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        import os

        # 如果文件不存在,直接返回原名
        if not self.exists(name):
            return name

        # 文件存在,添加序号
        dir_name = os.path.dirname(name)
        base_name = os.path.basename(name)
        stem, ext = os.path.splitext(base_name)

        counter = 1
        while True:
            new_name = os.path.join(dir_name, f"{stem}_{counter}{ext}") if dir_name else f"{stem}_{counter}{ext}"
            if not self.exists(new_name):
                return new_name
            counter += 1
