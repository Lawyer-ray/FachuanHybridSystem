"""MCP Server 配置 - 从环境变量读取法穿连接信息"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

BASE_URL: str = os.getenv("FACHUAN_BASE_URL", "http://127.0.0.1:8002/api/v1")
USERNAME: str = os.getenv("FACHUAN_USERNAME", "")
PASSWORD: str = os.getenv("FACHUAN_PASSWORD", "")
