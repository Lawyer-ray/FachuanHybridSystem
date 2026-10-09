"""
Django settings for apiSystem project.
"""

import os
import sys
from pathlib import Path

try:
    import django_stubs_ext

    django_stubs_ext.monkeypatch()
except ImportError:
    pass

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

from apps.core.config.django_runtime import (
    resolve_cache_redis_url,
    resolve_channel_layers,
    resolve_channel_redis_url,
    resolve_contract_folder_browse_roots,
    resolve_cors_and_csrf,
    resolve_perm_open_access,
    resolve_q_cluster,
    resolve_rate_limit,
    resolve_security_config,
    resolve_web_worker_count,
    validate_runtime_topology,
)

# 从环境变量读取配置
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR.parent / ".env")
except ImportError:
    pass

# ============================================================
# 核心配置
# ============================================================

# 安全的默认密钥（仅用于开发环境）
_DEV_SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"  # pragma: allowlist secret

_security = resolve_security_config(
    dev_secret_key=_DEV_SECRET_KEY,
    default_allowed_hosts_dev=["*"],
    default_allowed_hosts_prod=["localhost", "127.0.0.1"],
)

_is_production = _security.is_production
_allow_lan = _security.allow_lan
SECRET_KEY = _security.secret_key
DEBUG = _security.debug
ALLOWED_HOSTS = _security.allowed_hosts
CREDENTIAL_ENCRYPTION_KEY = _security.credential_encryption_key
SCRAPER_ENCRYPTION_KEY = _security.scraper_encryption_key

# Application definition

INSTALLED_APPS = [
    # 'unfold',  # django-unfold 主题（已禁用，与自定义模板冲突）
    # 'unfold.contrib.filters',
    # 'unfold.contrib.forms',
    "apps.organization",  # 必须在 admin 之前，以覆盖登录模板
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",  # PostgreSQL 全文搜索扩展
    "nested_admin",
    "simple_history",
    "corsheaders",
    "ninja_jwt",
    # 安全审计 M-8：refresh token 轮换 + 黑名单（ROTATE_REFRESH_TOKENS /
    # BLACKLIST_AFTER_ROTATION 依赖本 app 的 OutstandingToken/BlacklistedToken）
    "ninja_jwt.token_blacklist",
    "channels",  # WebSocket 支持
    # === Django Admin 侧边栏顺序（按以下顺序显示）===
    "apps.client",  # 1. Client CRM（当事人管理）
    "apps.contracts",  # 2. Contracts（合同管理）
    "apps.cases",  # 3. CASES（案件管理）
    "apps.contacts",  # 3.1 工作人员联系方式
    "apps.reminders",  # 3.5 Reminders（重要日期提醒）
    "apps.automation",  # 5. 自动化工具
    "apps.message_hub.apps.MessageHubConfig",  # 5.1 信息中转站
    "apps.image_rotation",  # 5.1 图片自动旋转（从 automation 拆分）
    "apps.invoice_recognition",  # 5.2 发票识别（从 automation 拆分）
    "apps.document_recognition",  # 5.4 文书智能识别（从 automation 拆分）
    "apps.document_parsing",  # 5.405 文档解析（MinerU 集成）
    "apps.labor_arbitration",  # 5.406 劳动仲裁文书爬虫（佛山人社局）
    "apps.express_query",  # 5.41 快递查询
    "apps.pdf_splitting",  # 5.45 PDF 拆解
    "apps.batch_printing",  # 5.455 批量打印
    "apps.story_viz",  # 5.46 故事可视化
    "apps.evidence",  # 5.5 证据管理
    "apps.evidence_sorting",  # 5.51 案件材料整理（财务单据分类/对账单比对）
    "apps.documents",  # 6. 文书生成
    "apps.chat_records",  # 6.0 聊天记录梳理
    "apps.litigation_ai",  # 6.1 AI 诉讼文书生成
    "apps.contract_review",  # 6.2 合同审查
    "apps.finance",  # 6.3.1 金融工具(LPR计算器)
    "apps.oa_filing",  # 6.4 OA立案
    "apps.legal_research",  # 6.5 案例检索（法律数据源）
    "apps.legal_solution",  # 6.6 法律服务方案
    "apps.enterprise_data",  # 6.6 企业数据查询（天眼查/企查查等）
    "apps.doc_convert",  # 6.7 要素式转换（传统文书转要素式文书）
    "apps.doc_converter",  # 6.71 DOC 批量转 DOCX
    "apps.workbench",  # 6.8 工作台（AI 对话式操作中心）
    "apps.workflow",  # 6.9 工作流引擎（Temporal 集成）
    "apps.docspace",  # 6.95 DocSpace 云文档
    "apps.core",  # 7. 核心系统
    "apps.cloud_storage",  # 7.0 云存储（自 core 拆分的独立 app，表名钉死 core_cloudstorageaccount）
    "apps.social_auth",  # 7.1 社交登录
    "django_q",  # 8. DJANGO Q
]

