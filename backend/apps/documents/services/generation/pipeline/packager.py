"""Business logic services."""

import zipfile
from io import BytesIO
from typing import Any


class ZipPackager:
    def create(self, folder_structure: dict[str, Any], documents: list[tuple[str, bytes, str]]) -> bytes:
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            self._create_folders_in_zip(zip_file, folder_structure, "")
            root = folder_structure.get("name", "folder")
            for folder_path, content, filename in documents:
                if folder_path:
                    file_path = f"{root}/{folder_path}/{filename}"
                else:
                    file_path = f"{root}/{filename}"
                zip_file.writestr(file_path, content)
        return zip_buffer.getvalue()

    def _create_folders_in_zip(self, zip_file: zipfile.ZipFile, structure: dict[str, Any], parent_path: str) -> None:
        if not structure:
            return
        folder_name = structure.get("name", "")
        if not folder_name:
            return
        current_path = f"{parent_path}/{folder_name}" if parent_path else folder_name
        zip_file.writestr(f"{current_path}/", "")
        children = structure.get("children", [])
        for child in children:
            self._create_folders_in_zip(zip_file, child, current_path)
