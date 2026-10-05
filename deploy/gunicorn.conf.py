"""gunicorn 配置（公网后端，launchd com.user.fachuan-gunicorn 托管）。

经运行时目录的 bin/gunicorn.sh 启动（install.sh 从 deploy/ 复制到
~/Library/Application Support/FachuanHybridSystem/），绑定 127.0.0.1:8003。
nginx 是唯一上游（nginx/nginx.conf），端口只对本机开放。
"""

from __future__ import annotations

import os
from pathlib import Path

_repo = Path(os.environ["FACHUAN_REPO"])

bind = "127.0.0.1:8003"
# 与开发栈同款模块路径：cd backend/apiSystem && uvicorn apiSystem.asgi
chdir = str(_repo / "backend" / "apiSystem")

workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
# ASGI worker：uvicorn 自带（uvicorn>=0.54 仍捆绑，无需额外依赖）
worker_class = "uvicorn.workers.UvicornWorker"

# LLM 生成、文书下载、OCR 等长请求；与 nginx proxy_read_timeout 对齐。
# 注：/media/ 走 Django FileResponse 流式回发，大文件也在该时限内
timeout = 300
graceful_timeout = 30
keepalive = 5

# 定期回收 worker，防慢性泄漏（连接/浏览器句柄累积）
max_requests = 1000
max_requests_jitter = 100

loglevel = "info"
errorlog = "-"  # stderr → launchd 日志（~/Library/Logs/fachuan-gunicorn.log）
accesslog = None  # 访问日志由 Django LOGGING（backend/logs/api.log）统一记录