MIDDLEWARE = [
    # 响应压缩放最外层：列表 JSON（中文文本）压缩率通常 5-8 倍。
    # SSE/流式响应兼容——Django 的 compress_sequence 每个事件块后立即
    # flush() 并 yield，不会缓冲整流（workbench stream_chat 可安全过压缩）。
    "django.middleware.gzip.GZipMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # 请求级 statement_timeout（仅生产 + PostgreSQL 生效，DEBUG/非 PG 自动跳过）：
    # 放在所有会查 DB 的中间件（限流/Session/Auth/视图）之外，覆盖面最大；
    # 紧贴 RequestId 保持基础设施中间件分组。Django-Q worker 不跑中间件栈，
    # 其长任务 SQL 不受影响（详见模块 docstring 的防误伤论证）。
    "apps.core.middleware.db_statement_timeout.DbStatementTimeoutMiddleware",
    # RequestId 在限流之外：429 短路响应也要带 X-Request-ID，
    # 且限流命中时的告警日志能关联到 request context。
    "apps.core.middleware.request_id.RequestIdMiddleware",
    "apps.core.middleware.token_rate_limit.TokenRateLimitMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "apps.organization.middleware.ApiTrailingSlashMiddleware",
    "django.middleware.common.CommonMiddleware",
    "ninja.compatibility.files.fix_request_files_middleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "apps.organization.middleware.OrgAccessMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.core.middleware.PermissionsPolicyMiddleware",
    "apps.core.middleware.ServiceLocatorScopeMiddleware",
]

_request_timing_env = (os.environ.get("DJANGO_REQUEST_TIMING", "") or "").lower().strip()
_enable_request_timing = _request_timing_env in ("true", "1", "yes") or (_request_timing_env == "" and not DEBUG)

_request_metrics_env = (os.environ.get("DJANGO_REQUEST_METRICS", "") or "").lower().strip()
_enable_request_metrics = _request_metrics_env in ("true", "1", "yes") or (_request_metrics_env == "" and not DEBUG)

_service_locator_scope_env = (os.environ.get("DJANGO_SERVICE_LOCATOR_SCOPE", "") or "").lower().strip()
_enable_service_locator_scope = _service_locator_scope_env not in ("false", "0", "no")

ROOT_URLCONF = "apiSystem.urls"

# 禁用 Django 的自动尾部斜杠重定向
# API 路由由 ApiTrailingSlashMiddleware 统一处理（移除尾部斜杠）
APPEND_SLASH = False

# 生产环境使用 cached.Loader 缓存模板 AST，避免 40+ app 的 templates/ 目录扫描
# DEBUG 模式不缓存（模板修改需即时生效）
if not DEBUG:
    _template_loaders: list[tuple[str, list[str]]] | None = [
        (
            "django.template.loaders.cached.Loader",
            [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
        ),
    ]
else:
    _template_loaders = None

_TEMPLATE_DIRS: list[str | Path] = [BASE_DIR / "templates"]
try:
    from plugins import has_court_automation_plugin  # type: ignore[attr-defined]

    if has_court_automation_plugin():
        _TEMPLATE_DIRS.append(os.path.join(BASE_DIR, "..", "plugins", "court_automation", "templates"))
except ImportError:
    pass
try:
    from plugins import has_doc_convert_plugin  # type: ignore[attr-defined]

    if has_doc_convert_plugin():
        _TEMPLATE_DIRS.append(os.path.join(BASE_DIR, "..", "plugins", "doc_convert", "templates"))
except ImportError:
    pass

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": _TEMPLATE_DIRS,
        **({"APP_DIRS": True} if _template_loaders is None else {}),
        "OPTIONS": {
            **({"loaders": _template_loaders} if _template_loaders else {}),
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "apiSystem.wsgi.application"

# ============================================================
# 数据库配置
# ============================================================

DB_ENGINE = (os.environ.get("DB_ENGINE", "postgresql") or "postgresql").strip().lower()
DATABASE_PATH = (os.environ.get("DATABASE_PATH", "") or "").strip()


def _get_env_str(name: str, default: str = "", *, allow_empty: bool = False) -> str:
    raw_value = os.environ.get(name)
    value = (default if raw_value is None else raw_value).strip()
    if not value and not allow_empty:
        raise RuntimeError(f"DB_ENGINE={DB_ENGINE} 时必须设置环境变量 {name}")
    return value


if DB_ENGINE in ("sqlite", "sqlite3", "django.db.backends.sqlite3"):
    db_name = DATABASE_PATH if DATABASE_PATH else BASE_DIR / "db.sqlite3"
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": db_name,
            "AUTOCOMMIT": True,
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": False,
            "OPTIONS": {
                "timeout": 20,
            },
            "ATOMIC_REQUESTS": False,
            "TIME_ZONE": None,
        }
    }
