"""
配置模式注册表

定义系统中所有配置项的模式，包括 Django 核心、第三方服务、群聊平台、业务功能配置
"""
from typing import Dict
from .field import ConfigField


def create_config_registry() -> Dict[str, ConfigField]:
    """
    创建完整的配置模式注册表
    
    Returns:
        Dict[str, ConfigField]: 配置字段注册表，键为配置路径，值为字段定义
    """
    registry = {}
    
    # ==================== Django 核心配置 ====================
    
    # 基础配置
    registry["django.secret_key"] = ConfigField(
        name="django.secret_key",
        type=str,
        required=True,
        sensitive=True,
        env_var="SECRET_KEY",
        description="Django 密钥，用于加密和签名",
        min_length=50
    )
    
    registry["django.debug"] = ConfigField(
        name="django.debug",
        type=bool,
        default=False,
        env_var="DEBUG",
        description="调试模式开关，生产环境必须为 False"
    )
    
    registry["django.allowed_hosts"] = ConfigField(
        name="django.allowed_hosts",
        type=list,
        default=["localhost", "127.0.0.1"],
        description="允许的主机列表"
    )
    
    # 数据库配置
    registry["database.engine"] = ConfigField(
        name="database.engine",
        type=str,
        default="django.db.backends.mysql",
        choices=[
            "django.db.backends.mysql",
            "django.db.backends.postgresql",
            "django.db.backends.sqlite3"
        ],
        description="数据库引擎"
    )
    
    registry["database.name"] = ConfigField(
        name="database.name",
        type=str,
        required=False,  # 开发环境使用 SQLite 时不需要
        env_var="DB_NAME",
        description="数据库名称"
    )
    
    registry["database.user"] = ConfigField(
        name="database.user",
        type=str,
        required=False,  # 开发环境使用 SQLite 时不需要
        env_var="DB_USER",
        description="数据库用户名"
    )
    
    registry["database.password"] = ConfigField(
        name="database.password",
        type=str,
        required=False,  # 开发环境使用 SQLite 时不需要
        sensitive=True,
        env_var="DB_PASSWORD",
        description="数据库密码"
    )
    
    registry["database.host"] = ConfigField(
        name="database.host",
        type=str,
        default="localhost",
        env_var="DB_HOST",
        description="数据库主机地址"
    )
    
    registry["database.port"] = ConfigField(
        name="database.port",
        type=int,
        default=3306,
        env_var="DB_PORT",
        min_value=1,
        max_value=65535,
        description="数据库端口"
    )
    
    # CORS 配置
    registry["cors.allowed_origins"] = ConfigField(
        name="cors.allowed_origins",
        type=list,
        default=[],
        description="CORS 允许的来源列表"
    )
    
    registry["cors.trusted_origins"] = ConfigField(
        name="cors.trusted_origins",
        type=list,
        default=[],
        description="CSRF 信任的来源列表"
    )
    
    # ==================== 第三方服务配置 ====================
    
    # Moonshot AI 配置
    registry["services.moonshot.base_url"] = ConfigField(
        name="services.moonshot.base_url",
        type=str,
        default="https://api.moonshot.cn/v1",
        env_var="MOONSHOT_BASE_URL",
        description="Moonshot AI API 基础 URL"
    )
    
    registry["services.moonshot.api_key"] = ConfigField(
        name="services.moonshot.api_key",
        type=str,
        required=False,  # 开发环境中可选
        sensitive=True,
        env_var="MOONSHOT_API_KEY",
        description="Moonshot AI API 密钥"
    )
    
    registry["services.moonshot.timeout"] = ConfigField(
        name="services.moonshot.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="Moonshot AI API 超时时间（秒）"
    )
    
    # Ollama 配置
    registry["services.ollama.model"] = ConfigField(
        name="services.ollama.model",
        type=str,
        default="qwen2.5:7b",
        env_var="OLLAMA_MODEL",
        description="Ollama 模型名称"
    )
    
    registry["services.ollama.base_url"] = ConfigField(
        name="services.ollama.base_url",
        type=str,
        default="http://localhost:11434",
        env_var="OLLAMA_BASE_URL",
        description="Ollama API 基础 URL"
    )
    
    registry["services.ollama.timeout"] = ConfigField(
        name="services.ollama.timeout",
        type=int,
        default=60,
        min_value=1,
        max_value=600,
        description="Ollama API 超时时间（秒）"
    )
    
    # 爬虫配置
    registry["services.scraper.encryption_key"] = ConfigField(
        name="services.scraper.encryption_key",
        type=str,
        required=False,  # 开发环境中可选
        sensitive=True,
        env_var="SCRAPER_ENCRYPTION_KEY",
        description="爬虫加密密钥"
    )
    
    # ==================== 群聊平台配置 ====================
    
    # 飞书配置
    registry["chat_platforms.feishu.app_id"] = ConfigField(
        name="chat_platforms.feishu.app_id",
        type=str,
        required=False,  # 开发环境中可选
        sensitive=True,
        env_var="FEISHU_APP_ID",
        description="飞书应用 ID"
    )
    
    registry["chat_platforms.feishu.app_secret"] = ConfigField(
        name="chat_platforms.feishu.app_secret",
        type=str,
        required=False,  # 开发环境中可选
        sensitive=True,
        env_var="FEISHU_APP_SECRET",
        description="飞书应用密钥"
    )
    
    registry["chat_platforms.feishu.webhook_url"] = ConfigField(
        name="chat_platforms.feishu.webhook_url",
        type=str,
        env_var="FEISHU_WEBHOOK_URL",
        description="飞书 Webhook URL"
    )
    
    registry["chat_platforms.feishu.timeout"] = ConfigField(
        name="chat_platforms.feishu.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="飞书 API 超时时间（秒）"
    )
    
    registry["chat_platforms.feishu.default_owner_id"] = ConfigField(
        name="chat_platforms.feishu.default_owner_id",
        type=str,
        env_var="FEISHU_DEFAULT_OWNER_ID",
        description="飞书默认群主 ID"
    )
    
    # 钉钉配置
    registry["chat_platforms.dingtalk.app_key"] = ConfigField(
        name="chat_platforms.dingtalk.app_key",
        type=str,
        env_var="DINGTALK_APP_KEY",
        description="钉钉应用 Key"
    )
    
    registry["chat_platforms.dingtalk.app_secret"] = ConfigField(
        name="chat_platforms.dingtalk.app_secret",
        type=str,
        sensitive=True,
        env_var="DINGTALK_APP_SECRET",
        description="钉钉应用密钥"
    )
    
    registry["chat_platforms.dingtalk.agent_id"] = ConfigField(
        name="chat_platforms.dingtalk.agent_id",
        type=str,
        env_var="DINGTALK_AGENT_ID",
        description="钉钉应用 Agent ID"
    )
    
    registry["chat_platforms.dingtalk.timeout"] = ConfigField(
        name="chat_platforms.dingtalk.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="钉钉 API 超时时间（秒）"
    )
    
    # 企业微信配置
    registry["chat_platforms.wechat_work.corp_id"] = ConfigField(
        name="chat_platforms.wechat_work.corp_id",
        type=str,
        env_var="WECHAT_WORK_CORP_ID",
        description="企业微信 Corp ID"
    )
    
    registry["chat_platforms.wechat_work.agent_id"] = ConfigField(
        name="chat_platforms.wechat_work.agent_id",
        type=str,
        env_var="WECHAT_WORK_AGENT_ID",
        description="企业微信应用 Agent ID"
    )
    
    registry["chat_platforms.wechat_work.secret"] = ConfigField(
        name="chat_platforms.wechat_work.secret",
        type=str,
        sensitive=True,
        env_var="WECHAT_WORK_SECRET",
        description="企业微信应用密钥"
    )
    
    registry["chat_platforms.wechat_work.timeout"] = ConfigField(
        name="chat_platforms.wechat_work.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="企业微信 API 超时时间（秒）"
    )
    
    # Telegram 配置
    registry["chat_platforms.telegram.bot_token"] = ConfigField(
        name="chat_platforms.telegram.bot_token",
        type=str,
        sensitive=True,
        env_var="TELEGRAM_BOT_TOKEN",
        description="Telegram Bot Token"
    )
    
    registry["chat_platforms.telegram.timeout"] = ConfigField(
        name="chat_platforms.telegram.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="Telegram API 超时时间（秒）"
    )
    
    # Slack 配置
    registry["chat_platforms.slack.bot_token"] = ConfigField(
        name="chat_platforms.slack.bot_token",
        type=str,
        sensitive=True,
        env_var="SLACK_BOT_TOKEN",
        description="Slack Bot Token"
    )
    
    registry["chat_platforms.slack.signing_secret"] = ConfigField(
        name="chat_platforms.slack.signing_secret",
        type=str,
        sensitive=True,
        env_var="SLACK_SIGNING_SECRET",
        description="Slack 签名密钥"
    )
    
    registry["chat_platforms.slack.timeout"] = ConfigField(
        name="chat_platforms.slack.timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="Slack API 超时时间（秒）"
    )
    
    # ==================== 业务功能配置 ====================
    
    # 案件聊天配置
    registry["features.case_chat.default_platform"] = ConfigField(
        name="features.case_chat.default_platform",
        type=str,
        default="feishu",
        choices=["feishu", "dingtalk", "wechat_work", "telegram", "slack"],
        description="默认聊天平台"
    )
    
    registry["features.case_chat.auto_create_on_push"] = ConfigField(
        name="features.case_chat.auto_create_on_push",
        type=bool,
        default=True,
        description="推送时自动创建聊天群"
    )
    
    registry["features.case_chat.default_owner_id"] = ConfigField(
        name="features.case_chat.default_owner_id",
        type=str,
        env_var="CASE_CHAT_DEFAULT_OWNER_ID",
        description="案件聊天默认群主 ID"
    )
    
    # 法院短信处理配置
    registry["features.court_sms.max_retries"] = ConfigField(
        name="features.court_sms.max_retries",
        type=int,
        default=3,
        min_value=0,
        max_value=10,
        description="法院短信最大重试次数"
    )
    
    registry["features.court_sms.retry_delay"] = ConfigField(
        name="features.court_sms.retry_delay",
        type=int,
        default=60,
        min_value=1,
        max_value=3600,
        description="法院短信重试延迟（秒）"
    )
    
    registry["features.court_sms.auto_recovery"] = ConfigField(
        name="features.court_sms.auto_recovery",
        type=bool,
        default=True,
        description="是否启用自动恢复"
    )
    
    # 文档处理配置
    registry["features.document_processing.default_text_limit"] = ConfigField(
        name="features.document_processing.default_text_limit",
        type=int,
        default=5000,
        min_value=100,
        max_value=100000,
        description="默认文本提取限制（字符数）"
    )
    
    registry["features.document_processing.max_text_limit"] = ConfigField(
        name="features.document_processing.max_text_limit",
        type=int,
        default=50000,
        min_value=1000,
        max_value=1000000,
        description="最大文本提取限制（字符数）"
    )
    
    registry["features.document_processing.default_preview_page"] = ConfigField(
        name="features.document_processing.default_preview_page",
        type=int,
        default=1,
        min_value=1,
        description="默认预览页数"
    )
    
    registry["features.document_processing.max_preview_pages"] = ConfigField(
        name="features.document_processing.max_preview_pages",
        type=int,
        default=10,
        min_value=1,
        max_value=100,
        description="最大预览页数"
    )
    
    # ==================== 性能配置 ====================
    
    # 限流配置
    registry["performance.rate_limit.default_requests"] = ConfigField(
        name="performance.rate_limit.default_requests",
        type=int,
        default=100,
        env_var="RATE_LIMIT_DEFAULT_REQUESTS",
        min_value=1,
        max_value=10000,
        description="默认请求限制（每窗口期）"
    )
    
    registry["performance.rate_limit.default_window"] = ConfigField(
        name="performance.rate_limit.default_window",
        type=int,
        default=60,
        env_var="RATE_LIMIT_DEFAULT_WINDOW",
        min_value=1,
        max_value=3600,
        description="默认限流窗口期（秒）"
    )
    
    registry["performance.rate_limit.auth_requests"] = ConfigField(
        name="performance.rate_limit.auth_requests",
        type=int,
        default=1000,
        env_var="RATE_LIMIT_AUTH_REQUESTS",
        min_value=1,
        max_value=100000,
        description="认证用户请求限制（每窗口期）"
    )
    
    registry["performance.rate_limit.auth_window"] = ConfigField(
        name="performance.rate_limit.auth_window",
        type=int,
        default=60,
        env_var="RATE_LIMIT_AUTH_WINDOW",
        min_value=1,
        max_value=3600,
        description="认证用户限流窗口期（秒）"
    )
    
    # 缓存配置
    registry["performance.cache.redis_url"] = ConfigField(
        name="performance.cache.redis_url",
        type=str,
        default="redis://localhost:6379/0",
        env_var="REDIS_URL",
        description="Redis 连接 URL"
    )
    
    registry["performance.cache.redis_host"] = ConfigField(
        name="performance.cache.redis_host",
        type=str,
        default="127.0.0.1",
        env_var="REDIS_HOST",
        description="Redis 主机地址"
    )
    
    registry["performance.cache.redis_port"] = ConfigField(
        name="performance.cache.redis_port",
        type=int,
        default=6379,
        env_var="REDIS_PORT",
        min_value=1,
        max_value=65535,
        description="Redis 端口"
    )
    
    registry["performance.cache.redis_db"] = ConfigField(
        name="performance.cache.redis_db",
        type=int,
        default=0,
        env_var="REDIS_DB",
        min_value=0,
        max_value=15,
        description="Redis 数据库编号"
    )
    
    registry["performance.cache.redis_password"] = ConfigField(
        name="performance.cache.redis_password",
        type=str,
        default="",
        sensitive=True,
        env_var="REDIS_PASSWORD",
        description="Redis 密码"
    )
    
    registry["performance.cache.default_timeout"] = ConfigField(
        name="performance.cache.default_timeout",
        type=int,
        default=300,
        min_value=1,
        max_value=86400,
        description="默认缓存超时时间（秒）"
    )
    
    registry["performance.cache.max_connections"] = ConfigField(
        name="performance.cache.max_connections",
        type=int,
        default=50,
        min_value=1,
        max_value=1000,
        description="Redis 最大连接数"
    )
    
    registry["performance.cache.socket_timeout"] = ConfigField(
        name="performance.cache.socket_timeout",
        type=int,
        default=5,
        min_value=1,
        max_value=60,
        description="Redis Socket 超时时间（秒）"
    )
    
    registry["performance.cache.key_prefix"] = ConfigField(
        name="performance.cache.key_prefix",
        type=str,
        default="lawfirm",
        description="缓存键前缀"
    )
    
    registry["performance.cache.timeout_short"] = ConfigField(
        name="performance.cache.timeout_short",
        type=int,
        default=60,
        min_value=1,
        max_value=3600,
        description="短期缓存超时时间（秒）"
    )
    
    registry["performance.cache.timeout_medium"] = ConfigField(
        name="performance.cache.timeout_medium",
        type=int,
        default=300,
        min_value=1,
        max_value=3600,
        description="中期缓存超时时间（秒）"
    )
    
    registry["performance.cache.timeout_long"] = ConfigField(
        name="performance.cache.timeout_long",
        type=int,
        default=3600,
        min_value=1,
        max_value=86400,
        description="长期缓存超时时间（秒）"
    )
    
    registry["performance.cache.timeout_day"] = ConfigField(
        name="performance.cache.timeout_day",
        type=int,
        default=86400,
        min_value=1,
        max_value=604800,
        description="日缓存超时时间（秒）"
    )
    
    # Q_CLUSTER 配置
    registry["performance.q_cluster.workers"] = ConfigField(
        name="performance.q_cluster.workers",
        type=int,
        default=4,
        min_value=1,
        max_value=32,
        description="Q_CLUSTER 工作进程数"
    )
    
    registry["performance.q_cluster.timeout"] = ConfigField(
        name="performance.q_cluster.timeout",
        type=int,
        default=60,
        min_value=1,
        max_value=3600,
        description="Q_CLUSTER 任务超时时间（秒）"
    )
    
    registry["performance.q_cluster.retry"] = ConfigField(
        name="performance.q_cluster.retry",
        type=int,
        default=60,
        min_value=1,
        max_value=3600,
        description="Q_CLUSTER 重试间隔（秒）"
    )
    
    registry["performance.q_cluster.queue_limit"] = ConfigField(
        name="performance.q_cluster.queue_limit",
        type=int,
        default=50,
        min_value=1,
        max_value=1000,
        description="Q_CLUSTER 队列限制"
    )
    
    registry["performance.q_cluster.bulk"] = ConfigField(
        name="performance.q_cluster.bulk",
        type=int,
        default=10,
        min_value=1,
        max_value=100,
        description="Q_CLUSTER 批量处理数量"
    )
    
    registry["performance.q_cluster.max_attempts"] = ConfigField(
        name="performance.q_cluster.max_attempts",
        type=int,
        default=1,
        min_value=1,
        max_value=10,
        description="Q_CLUSTER 最大尝试次数"
    )
    
    # ==================== 硬编码配置项（需要提取） ====================
    
    # 保险询价服务配置
    registry["services.insurance.list_url"] = ConfigField(
        name="services.insurance.list_url",
        type=str,
        default="https://baoquan.court.gov.cn/wsbq/ssbq/api/commoncodepz",
        description="保险公司列表 API URL"
    )
    
    registry["services.insurance.premium_query_url"] = ConfigField(
        name="services.insurance.premium_query_url",
        type=str,
        default="https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium",
        description="保险费率查询 API URL"
    )
    
    registry["services.insurance.default_timeout"] = ConfigField(
        name="services.insurance.default_timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="保险服务默认超时时间（秒）"
    )
    
    registry["services.insurance.max_connections"] = ConfigField(
        name="services.insurance.max_connections",
        type=int,
        default=10,
        min_value=1,
        max_value=100,
        description="保险服务最大连接数"
    )
    
    # 日志配置
    registry["logging.file_max_size"] = ConfigField(
        name="logging.file_max_size",
        type=int,
        default=10485760,  # 10MB
        min_value=1048576,  # 1MB
        max_value=104857600,  # 100MB
        description="日志文件最大大小（字节）"
    )
    
    registry["logging.api_backup_count"] = ConfigField(
        name="logging.api_backup_count",
        type=int,
        default=5,
        min_value=1,
        max_value=50,
        description="API 日志文件备份数量"
    )
    
    registry["logging.error_backup_count"] = ConfigField(
        name="logging.error_backup_count",
        type=int,
        default=10,
        min_value=1,
        max_value=50,
        description="错误日志文件备份数量"
    )
    
    registry["logging.sql_backup_count"] = ConfigField(
        name="logging.sql_backup_count",
        type=int,
        default=3,
        min_value=1,
        max_value=20,
        description="SQL 日志文件备份数量"
    )
    
    registry["logging.console_level"] = ConfigField(
        name="logging.console_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        description="控制台日志级别"
    )
    
    registry["logging.file_level"] = ConfigField(
        name="logging.file_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        description="文件日志级别"
    )
    
    registry["logging.error_level"] = ConfigField(
        name="logging.error_level",
        type=str,
        default="ERROR",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        description="错误日志级别"
    )
    
    registry["logging.django_level"] = ConfigField(
        name="logging.django_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        description="Django 日志级别"
    )
    
    registry["logging.request_level"] = ConfigField(
        name="logging.request_level",
        type=str,
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        description="Django 请求日志级别"
    )
    
    registry["logging.apps_level"] = ConfigField(
        name="logging.apps_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        description="应用日志级别"
    )
    
    registry["logging.root_level"] = ConfigField(
        name="logging.root_level",
        type=str,
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        description="根日志级别"
    )
    
    # 分页配置
    registry["pagination.default_page_size"] = ConfigField(
        name="pagination.default_page_size",
        type=int,
        default=20,
        min_value=1,
        max_value=1000,
        description="默认分页大小"
    )
    
    registry["pagination.max_page_size"] = ConfigField(
        name="pagination.max_page_size",
        type=int,
        default=100,
        min_value=1,
        max_value=10000,
        description="最大分页大小"
    )
    
    # 验证规则配置
    registry["validation.max_amount"] = ConfigField(
        name="validation.max_amount",
        type=float,
        default=10000000.0,  # 1000万
        min_value=0.01,
        description="最大金额限制"
    )
    
    registry["validation.max_string_length"] = ConfigField(
        name="validation.max_string_length",
        type=int,
        default=1000,
        min_value=1,
        max_value=100000,
        description="字符串最大长度限制"
    )
    
    registry["validation.max_file_size"] = ConfigField(
        name="validation.max_file_size",
        type=int,
        default=52428800,  # 50MB
        min_value=1024,  # 1KB
        max_value=1073741824,  # 1GB
        description="文件上传最大大小（字节）"
    )
    
    # 数据库字段长度配置
    registry["validation.name_max_length"] = ConfigField(
        name="validation.name_max_length",
        type=int,
        default=255,
        min_value=1,
        max_value=1000,
        description="姓名/名称字段最大长度"
    )
    
    registry["validation.phone_max_length"] = ConfigField(
        name="validation.phone_max_length",
        type=int,
        default=20,
        min_value=1,
        max_value=50,
        description="电话号码字段最大长度"
    )
    
    registry["validation.address_max_length"] = ConfigField(
        name="validation.address_max_length",
        type=int,
        default=255,
        min_value=1,
        max_value=1000,
        description="地址字段最大长度"
    )
    
    registry["validation.id_number_max_length"] = ConfigField(
        name="validation.id_number_max_length",
        type=int,
        default=64,
        min_value=1,
        max_value=100,
        description="身份证号/统一社会信用代码最大长度"
    )
    
    # 金额字段配置
    registry["validation.decimal_max_digits"] = ConfigField(
        name="validation.decimal_max_digits",
        type=int,
        default=15,
        min_value=1,
        max_value=30,
        description="金额字段最大位数"
    )
    
    registry["validation.decimal_places"] = ConfigField(
        name="validation.decimal_places",
        type=int,
        default=2,
        min_value=0,
        max_value=10,
        description="金额字段小数位数"
    )
    
    # 文本内容限制
    registry["validation.text_extraction_limit"] = ConfigField(
        name="validation.text_extraction_limit",
        type=int,
        default=5000,
        min_value=100,
        max_value=100000,
        description="文本提取默认限制（字符数）"
    )
    
    registry["validation.max_text_extraction_limit"] = ConfigField(
        name="validation.max_text_extraction_limit",
        type=int,
        default=50000,
        min_value=1000,
        max_value=1000000,
        description="文本提取最大限制（字符数）"
    )
    
    registry["validation.screenshot_limit"] = ConfigField(
        name="validation.screenshot_limit",
        type=int,
        default=5,
        min_value=1,
        max_value=20,
        description="调试截图收集数量限制"
    )
    
    # ==================== Steering 配置 ====================
    
    # 条件加载配置
    registry["steering.conditional_loading.enabled"] = ConfigField(
        name="steering.conditional_loading.enabled",
        type=bool,
        default=True,
        description="是否启用条件加载"
    )
    
    registry["steering.conditional_loading.cache_ttl"] = ConfigField(
        name="steering.conditional_loading.cache_ttl",
        type=int,
        default=3600,
        min_value=60,
        max_value=86400,
        description="条件加载缓存 TTL（秒）"
    )
    
    # 性能监控配置
    registry["steering.performance.load_threshold_ms"] = ConfigField(
        name="steering.performance.load_threshold_ms",
        type=int,
        default=100,
        min_value=1,
        max_value=10000,
        description="加载性能阈值（毫秒）"
    )
    
    registry["steering.performance.warn_threshold_ms"] = ConfigField(
        name="steering.performance.warn_threshold_ms",
        type=int,
        default=500,
        min_value=1,
        max_value=10000,
        description="性能警告阈值（毫秒）"
    )
    
    return registry


