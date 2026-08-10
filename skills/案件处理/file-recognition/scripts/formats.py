"""
文件识别 Skill - 格式定义与配置

定义支持的文件格式、各解析后端的能力矩阵,以及默认配置常量。
"""

from __future__ import annotations

# 解析后端名称
BACKEND_AUTO = 'auto'
BACKEND_MINERU = 'mineru'
BACKEND_TEXTIN = 'textin'
BACKEND_LOCAL = 'local'

# 默认后端(auto 由后端 SystemConfig 决定实际后端)
DEFAULT_BACKEND = BACKEND_AUTO

# 各后端支持的文件格式(扩展名小写,无点)
BACKEND_FORMATS: dict[str, set[str]] = {
    BACKEND_MINERU: {
        'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
        'jpg', 'jpeg', 'png',
    },
    BACKEND_TEXTIN: {
        'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
        'jpg', 'jpeg', 'png', 'ofd', 'rtf', 'html', 'csv', 'txt',
    },
    BACKEND_LOCAL: {
        'pdf', 'jpg', 'jpeg', 'png', 'bmp', 'tiff',
    },
}

# 所有支持的格式(任意后端支持即可)
ALL_SUPPORTED_FORMATS: set[str] = set().union(*BACKEND_FORMATS.values())

# auto 模式下的后端选择优先级(支持 markdown 输出 + 格式覆盖广的优先)
AUTO_BACKEND_PRIORITY: tuple[str, ...] = (BACKEND_TEXTIN, BACKEND_MINERU, BACKEND_LOCAL)

# 各后端特性
BACKEND_FEATURES: dict[str, dict] = {
    BACKEND_MINERU: {
        'name': 'MinerU 云 API',
        'markdown': True,
        'async': True,
    },
    BACKEND_TEXTIN: {
        'name': 'TextinParse 云 API',
        'markdown': True,
        'async': True,
    },
    BACKEND_LOCAL: {
        'name': '本地 PyMuPDF + RapidOCR',
        'markdown': False,
        'async': False,
    },
    BACKEND_AUTO: {
        'name': '自动选择(由后端 SystemConfig 控制)',
        'markdown': True,
        'async': None,
    },
}

# Markdown 输出后缀
MD_SUFFIX = '.md'

# 轮询配置
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_POLL_TIMEOUT = 600.0
