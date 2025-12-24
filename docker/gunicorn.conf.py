# ============================================================
# 法穿案件管理系统 - Gunicorn 配置文件
# ============================================================
# 用于生产环境的 WSGI 服务器配置
# 文档: https://docs.gunicorn.org/en/stable/settings.html
# ============================================================
# Requirements: 6.4

import multiprocessing
import os

# ============================================================
# 服务器绑定
# ============================================================
# 监听地址和端口
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# ============================================================
# Worker 进程配置
# ============================================================
# Worker 数量：推荐 (2 * CPU核心数) + 1
# 对于 I/O 密集型应用（如本系统），可以适当增加
# 默认值：2 workers（适合小型部署）
workers = int(os.getenv("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 4)))

# Worker 类型
# - sync: 同步 worker（默认）
# - gthread: 线程 worker（推荐用于 I/O 密集型）
# - gevent: 协程 worker（需要安装 gevent）
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")

# 每个 worker 的线程数（仅 gthread 模式有效）
threads = int(os.getenv("GUNICORN_THREADS", 4))

# Worker 连接数上限（仅 async worker 有效）
worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", 1000))

# ============================================================
# 超时配置
# ============================================================
# Worker 超时时间（秒）
# 如果 worker 在此时间内没有响应，将被杀死并重启
# 对于长时间运行的请求（如文件上传、报表生成），需要适当增加
timeout = int(os.getenv("GUNICORN_TIMEOUT", 120))

# 优雅关闭超时（秒）
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 30))

# Keep-alive 超时（秒）
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 5))

# ============================================================
# 请求配置
# ============================================================
# 最大请求数：worker 处理此数量请求后重启（防止内存泄漏）
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 1000))

# 最大请求数抖动：随机增加 0 到此值的请求数，避免所有 worker 同时重启
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", 50))

# 请求行最大长度
limit_request_line = int(os.getenv("GUNICORN_LIMIT_REQUEST_LINE", 4094))

# 请求头字段数量上限
limit_request_fields = int(os.getenv("GUNICORN_LIMIT_REQUEST_FIELDS", 100))

# 请求头字段大小上限
limit_request_field_size = int(os.getenv("GUNICORN_LIMIT_REQUEST_FIELD_SIZE", 8190))

# ============================================================
# 日志配置
# ============================================================
# 访问日志格式
# 常用变量:
# %(h)s - 远程地址
# %(l)s - '-'
# %(u)s - 用户名
# %(t)s - 时间
# %(r)s - 请求行
# %(s)s - 状态码
# %(b)s - 响应长度
# %(f)s - Referer
# %(a)s - User-Agent
# %(D)s - 请求处理时间（微秒）
# %(L)s - 请求处理时间（秒，小数）
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")  # "-" 表示输出到 stdout
access_log_format = os.getenv(
    "GUNICORN_ACCESS_LOG_FORMAT",
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sμs'
)

# 错误日志
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")  # "-" 表示输出到 stderr

# 日志级别: debug, info, warning, error, critical
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# 捕获 stdout/stderr 输出到日志
capture_output = True

# ============================================================
# 进程管理
# ============================================================
# 守护进程模式（Docker 中应设为 False）
daemon = False

# PID 文件路径
pidfile = os.getenv("GUNICORN_PID_FILE", None)

# 用户和组（Docker 中通常不需要设置，由 Dockerfile 控制）
# user = None
# group = None

# ============================================================
# 安全配置
# ============================================================
# 转发头信任设置（用于反向代理）
# 设置为 1 表示信任一层代理
forwarded_allow_ips = os.getenv("GUNICORN_FORWARDED_ALLOW_IPS", "*")

# 代理协议（用于 HTTPS 终止）
proxy_protocol = os.getenv("GUNICORN_PROXY_PROTOCOL", "false").lower() == "true"

# ============================================================
# 服务器钩子
# ============================================================
def on_starting(server):
    """服务器启动时调用"""
    pass


def on_reload(server):
    """服务器重载时调用"""
    pass


def worker_int(worker):
    """Worker 收到 SIGINT 或 SIGQUIT 时调用"""
    pass


def worker_abort(worker):
    """Worker 收到 SIGABRT 时调用（超时）"""
    pass


def pre_fork(server, worker):
    """Worker fork 之前调用"""
    pass


def post_fork(server, worker):
    """Worker fork 之后调用"""
    pass


def post_worker_init(worker):
    """Worker 初始化完成后调用"""
    pass


def worker_exit(server, worker):
    """Worker 退出时调用"""
    pass


def nworkers_changed(server, new_value, old_value):
    """Worker 数量变化时调用"""
    pass


def on_exit(server):
    """服务器退出时调用"""
    pass
