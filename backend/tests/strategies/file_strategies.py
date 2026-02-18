"""
文件上传相关 Hypothesis 策略
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from hypothesis import strategies as st

from apps.core.services.file_upload_service import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES

# 扩展名 → MIME 类型映射（白名单内）
_EXT_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# 不在白名单中的扩展名样本
_DISALLOWED_EXTENSIONS: list[str] = [
    ".exe",
    ".sh",
    ".py",
    ".js",
    ".txt",
    ".zip",
    ".csv",
    ".bat",
    ".cmd",
    ".php",
    ".rb",
    ".go",
    ".rs",
    ".html",
    ".xml",
    ".json",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
]

# 不在白名单中的 MIME 类型样本
_DISALLOWED_MIME_TYPES: list[str] = [
    "text/html",
    "text/plain",
    "application/octet-stream",
    "application/javascript",
    "application/zip",
    "text/xml",
    "application/json",
]


@st.composite
def allowed_file(draw: Any) -> MagicMock:
    """生成白名单内的合法文件对象"""
    ext = draw(st.sampled_from(sorted(_EXT_TO_MIME.keys())))
    mime = _EXT_TO_MIME[ext]
    base_name = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
        )
    )
    size = draw(st.integers(min_value=0, max_value=10 * 1024 * 1024))  # 0~10MB

    mock = MagicMock()
    mock.name = f"{base_name}{ext}"
    mock.size = size
    mock.content_type = mime
    mock.chunks.return_value = [b"fake content"]
    return mock


@st.composite
def disallowed_extension_file(draw: Any) -> MagicMock:
    """生成扩展名不在白名单中的文件对象"""
    ext = draw(st.sampled_from(_DISALLOWED_EXTENSIONS))
    mime = draw(st.sampled_from(_DISALLOWED_MIME_TYPES))
    base_name = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
        )
    )
    size = draw(st.integers(min_value=0, max_value=1024))

    mock = MagicMock()
    mock.name = f"{base_name}{ext}"
    mock.size = size
    mock.content_type = mime
    mock.chunks.return_value = [b"fake content"]
    return mock


@st.composite
def arbitrary_filename(draw: Any) -> str:
    """生成任意文件名（可能含路径遍历字符）"""
    # 基础名称部分
    base = draw(
        st.text(
            min_size=1,
            max_size=30,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                whitelist_characters="_-. /\\",
            ),
        )
    )
    # 随机选择一个白名单扩展名
    ext = draw(st.sampled_from(sorted(_EXT_TO_MIME.keys())))
    return f"{base}{ext}"