elif DB_ENGINE in ("", "postgres", "postgresql", "django.db.backends.postgresql"):
    # 连接复用：开发默认 60s、生产默认 600s（每请求省一次 TCP+PG 认证握手）。
    # 历史上开发环境用 0（每请求建连即释放）是为了规避多进程下 "too many clients"；
    # 现改为温和复用 + 环境变量 DB_CONN_MAX_AGE 可随时覆盖（设 0 恢复旧行为）。
    # CONN_HEALTH_CHECKS=True 保证复用前先探活，剔除被 PG 重启/超时杀掉的连接。
    _default_conn_max_age = 60 if DEBUG else 600
    try:
        _conn_max_age = int(os.environ.get("DB_CONN_MAX_AGE", "") or _default_conn_max_age)
    except ValueError:
        _conn_max_age = _default_conn_max_age

    # psycopg3 进程级连接池（Django 5.1+ OPTIONS["pool"]）。
    # - 与 CONN_MAX_AGE 持久连接互斥：启用 pool 时强制 CONN_MAX_AGE=0（连接由池管理）。
    # - 池是进程内共享的：线程型 ASGI worker 的所有请求线程复用同一组连接，
    #   比「每线程 CONN_MAX_AGE 各持一条」省连接；但 max_size 会限制并发 DB 线程数。
    # - 开关 DB_POOL：默认 dev(DEBUG) 开、生产关（生产的并发模型需按部署评估后再开），
    #   显式 true/false 永远优先；pytest 下强制关（测试库每次重建，池会持有失效连接）。
    _pool_env = (os.environ.get("DB_POOL", "") or "").strip().lower()
    _use_pool = (_pool_env in ("true", "1", "yes")) or (_pool_env == "" and DEBUG)
    if "pytest" in sys.modules:
        _use_pool = False

    # PG 会话级超时治理（通过连接 options 注入，对整个进程的所有连接生效）：
    #
    # idle_in_transaction_session_timeout —— 全局生效（DEBUG 与生产一致）。
    #   只杀「持有未提交事务且空闲」的会话（请求中途崩溃残留的 atomic、
    #   泄漏的事务锁），不影响健康负载：已核查长任务（批量分析 timeout=7200s、
    #   OA 同步 3600s）的 transaction.atomic 均只包裹短 SQL（bulk_update /
    #   bulk_create），分钟级 Playwright/文件 IO 全部在事务外，不会触发。
    #   DEBUG 下沿用更紧的 60s（CI 中快速暴露 hang 住的事务），生产 300s。
    #
    # statement_timeout —— 仅 DEBUG 注入，生产不启用。原因：Django-Q worker
    #   与 web 共用同一 DATABASES["default"]（Q_CLUSTER 无独立 alias），无法
    #   按「web / worker」区分注入；全局 statement_timeout 会把 worker 里
    #   长任务的慢 SQL（批量分析、OA 全量同步）中途杀掉。生产的 web 慢 SQL
    #   治理走请求级方案：DbStatementTimeoutMiddleware（见 MIDDLEWARE 注册处）
    #   在每个 web 请求内 SET/RESET statement_timeout（env
    #   DB_WEB_STATEMENT_TIMEOUT_MS，默认 60000；worker 进程不跑中间件栈，
    #   长任务不受影响），不在连接级全局设置。
    _pg_options: dict[str, object] = {"connect_timeout": 10}
    _idle_tx_default = "60000" if DEBUG else "300000"
    _idle_tx_timeout = os.environ.get("DB_IDLE_IN_TX_TIMEOUT_MS", _idle_tx_default)
    _pg_opts = [f"-c idle_in_transaction_session_timeout={_idle_tx_timeout}"]
    if DEBUG:
        # 防止 flaky test 在 psycopg socket wait 中 hang 住导致 CI 60 分钟超时。
        # 默认 120000（2 分钟），避免 Django flush（TRUNCATE 所有表）在 CI 中超时。
        _stmt_timeout = os.environ.get("DB_STATEMENT_TIMEOUT_MS", "120000")
        _pg_opts.append(f"-c statement_timeout={_stmt_timeout}")
    _pg_options["options"] = " ".join(_pg_opts)

    if _use_pool:
        try:
            _pool_min = max(1, int(os.environ.get("DB_POOL_MIN", "2")))
            _pool_max = max(_pool_min, int(os.environ.get("DB_POOL_MAX", "16")))
        except ValueError:
            _pool_min, _pool_max = 2, 16
        # timeout：池满时 get() 的最长等待（psycopg_pool 默认 30s，实测会让第 9 个
        # 并发借入者挂半分钟；收到 10s 快速暴露容量问题，由调用方重试/降级）。
        # max_size 默认 16 覆盖 uvicorn threadpool 常见并发，生产开启时按部署调大。
        _pg_options["pool"] = {"min_size": _pool_min, "max_size": _pool_max, "timeout": 10}
        _conn_max_age = 0  # pool 接管连接生命周期，持久连接必须关闭

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _get_env_str("DB_NAME", "fachuan_dev"),
            "USER": _get_env_str("DB_USER", "postgres"),
            "PASSWORD": _get_env_str("DB_PASSWORD", "postgres", allow_empty=True),
            "HOST": _get_env_str("DB_HOST", "127.0.0.1"),
            "PORT": int(os.environ.get("DB_PORT", "5432") or "5432"),
            "CONN_MAX_AGE": _conn_max_age,
            "CONN_HEALTH_CHECKS": not _use_pool,
            "OPTIONS": _pg_options,
        }
    }
