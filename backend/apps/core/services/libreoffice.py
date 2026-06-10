"""LibreOffice 可执行文件路径查找。

合并自 doc_converter/services/engine.py、documents/services/infrastructure/pdf_merge_utils.py
和 batch_printing/services/job/file_prepare_service.py 三处重复实现。
"""

from __future__ import annotations

import platform
import shutil
from pathlib import Path


def find_libreoffice() -> str | None:  # pragma: no cover
    """查找 LibreOffice 可执行文件路径。

    搜索顺序：PATH → 平台特定安装路径（macOS / Linux）。

    Returns:
        可执行文件路径，未找到返回 None。
    """
    # 1. PATH 环境变量
    path = shutil.which("soffice") or shutil.which("libreoffice")
    if path:
        return path

    # 2. 平台特定路径
    candidates: list[Path] = []
    if platform.system() == "Darwin":
        candidates = [
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
            Path("/Applications/LibreOffice.app/Contents/program/soffice"),
            Path("/Applications/OpenOffice.app/Contents/MacOS/soffice"),
            Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice",
            Path.home() / "Applications/LibreOffice.app/Contents/program/soffice",
        ]
    elif platform.system() == "Linux":
        candidates = [
            Path("/usr/bin/libreoffice"),
            Path("/usr/bin/soffice"),
            Path("/usr/local/bin/libreoffice"),
            Path("/snap/bin/libreoffice"),
        ]

    for p in candidates:
        if p.is_file():
            return str(p)

    return None
