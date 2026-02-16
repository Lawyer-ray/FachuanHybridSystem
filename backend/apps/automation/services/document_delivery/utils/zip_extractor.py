"""Business logic services."""

import os
import tempfile

from apps.core.filesystem import FolderFilesystemService
from apps.core.path import Path


def extract_zip_if_needed(file_path: str) -> list[str] | None | None:
    if not file_path.lower().endswith(".zip"):
        return None

    extract_dir = tempfile.mkdtemp(prefix="extracted_documents_")
    with open(file_path, "rb") as f:
        zip_content = f.read()
    FolderFilesystemService().extract_zip_bytes(extract_dir, zip_content)

    extracted_files: list[str] = []
    for root, _dirs, files in os.walk(extract_dir):
        for file in files:
            extracted_files.append(str(Path(root) / file))

    return extracted_files