elif DB_ENGINE in ("mysql", "django.db.backends.mysql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": _get_env_str("DB_NAME"),
            "USER": _get_env_str("DB_USER"),
            "PASSWORD": _get_env_str("DB_PASSWORD"),
            "HOST": _get_env_str("DB_HOST"),
            "PORT": int(os.environ.get("DB_PORT", "3306") or "3306"),
            "CONN_MAX_AGE": 600,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    raise RuntimeError(f"不支持的 DB_ENGINE: {DB_ENGINE}")

from typing import Any

# 启用 SQLite 外键约束
from django.db.backends.signals import connection_created


def activate_foreign_keys(sender: Any, connection: Any, **kwargs: Any) -> None:
    """启用 SQLite 外键约束和 WAL 模式"""
    if connection.vendor == "sqlite":
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA busy_timeout = 30000;")


connection_created.connect(activate_foreign_keys)

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# JWT Token 有效期配置
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    # 安全审计 M-8（refresh token 30 天不轮换、无黑名单）：原配置下 refresh
    # token 一旦泄露（localStorage XSS、日志、Referer）有 30 天窗口，且每次
    # 刷新不轮换——被盗后攻击者可长期静默续期，无任何检测手段。
    #
    # 启用轮换 + 轮换后拉黑：每次 /token/refresh 都签发新 refresh，旧 refresh
    # 立即进入黑名单（OutstandingToken/BlacklistedToken 两张表），二次使用即
    # 报「Token is blacklisted」。被盗场景下，合法用户与被盗方的首次刷新会
    # 互相把对方的 token 打失效——至少把「无限续期」收敛成「一次性」。
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    # 安全审计 C-14/E-07（改密后旧 token 仍有效）：签发时在 token 注入密码哈希
    # 指纹 claim，刷新时校验一致性——密码一改旧 refresh token 全部失效，零迁移实现
    "TOKEN_OBTAIN_PAIR_INPUT_SCHEMA": "apps.core.security.jwt_password_binding.PasswordBoundTokenObtainPairInputSchema",
    "TOKEN_OBTAIN_PAIR_REFRESH_INPUT_SCHEMA": "apps.core.security.jwt_password_binding.PasswordBoundTokenRefreshInputSchema",
}

# 安全审计 C-13：密码重置链接实际有效期与邮件文案（30 分钟）对齐
PASSWORD_RESET_TIMEOUT = 30 * 60

# Session 安全配置
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 7 天
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = False

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "zh-hans"

LANGUAGES = [
    ("zh-hans", "简体中文"),
]

LOCALE_PATHS = [
    BASE_DIR / "locale",
]

TIME_ZONE = "Asia/Shanghai"

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"

# 静态文件收集目录（Docker 部署需要）
STATIC_ROOT = os.environ.get("STATIC_ROOT", BASE_DIR / "staticfiles")

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "organization.Lawyer"

# ============================================================
# 登录配置
# ============================================================

LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/admin/"

ALLOW_FIRST_USER_SUPERUSER = (os.environ.get("ALLOW_FIRST_USER_SUPERUSER", "False") or "").lower() in (
    "true",
    "1",
    "yes",
)
BOOTSTRAP_ADMIN_TOKEN = (os.environ.get("BOOTSTRAP_ADMIN_TOKEN", "") or "").strip()
# auto_register 首用户引导口令（安全审计 2026Q4）：原为源码内硬编码 "1234qwer"，
# 任何人可在 DEBUG 实例上免令牌调用 /admin/register/ 的 auto_register 分支抢占
# 超管。现改为环境变量注入，无默认值——未配置时 auto_register_superadmin 直接
# 拒绝（fail-closed），源码不再保留任何可用口令。
AUTO_REGISTER_BOOTSTRAP_PASSWORD = (os.environ.get("AUTO_REGISTER_BOOTSTRAP_PASSWORD", "") or "").strip()
# 表单注册入口开关（默认关闭）：/admin/register/ 的表单注册在 False 时直接拒绝
# （apps/organization/views.py register 视图消费）；auto_register 首用户引导分支
# （BOOTSTRAP_ADMIN_TOKEN 保护）不受此开关影响。API 侧 /api/v1/organization/register
# 独立于本开关（注册后需管理员审批激活）。
ALLOW_ADMIN_REGISTER = (os.environ.get("ALLOW_ADMIN_REGISTER", "False") or "").lower() in ("true", "1", "yes")
_smoke_pw = os.environ.get("SMOKE_ADMIN_PASSWORD", "").strip()
if not _smoke_pw and not DEBUG:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("SMOKE_ADMIN_PASSWORD 环境变量未设置，生产环境必须配置此变量")
SMOKE_ADMIN_PASSWORD = _smoke_pw or "smoke_admin_password"  # DEBUG 模式下使用默认值

if (not DEBUG) and ALLOW_FIRST_USER_SUPERUSER and (not BOOTSTRAP_ADMIN_TOKEN):
    raise RuntimeError("ALLOW_FIRST_USER_SUPERUSER=true 时必须配置 BOOTSTRAP_ADMIN_TOKEN")

# auto_register 口令闸门（安全审计 2026Q4）：开启首用户引导时必须显式注入口令，
# 否则 auto_register_superadmin 会因口令为空而拒绝——此处提前 fail-fast，
# 把「配置漏项」暴露在启动阶段而非首次引导时。
if ALLOW_FIRST_USER_SUPERUSER and (not AUTO_REGISTER_BOOTSTRAP_PASSWORD):
    raise RuntimeError("ALLOW_FIRST_USER_SUPERUSER=true 时必须配置 AUTO_REGISTER_BOOTSTRAP_PASSWORD")