# 全局配置注册表实例
CONFIG_REGISTRY = create_config_registry()


def get_config_field(key: str) -> ConfigField:
    """
    获取配置字段定义
    
    Args:
        key: 配置键（支持点号路径）
        
    Returns:
        ConfigField: 配置字段定义
        
    Raises:
        KeyError: 配置字段不存在
    """
    if key not in CONFIG_REGISTRY:
        raise KeyError(f"配置字段 '{key}' 不存在")
    
    return CONFIG_REGISTRY[key]


def get_all_config_fields() -> Dict[str, ConfigField]:
    """
    获取所有配置字段定义
    
    Returns:
        Dict[str, ConfigField]: 所有配置字段定义
    """
    return CONFIG_REGISTRY.copy()


def get_config_fields_by_category(category: str) -> Dict[str, ConfigField]:
    """
    按类别获取配置字段定义
    
    Args:
        category: 配置类别（如 'django', 'services', 'chat_platforms' 等）
        
    Returns:
        Dict[str, ConfigField]: 指定类别的配置字段定义
    """
    return {
        key: field for key, field in CONFIG_REGISTRY.items()
        if key.startswith(f"{category}.")
    }


def get_sensitive_config_fields() -> Dict[str, ConfigField]:
    """
    获取所有敏感配置字段定义
    
    Returns:
        Dict[str, ConfigField]: 敏感配置字段定义
    """
    return {
        key: field for key, field in CONFIG_REGISTRY.items()
        if field.sensitive
    }


