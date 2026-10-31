"""上传附件的命名白名单与限额：收件箱两类上传（律师手动 / 客户链接）的共用口径。

三样东西放在这里而不是放在某个上传服务里，是为了切断
``archive_extract_service`` ↔ ``manual_upload_service`` 的循环导入：

- ``archive_extract_service`` 展开压缩包后要给内层文件过同一套白名单（与直传
  等价），
- ``manual_upload_service`` 与 ``client_upload_service`` 要在入口处校验直传文件。

两条路径都问同一套「扩展名 + 大小」，把它下沉到此模块后依赖形状是
``archive_extract → upload_policy ← manual_upload``，压缩包展开与上传服务之间
零 import（含函数内延迟导入——``py/cyclic-import`` 按模块级依赖图判定，延迟
导入不消除告警）。

本模块刻意只依赖 ``pathlib`` / ``re`` 与异常基类：任何一处引入 Django 或业务
模块都会把环重新引回来。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from apps.core.exceptions import ValidationException

#: 可展开的压缩包扩展名（zip 走 stdlib，rar/7z 走 bsdtar）
ARCHIVE_EXTENSIONS = frozenset({".zip", ".rar", ".7z"})

#: 分卷压缩包命名（.part1.rar / .z01 / .zip.001 / .7z.002 / .rar.00x）
_MULTIPART_RE = re.compile(r"\.part\d+\.rar$|\.zip\.\d+$|\.7z\.\d+$|\.z\d+$|\.r\d+$|\.0\d+$", re.IGNORECASE)

# 收件箱手动上传白名单：文档 / 图片 / 压缩包（对齐 document_parsing 等上传口的先例）
MANUAL_UPLOAD_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".txt",
        ".md",
        ".csv",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".bmp",
        ".tiff",
        ".heic",
        ".zip",
        ".rar",
        ".7z",
    }
)
# 单文件上限 50MB（与 document_parsing 上传、合同归档上传的先例一致）；
# 压缩包单独放宽——律所扫描件整包常见 100–200MB，展开侧自有
# 200MB/200 条硬上限兜底
MANUAL_UPLOAD_MAX_SIZE_BYTES = 50 * 1024 * 1024
MANUAL_UPLOAD_ARCHIVE_MAX_SIZE_BYTES = 200 * 1024 * 1024


def is_archive_filename(name: str) -> bool:
    return Path(name).suffix.lower() in ARCHIVE_EXTENSIONS


def is_multipart_filename(name: str) -> bool:
    """分卷压缩包命名（.part1.rar / .z01 / .zip.001 / .7z.002 / .r00 …）。"""
    return bool(_MULTIPART_RE.search(name))


def validate_manual_upload_file(uploaded: Any) -> None:
    """上传附件的类型 / 大小校验（无类型限制时收件箱会沦为任意文件仓库）。

    收件箱两类上传共用：直传文件在入口校验，压缩包展开出的内层文件由
    :func:`apps.message_hub.services.archive_extract_service.expand_upload_files`
    逐个回调本函数校验——与直传完全同口径。
    """
    name = str(getattr(uploaded, "name", "") or "")
    if is_multipart_filename(name):
        raise ValidationException(
            "分卷压缩包不支持直接上传",
            code="MULTIPART_ARCHIVE",
            errors={"files": f"{name} 是分卷压缩包，请先在本地合并成完整压缩包再上传"},
        )
    ext = Path(name).suffix.lower()
    if ext not in MANUAL_UPLOAD_ALLOWED_EXTENSIONS:
        raise ValidationException(
            f"不支持的附件格式: {ext or '(无扩展名)'}",
            code="INVALID_ATTACHMENT_TYPE",
            errors={"files": f"允许的格式: {', '.join(sorted(MANUAL_UPLOAD_ALLOWED_EXTENSIONS))}"},
        )
    size = int(getattr(uploaded, "size", 0) or 0)
    cap = MANUAL_UPLOAD_ARCHIVE_MAX_SIZE_BYTES if is_archive_filename(name) else MANUAL_UPLOAD_MAX_SIZE_BYTES
    if size > cap:
        limit = f"{cap // (1024 * 1024)}MB" + ("（压缩包）" if cap != MANUAL_UPLOAD_MAX_SIZE_BYTES else "")
        raise ValidationException(
            f"附件过大（单个不能超过 {limit}）",
            code="ATTACHMENT_TOO_LARGE",
            errors={"files": f"单个附件不能超过 {limit}"},
        )