# ============================================================
# 社交登录
# ============================================================
# Provider 配置（App ID / Secret / 回调地址 / scope / 开关）统一维护在
# SystemConfig（分类 social_auth），见 admin/systemconfig/。
# 不在这里配置：密钥会落进环境变量，且改动要重启进程才生效。

FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:5090")

# ============================================================
# CORS 配置
# ============================================================

# 安全的 CORS 默认白名单（仅本地访问）
_SAFE_CORS_ORIGINS = [
    "http://localhost:5090",
    "http://localhost:3000",
    "http://127.0.0.1:5090",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

if DEBUG:
    _cors = resolve_cors_and_csrf(debug=True, allow_lan=_allow_lan, safe_cors_origins=_SAFE_CORS_ORIGINS)
else:
    _cors = resolve_cors_and_csrf(debug=False, allow_lan=_allow_lan, safe_cors_origins=_SAFE_CORS_ORIGINS)

CORS_ALLOW_ALL_ORIGINS = bool(_cors.get("CORS_ALLOW_ALL_ORIGINS", False))
CORS_ALLOWED_ORIGINS = _cors["CORS_ALLOWED_ORIGINS"]
CSRF_TRUSTED_ORIGINS = _cors["CSRF_TRUSTED_ORIGINS"]

CORS_ALLOW_CREDENTIALS = (os.environ.get("CORS_ALLOW_CREDENTIALS", "False") or "").lower() in ("true", "1", "yes")
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

MEDIA_URL = "/media/"
# 环境变量可覆盖（与 STATIC_ROOT 同款惯例），默认 backend/apiSystem/media
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT") or (BASE_DIR / "media"))

# 受保护媒体服务（默认启用——安全默认）：非 DEBUG 环境的 /media/ 由
# apps.core.api.media_protected.serve_protected_media 鉴权后发送（JWT 头 /
# ?token= / Session），案件文书、证件扫描件不再可被 URL 枚举裸读。
# DEBUG 开发环境仍走 static 直出不受影响；确需网关直出时显式设
# MEDIA_REQUIRE_AUTH=false 回到旧行为（不注册媒体路由）。
MEDIA_REQUIRE_AUTH = os.environ.get("MEDIA_REQUIRE_AUTH", "true").lower() in ("1", "true", "yes")
# 可选：nginx internal location 前缀（如 /protected_media/）。非空时视图只做鉴权，
# 返回 X-Accel-Redirect 头由 nginx 发文件（Django 不读文件）；为空时 Django FileResponse 流式返回。
MEDIA_X_ACCEL_PREFIX = (os.environ.get("MEDIA_X_ACCEL_PREFIX", "") or "").strip()

# 短时下载票据（安全审计 M-2）。JWT 不再经 ?token= 查询参数传递——完整 JWT
# 会落入 nginx access log / 浏览器历史 / Referer。改为：需要放进 URL 的
# <img>/<iframe>/<a download> 场景用 60 秒一次性票据（见
# apps/core/security/download_tickets.py），票据泄露也换不来身份。
# TTL 只影响「从签发到浏览器发起请求」的窗口，60s 足够慢网一次跳转。
DOWNLOAD_TICKET_TTL_SECONDS = int(os.environ.get("DOWNLOAD_TICKET_TTL_SECONDS", "60"))
# 单次使用：兑现后即失效，重放被拒。缓存后端故障时退化为「仅签名 + 过期」，
# 不因缓存挂了拒绝合法下载。
DOWNLOAD_TICKET_SINGLE_USE = os.environ.get("DOWNLOAD_TICKET_SINGLE_USE", "true").lower() in ("1", "true", "yes")

# 验证码识别服务间共享密钥（安全审计 M-5）。
#
# /api/v1/automation/captcha/recognize 原为 auth=None 的匿名端点，可被公网当
# 免费 OCR 刷。仓库内没有任何调用方走 HTTP 打它（浏览器自动化与插件全部进程内
# 直连 service），故改为要求 X-Captcha-Secret 头匹配此密钥。
#
# **未配置时端点整体不可用（fail-closed）**：生产忘配的表现是「功能不可用」，
# 而不是「匿名可刷」。确需对外开放（如外部脚本接入）时显式配置一个强随机值，
# 并同步给调用方。
CAPTCHA_RECOGNIZE_SECRET = (os.environ.get("CAPTCHA_RECOGNIZE_SECRET", "") or "").strip()

# ============================================================
# 请求体大小限制
# ============================================================

# 语义：DATA_UPLOAD_MAX_MEMORY_SIZE 只限制「非 multipart」请求体（如 JSON）
# 的大小，以及 multipart 中非文件字段的累计大小；multipart 文件上传不受
# 它限制（文件超过 FILE_UPLOAD_MAX_MEMORY_SIZE，默认 2.5MB，即流式落盘）。
#
# 取值依据：全仓唯一的大 JSON body 消费方是 image_rotation
# （/extract-pdf-fast、/detect-orientation 等以 Base64 内嵌图片/PDF）。
# 硬约束为 extract-pdf-fast 的单 PDF 上传：前端单文件上限 50MB
# （image_rotation.html MAX_PDF_SIZE），Base64 膨胀 4/3 ≈ 66.7MB，
# 故 70MB 是满足现有功能的最小值。批量图片端点（detect-orientation）
# 前端未限制张数，理论上可超任何上限，属前端契约问题，不靠此设置兜底。
DATA_UPLOAD_MAX_MEMORY_SIZE_MB = int(os.environ.get("DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE_MB", "70"))
DATA_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE_MB * 1024 * 1024

# 批量文档分析需要上传大量文件，默认 100 太小
DATA_UPLOAD_MAX_NUMBER_FILES = int(os.environ.get("DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES", "5000"))

CONTRACT_FOLDER_BROWSE_ROOTS = resolve_contract_folder_browse_roots()

FOLDER_BROWSE_ROOTS = CONTRACT_FOLDER_BROWSE_ROOTS

# 可选：仓库外私有 docx_templates 根目录（例如 /xx/documents/docx_templates）
DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT = (os.environ.get("DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT", "") or "").strip()
if DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT:
    DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT = str(Path(DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT).expanduser())

# ============================================================
# 要素式转换（znszj）配置
# ============================================================

# 是否启用传统文书转要素式文书功能（默认启用）
ZNSZJ_ENABLED = (os.environ.get("ZNSZJ_ENABLED", "True") or "").lower() not in ("false", "0", "no")

# 是否启用案例检索/案例下载后台创建功能（默认关闭）。
# 说明：当该开关为 False 时，仅在检测到私有 wk API 可用时才允许创建任务。
LEGAL_RESEARCH_ADMIN_FEATURE_ENABLED = (
    os.environ.get("LEGAL_RESEARCH_ADMIN_FEATURE_ENABLED", "False") or ""
).lower() in ("true", "1", "yes")

# 是否启用 OnlyOffice DocSpace 云文档编辑（默认关闭）
DOCSPACE_ENABLED = (os.environ.get("DOCSPACE_ENABLED", "False") or "").lower() in ("true", "1", "yes")

# ============================================================
# Django Q 配置
# ============================================================

# 集群名按 SECRET_KEY 指纹派生：key 轮换后新旧进程不再共抢同一 Redis 队列，
# 旧 key 签名的任务不会被新集群以 BadSignature 静默丢弃（反之亦然）。
Q_CLUSTER = resolve_q_cluster(secret_key=SECRET_KEY)

# ============================================================
# 基础配置（保留少量必要配置）
# ============================================================

# 调试开关
PERM_OPEN_ACCESS = resolve_perm_open_access(is_production=_is_production)

# API 版本
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
API_VERSION = "1.0.0"

# 请求限流配置
RATE_LIMIT = resolve_rate_limit()
if not DEBUG:
    _trust_xff_env = (os.environ.get("DJANGO_TRUST_X_FORWARDED_FOR", "") or "").lower().strip()
    _trust_xff = _trust_xff_env in ("true", "1", "yes")
    _trusted_proxies_env = (os.environ.get("DJANGO_TRUSTED_PROXY_IPS", "") or "").strip()
    if _trust_xff and not _trusted_proxies_env:
        raise RuntimeError("生产环境启用 DJANGO_TRUST_X_FORWARDED_FOR 必须配置 DJANGO_TRUSTED_PROXY_IPS")

# 可配置的客户端真实 IP 头（默认 None，行为与原先完全一致）。
#
# 适用场景（Cloudflare Tunnel / CDN）：REMOTE_ADDR 恒为隧道/代理地址，所有用户
# 共享同一个限流桶；而 X-Forwarded-For 的左值可被客户端伪造，不可直接采信。
# Cloudflare 会在每个请求上覆盖写入 CF-Connecting-IP（客户端无法伪造），此时配置：
#
#   DJANGO_CLIENT_IP_HEADER=CF-Connecting-IP        # 或 META 形式 HTTP_CF_CONNECTING_IP
#
# 生效前提（防伪造）：直连对端 REMOTE_ADDR 必须属于 DJANGO_TRUSTED_PROXY_IPS
# 列出的受信代理；否则该头被忽略，回退原有 X-Forwarded-For / REMOTE_ADDR 逻辑。
# 消费方：apps/core/infrastructure/throttling.py（RateLimiter.get_client_ip 链路最前）。
_client_ip_header_env = (os.environ.get("DJANGO_CLIENT_IP_HEADER", "") or "").strip()
DJANGO_CLIENT_IP_HEADER: str | None = _client_ip_header_env or None

# ============================================================
# 日志和缓存配置
# ============================================================

from apps.core.infrastructure import get_cache_config
from apps.core.infrastructure.logging import get_logging_config

LOGGING = get_logging_config(BASE_DIR.parent, DEBUG)
CACHES = get_cache_config()

# Session 后端：cached_db 先查缓存再查 DB，写回双写，零中断迁移
# 生产有 Redis 时完全消除 session DB 查询；无 Redis 时退化为 DB（与之前一致）
SESSION_ENGINE = os.environ.get("SESSION_ENGINE", "django.contrib.sessions.backends.cached_db")
SESSION_CACHE_ALIAS = "default"

SENTRY_DSN = (os.environ.get("SENTRY_DSN", "") or "").strip()
if SENTRY_DSN:
    try:
        import logging

        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.httpx import HttpxIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        def _sentry_before_send(event: dict, hint: dict) -> dict:  # type: ignore[type-arg]
            """Sentry before_send 钩子：注入 request_id / trace_id / task_name 到 tags"""
            try:
                from apps.core.infrastructure.request_context import get_request_id, get_task_name, get_trace_ids

                request_id = get_request_id(fallback_generate=False)
                trace_id, span_id = get_trace_ids()
                task_name = get_task_name()

                tags = event.setdefault("tags", {})
                if request_id:
                    tags["request_id"] = request_id
                if trace_id:
                    tags["trace_id"] = trace_id
                if span_id:
                    tags["span_id"] = span_id
                if task_name:
                    tags["task_name"] = task_name

                contexts = event.setdefault("contexts", {})
                app_ctx = contexts.setdefault("app", {})
                if request_id:
                    app_ctx["request_id"] = request_id
                if task_name:
                    app_ctx["task_name"] = task_name
            except Exception:
                pass
            return event

        # APM 采样率：开发默认 0（避免本地噪音），生产默认 0.1（10% 采样）
        _sentry_traces_rate_env = (os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "") or "").strip()
        if _sentry_traces_rate_env:
            _sentry_traces_rate = float(_sentry_traces_rate_env)
        elif DEBUG:
            _sentry_traces_rate = 0.0
        else:
            _sentry_traces_rate = 0.1

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[
                DjangoIntegration(),
                HttpxIntegration(),  # 自动追踪出站 HTTP 请求（法院系统/LLM 接口等）
                LoggingIntegration(
                    level=logging.INFO,  # Capture INFO and above as breadcrumbs
                    event_level=logging.ERROR,  # Send ERROR and above as events
                ),
            ],
            traces_sample_rate=_sentry_traces_rate,
            send_default_pii=False,
            environment=os.environ.get("ENVIRONMENT_TYPE", "production"),
            release=os.environ.get("APP_VERSION", None),
            before_send=_sentry_before_send,
        )
    except Exception:
        import logging

        logging.getLogger("apiSystem.settings").exception("Sentry 初始化失败")

