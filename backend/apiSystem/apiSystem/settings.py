"""
Django settings for apiSystem project.
"""

import os
from pathlib import Path

import django_stubs_ext
from django.utils.translation import gettext_lazy as _

django_stubs_ext.monkeypatch()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

from apps.core.config.django_runtime import (
    resolve_channel_layers,
    resolve_contract_folder_browse_roots,
    resolve_cors_and_csrf,
    resolve_perm_open_access,
    resolve_q_cluster,
    resolve_rate_limit,
    resolve_security_config,
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
_DEV_SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"

_security = resolve_security_config(
    dev_secret_key=_DEV_SECRET_KEY,
    default_allowed_hosts_dev=["*"],
    default_allowed_hosts_prod=["*"],
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
    "nested_admin",
    "corsheaders",
    "ninja_jwt",
    "channels",  # WebSocket 支持
    # === Django Admin 侧边栏顺序（按以下顺序显示）===
    "apps.client",  # 1. Client CRM（当事人管理）
    "apps.contracts",  # 2. Contracts（合同管理）
    "apps.cases",  # 3. CASES（案件管理）
    "apps.reminders",  # 3.5 Reminders（重要日期提醒）
    "apps.automation",  # 5. 自动化工具
    "apps.image_rotation",  # 5.1 图片自动旋转（从 automation 拆分）
    "apps.invoice_recognition",  # 5.2 发票识别（从 automation 拆分）
    "apps.fee_notice",  # 5.3 交费通知书识别（从 automation 拆分）
    "apps.preservation_date",  # 5.35 财产保全日期识别（从 automation 拆分）
    "apps.document_recognition",  # 5.4 文书智能识别（从 automation 拆分）
    "apps.pdf_splitting",  # 5.45 PDF 拆解
    "apps.evidence",  # 5.5 证据管理
    "apps.documents",  # 6. 文书生成
    "apps.chat_records",  # 6.0 聊天记录梳理
    "apps.litigation_ai",  # 6.1 AI 诉讼文书生成
    "apps.contract_review",  # 6.2 合同审查
    "apps.sales_dispute",  # 6.3 买卖纠纷计算
    "apps.finance",  # 6.3.1 金融工具(LPR计算器)
    "apps.oa_filing",  # 6.4 OA立案
    "apps.legal_research",  # 6.5 案例检索（法律数据源）
    "apps.enterprise_data",  # 6.6 企业数据查询（天眼查/企查查等）
    "apps.core",  # 7. 核心系统
    "django_q",  # 8. DJANGO Q
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware_request_id.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "apps.organization.middleware.ApiTrailingSlashMiddleware",
    "django.middleware.common.CommonMiddleware",
    "ninja.compatibility.files.fix_request_files_middleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # 全局模板目录
        "APP_DIRS": True,
        "OPTIONS": {
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

DB_ENGINE = (os.environ.get("DB_ENGINE", "") or "").strip().lower()
DATABASE_PATH = (os.environ.get("DATABASE_PATH", "") or "").strip()


def _require_env_str(name: str) -> str:
    value = (os.environ.get(name, "") or "").strip()
    if not value:
        raise RuntimeError(f"DB_ENGINE={DB_ENGINE} 时必须设置环境变量 {name}")
    return value


if DB_ENGINE in ("", "sqlite", "sqlite3", "django.db.backends.sqlite3"):
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
elif DB_ENGINE in ("postgres", "postgresql", "django.db.backends.postgresql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _require_env_str("DB_NAME"),
            "USER": _require_env_str("DB_USER"),
            "PASSWORD": _require_env_str("DB_PASSWORD"),
            "HOST": _require_env_str("DB_HOST"),
            "PORT": int(os.environ.get("DB_PORT", "5432") or "5432"),
            "CONN_MAX_AGE": 600,
            "CONN_HEALTH_CHECKS": True,
        }
    }
elif DB_ENGINE in ("mysql", "django.db.backends.mysql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": _require_env_str("DB_NAME"),
            "USER": _require_env_str("DB_USER"),
            "PASSWORD": _require_env_str("DB_PASSWORD"),
            "HOST": _require_env_str("DB_HOST"),
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

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "zh-hans"

LANGUAGES = [
    ("zh-hans", _("简体中文")),
    ("en", _("English")),
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

ALLOW_FIRST_USER_SUPERUSER = (os.environ.get("ALLOW_FIRST_USER_SUPERUSER", "False") or "").lower() in (
    "true",
    "1",
    "yes",
)
BOOTSTRAP_ADMIN_TOKEN = (os.environ.get("BOOTSTRAP_ADMIN_TOKEN", "") or "").strip()
ALLOW_ADMIN_REGISTER = (os.environ.get("ALLOW_ADMIN_REGISTER", "False") or "").lower() in ("true", "1", "yes")
_smoke_pw = os.environ.get("SMOKE_ADMIN_PASSWORD", "").strip()
if not _smoke_pw and not DEBUG:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("SMOKE_ADMIN_PASSWORD 环境变量未设置，生产环境必须配置此变量")
SMOKE_ADMIN_PASSWORD = _smoke_pw or "smoke_admin_password"  # DEBUG 模式下使用默认值

if (not DEBUG) and ALLOW_FIRST_USER_SUPERUSER and (not BOOTSTRAP_ADMIN_TOKEN):
    raise RuntimeError("ALLOW_FIRST_USER_SUPERUSER=true 时必须配置 BOOTSTRAP_ADMIN_TOKEN")

# ============================================================
# CORS 配置
# ============================================================

# 安全的 CORS 默认白名单（仅本地访问）
_SAFE_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
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
MEDIA_ROOT = BASE_DIR / "media"

# ============================================================
# 请求体大小限制
# ============================================================

# 默认 2.5MB 太小，图片旋转工具需要上传大量 Base64 数据
# multipart/form-data 上传也会受到此限制
DATA_UPLOAD_MAX_MEMORY_SIZE_MB = int(os.environ.get("DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE_MB", "100"))
DATA_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE_MB * 1024 * 1024

CONTRACT_FOLDER_BROWSE_ROOTS = resolve_contract_folder_browse_roots()

FOLDER_BROWSE_ROOTS = CONTRACT_FOLDER_BROWSE_ROOTS

# ============================================================
# Django Q 配置
# ============================================================

Q_CLUSTER = resolve_q_cluster()


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

# ============================================================
# 日志和缓存配置
# ============================================================

from apps.core.infrastructure import get_cache_config
from apps.core.logging import get_logging_config

LOGGING = get_logging_config(BASE_DIR.parent, DEBUG)
CACHES = get_cache_config()

SENTRY_DSN = (os.environ.get("SENTRY_DSN", "") or "").strip()
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0") or "0"),
            send_default_pii=False,
            environment=os.environ.get("ENVIRONMENT_TYPE", "production"),
            release=os.environ.get("APP_VERSION", None),
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
    _web_concurrency = int(os.environ.get("WEB_CONCURRENCY", "1") or "1")
    _q_workers = int(os.environ.get("DJANGO_Q_WORKERS", "1") or "1")
    _multiprocess = _web_concurrency > 1 or _q_workers > 1
    if _multiprocess:
        _cache_backend = ((CACHES or {}).get("default", {}) or {}).get("BACKEND", "")
        if _cache_backend == "django.core.cache.backends.locmem.LocMemCache":
            raise RuntimeError("生产多进程环境必须配置 Redis cache（DJANGO_CACHE_REDIS_URL）以保证限流一致性")

        _channel_layers: dict[str, Any] = dict(CHANNEL_LAYERS.items()) if isinstance(CHANNEL_LAYERS, dict) else {}
        _channel_backend = (_channel_layers.get("default") or {}).get("BACKEND", "")
        if _channel_backend == "channels.layers.InMemoryChannelLayer":
            raise RuntimeError("生产多进程环境必须配置 Redis channel layer（DJANGO_CHANNEL_REDIS_URL）")

# ============================================================
# Django Admin 界面配置
# ============================================================

ADMIN_SITE_HEADER = "法穿AI案件管理系统"
ADMIN_SITE_TITLE = "免费开源，尽情使用"
ADMIN_INDEX_TITLE = "法穿AI案件管理系统"

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
