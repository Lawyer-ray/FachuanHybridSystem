"""Business logic services."""

import zipfile
from io import BytesIO
from typing import Any

from apps.documents.services.generation.path_utils import safe_arcname


class ZipPackager:
    def create(
        self, folder_structure: dict[str, Any], documents: list[tuple[str, bytes, str]]
    ) -> bytes:  # pragma: no cover
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            self._create_folders_in_zip(zip_file, folder_structure, "")
            # 安全审计（2026-10-19）：ZIP 根目录名与骨架节点名来自文件夹模板结构、
            # 文件名来自案件/当事人数据，统一经 safe_arcname 清洗（拒 .. 与绝对路径形态）后写入，
            # 防止恶意名称造成解压路径穿越（zip slip）。
            root = safe_arcname(str(folder_structure.get("name", "") or "folder")) or "folder"
            for folder_path, content, filename in documents:
                # 安全审计（2026-10-19）：目录段与文件名分别清洗后再拼接（整体清洗无法剥掉中段的
                # 盘符等绝对路径片段），拒 .. 与绝对路径形态，防解压路径穿越（zip slip）。
                file_path = "/".join(part for part in (root, safe_arcname(folder_path), safe_arcname(filename)) if part)
                zip_file.writestr(file_path, content)
        return zip_buffer.getvalue()

    def _create_folders_in_zip(self, zip_file: zipfile.ZipFile, structure: dict[str, Any], parent_path: str) -> None:
        if not structure:
            return
        folder_name = safe_arcname(str(structure.get("name", "") or ""))
        if not folder_name:
            return
        current_path = f"{parent_path}/{folder_name}" if parent_path else folder_name
        zip_file.writestr(f"{current_path}/", "")
        children = structure.get("children", [])
        for child in children:
            self._create_folders_in_zip(zip_file, child, current_path)