# ============================================================
# Django Channels 配置
# ============================================================

# WebSocket Channel Layer 配置
# 开发/单进程环境使用 InMemoryChannelLayer（无需 Redis）
# 生产/多进程环境可升级到 Redis 后端
CHANNEL_LAYERS = resolve_channel_layers()

# ASGI Application
ASGI_APPLICATION = "apiSystem.asgi.application"

if not DEBUG:
    # 拓扑守卫：web 进程数合并 WEB_CONCURRENCY/UVICORN_WORKERS/GUNICORN_WORKERS
    # （盲区修正：docker-entrypoint.sh 的 uvicorn 缺省 4 workers 此前不被察觉）；
    # q_workers 复用 Q_CLUSTER 已解析值（其缺省 8 与旧守卫读 DJANGO_Q_WORKERS
    # 的缺省 1 不一致，一并消除）。校验逻辑在 django_runtime.validate_runtime_topology。
    _channel_layers_map: dict[str, Any] = dict(CHANNEL_LAYERS.items()) if isinstance(CHANNEL_LAYERS, dict) else {}
    _topology_warnings = validate_runtime_topology(
        debug=DEBUG,
        web_workers=resolve_web_worker_count(),
        q_workers=int(Q_CLUSTER["workers"]),  # type: ignore[arg-type]
        cache_backend=((CACHES or {}).get("default", {}) or {}).get("BACKEND", ""),
        channel_backend=(_channel_layers_map.get("default") or {}).get("BACKEND", ""),
        redis_cache_configured=bool(resolve_cache_redis_url()),
        redis_channel_configured=bool(resolve_channel_redis_url()),
    )
    if _topology_warnings:
        import logging as _logging

        _settings_logger = _logging.getLogger("apiSystem.settings")
        for _warn in _topology_warnings:
            _settings_logger.warning(_warn)

