#!/usr/bin/env python3
"""格式定义与配置常量。"""

import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# 导入时先加载 .env，确保后续 os.getenv 能读到值
_dotenv_path = SCRIPT_DIR / ".env"
if _dotenv_path.exists():
    try:
        from dotenv import load_dotenv as _load

        _load(_dotenv_path, override=True)
    except ImportError:
        pass

# 微信接口常量
TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
UPLOAD_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"
DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"

# 本地 token 缓存文件
TOKEN_CACHE_FILE = SCRIPT_DIR / "token_cache.json"

# 环境变量配置（.env 已加载）
APPID: str | None = os.getenv("WECHAT_APPID")
APPSECRET: str | None = os.getenv("WECHAT_APPSECRET")
AUTHOR: str = os.getenv("AUTHOR", "作者")
HTTP_PROXY: str | None = os.getenv("HTTP_PROXY") or os.getenv("https_proxy")