def get_required_config_fields() -> Dict[str, ConfigField]:
    """
    获取所有必需配置字段定义
    
    Returns:
        Dict[str, ConfigField]: 必需配置字段定义
    """
    return {
        key: field for key, field in CONFIG_REGISTRY.items()
        if field.required
    }


def validate_registry_consistency():
    """
    验证配置注册表的一致性
    
    检查是否有重复的环境变量名、依赖关系是否正确等
    
    Raises:
        ValueError: 配置注册表不一致
    """
    env_vars = {}
    errors = []
    
    for key, field in CONFIG_REGISTRY.items():
        # 检查环境变量名是否重复
        if field.env_var:
            if field.env_var in env_vars:
                errors.append(
                    f"环境变量 '{field.env_var}' 被多个配置项使用: "
                    f"'{env_vars[field.env_var]}' 和 '{key}'"
                )
            else:
                env_vars[field.env_var] = key
        
        # 检查依赖关系是否存在
        if field.depends_on:
            for dep in field.depends_on:
                if dep not in CONFIG_REGISTRY:
                    errors.append(
                        f"配置项 '{key}' 依赖的配置项 '{dep}' 不存在"
                    )
    
    if errors:
        raise ValueError("配置注册表不一致:\n" + "\n".join(errors))


# 在模块加载时验证注册表一致性
validate_registry_consistency()