"""
文件识别 Skill

接入后端文档解析服务(http://127.0.0.1:8002/api/v1/document-parsing/),
将各种格式文件(PDF/DOC/DOCX/图片/OFD/RTF 等)统一转为 Markdown,
为后续 AI 分析和案件处理流程做准备。

主要接口:
- recognize_file: 识别单个文件,输出 .md
- recognize_files: 批量识别文件

CLI 入口:
    python -m skills.案件处理.file-recognition.scripts <file_or_dir> [options]
"""

from __future__ import annotations

from .converter import recognize_file, recognize_files
from .detector import detect_file_format, is_format_supported, scan_directory, select_backend
from .formats import ALL_SUPPORTED_FORMATS, BACKEND_FEATURES, DEFAULT_BACKEND

__version__ = '1.1.0'

__all__ = [
    'recognize_file',
    'recognize_files',
    'detect_file_format',
    'is_format_supported',
    'scan_directory',
    'select_backend',
    'ALL_SUPPORTED_FORMATS',
    'BACKEND_FEATURES',
    'DEFAULT_BACKEND',
    '__version__',
]