# ============================================================
# Django Admin 界面配置
# ============================================================

ADMIN_SITE_HEADER = "法穿SI Copilot"
ADMIN_SITE_TITLE = "免费开源，尽情使用"
ADMIN_INDEX_TITLE = "法穿SI Copilot"

# ============================================================
# 浏览器安全策略配置
# ============================================================

SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "SAMEORIGIN"

PERMISSIONS_POLICY = {
    "geolocation": [],
    "camera": [],
    "microphone": [],
}

CONTENT_SECURITY_POLICY_REPORT_ONLY = (os.environ.get("CONTENT_SECURITY_POLICY_REPORT_ONLY", "") or "").strip()
CONTENT_SECURITY_POLICY = (os.environ.get("CONTENT_SECURITY_POLICY", "") or "").strip()
CONTENT_SECURITY_POLICY_API_REPORT_ONLY = (os.environ.get("CONTENT_SECURITY_POLICY_API_REPORT_ONLY", "") or "").strip()
CONTENT_SECURITY_POLICY_API = (os.environ.get("CONTENT_SECURITY_POLICY_API", "") or "").strip()
CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY = (
    os.environ.get("CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY", "") or ""
).strip()
CONTENT_SECURITY_POLICY_ADMIN = (os.environ.get("CONTENT_SECURITY_POLICY_ADMIN", "") or "").strip()
CROSS_ORIGIN_OPENER_POLICY = (os.environ.get("CROSS_ORIGIN_OPENER_POLICY", "") or "").strip()
CROSS_ORIGIN_RESOURCE_POLICY = (os.environ.get("CROSS_ORIGIN_RESOURCE_POLICY", "") or "").strip()
CROSS_ORIGIN_EMBEDDER_POLICY = (os.environ.get("CROSS_ORIGIN_EMBEDDER_POLICY", "") or "").strip()

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() in ("true", "1", "yes")
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get("SECURE_HSTS_INCLUDE_SUBDOMAINS", "True").lower() in (
        "true",
        "1",
        "yes",
    )
    SECURE_HSTS_PRELOAD = os.environ.get("SECURE_HSTS_PRELOAD", "True").lower() in ("true", "1", "yes")
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "True").lower() in ("true", "1", "yes")
    CSRF_COOKIE_SECURE = os.environ.get("CSRF_COOKIE_SECURE", "True").lower() in ("true", "1", "yes")
    SESSION_COOKIE_HTTPONLY = os.environ.get("SESSION_COOKIE_HTTPONLY", "True").lower() in ("true", "1", "yes")
    CSRF_COOKIE_HTTPONLY = os.environ.get("CSRF_COOKIE_HTTPONLY", "True").lower() in ("true", "1", "yes")
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
    if os.environ.get("DJANGO_SECURE_PROXY_SSL_HEADER", "False").lower() in ("true", "1", "yes"):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        USE_X_FORWARDED_HOST = os.environ.get("USE_X_FORWARDED_HOST", "False").lower() in ("true", "1", "yes")
    X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")
    _default_csp_policy = (
        "default-src 'self' data: blob:; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "base-uri 'self'"
    )
    _default_csp_api_policy = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'"
    )
    _csp_enforce_env = (os.environ.get("CONTENT_SECURITY_POLICY_ENFORCE", "") or "").lower().strip()
    _csp_enforce_enabled = _csp_enforce_env in ("true", "1", "yes")
    if _csp_enforce_enabled and not CONTENT_SECURITY_POLICY:
        if CONTENT_SECURITY_POLICY_REPORT_ONLY:
            CONTENT_SECURITY_POLICY = CONTENT_SECURITY_POLICY_REPORT_ONLY
            CONTENT_SECURITY_POLICY_REPORT_ONLY = ""
        else:
            CONTENT_SECURITY_POLICY = _default_csp_policy
    if _csp_enforce_enabled and not CONTENT_SECURITY_POLICY_API:
        if CONTENT_SECURITY_POLICY_API_REPORT_ONLY:
            CONTENT_SECURITY_POLICY_API = CONTENT_SECURITY_POLICY_API_REPORT_ONLY
            CONTENT_SECURITY_POLICY_API_REPORT_ONLY = ""
        else:
            CONTENT_SECURITY_POLICY_API = _default_csp_api_policy
    if (not _csp_enforce_enabled) and (not CONTENT_SECURITY_POLICY_REPORT_ONLY) and (not CONTENT_SECURITY_POLICY):
        CONTENT_SECURITY_POLICY_REPORT_ONLY = _default_csp_policy
    if (not CONTENT_SECURITY_POLICY_API_REPORT_ONLY) and (not CONTENT_SECURITY_POLICY_API):
        CONTENT_SECURITY_POLICY_API_REPORT_ONLY = _default_csp_api_policy
    if not CROSS_ORIGIN_OPENER_POLICY:
        CROSS_ORIGIN_OPENER_POLICY = "same-origin"
    if not CROSS_ORIGIN_RESOURCE_POLICY:
        CROSS_ORIGIN_RESOURCE_POLICY = "same-origin"
    if not CROSS_ORIGIN_EMBEDDER_POLICY:
        CROSS_ORIGIN_EMBEDDER_POLICY = "unsafe-none"

# ============================================================
# 诉讼文书生成 Agent 配置
# ============================================================

# 是否使用 Agent 模式（False 使用旧的状态机模式）
LITIGATION_USE_AGENT_MODE = os.environ.get("LITIGATION_USE_AGENT_MODE", "False").lower() in ("true", "1", "yes")

# Agent 使用的 LLM 模型（默认使用系统配置的模型）
LITIGATION_AGENT_MODEL = os.environ.get("LITIGATION_AGENT_MODEL", None)

# Agent LLM 温度参数
LITIGATION_AGENT_TEMPERATURE = float(os.environ.get("LITIGATION_AGENT_TEMPERATURE", "0.7"))

# 触发对话摘要的 token 阈值
LITIGATION_AGENT_SUMMARIZATION_THRESHOLD = int(os.environ.get("LITIGATION_AGENT_SUMMARIZATION_THRESHOLD", "2000"))

# 摘要时保留的最近消息数量
LITIGATION_AGENT_PRESERVE_MESSAGES = int(os.environ.get("LITIGATION_AGENT_PRESERVE_MESSAGES", "10"))

# Agent 最大迭代次数（防止无限循环）
LITIGATION_AGENT_MAX_ITERATIONS = int(os.environ.get("LITIGATION_AGENT_MAX_ITERATIONS", "10"))
