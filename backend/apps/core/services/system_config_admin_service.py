"""
系统配置 Admin 服务

提供 SystemConfigAdmin 所需的业务逻辑,包括默认配置项和环境变量映射.
"""

from typing import Any


class SystemConfigAdminService:
    """系统配置 Admin 服务"""

    def get_default_configs(self) -> list[dict[str, Any]]:
        """
        获取默认配置项列表

        Returns:
            默认配置项列表,每项包含 key, category, description, value(可选), is_secret(可选)
        """
        return (
            self._get_django_configs()
            + self._get_feishu_configs()
            + self._get_feishu_chat_configs()
            + self._get_court_sms_configs()
            + self._get_ai_configs()
            + self._get_llm_configs()
            + self._get_scraper_configs()
            + self._get_general_configs()
        )

    # ============ 默认配置项分组方法 ============

    def _get_django_configs(self) -> list[dict[str, Any]]:
        """Django 配置"""
        return [
            {
                "key": "DJANGO_SECRET_KEY",
                "category": "general",
                "description": "Django 密钥(生产环境必须修改)",
                "is_secret": True,
            },
            {
                "key": "DJANGO_DEBUG",
                "category": "general",
                "description": "Django 调试模式",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "DJANGO_ALLOWED_HOSTS",
                "category": "general",
                "description": "允许的主机列表(逗号分隔)",
                "value": "localhost,127.0.0.1",
                "is_secret": False,
            },
            {
                "key": "ADMIN_EMAIL",
                "category": "general",
                "description": "管理员邮箱(用于系统通知)",
                "value": "",
                "is_secret": False,
            },
            {
                "key": "TIMEZONE",
                "category": "general",
                "description": "系统时区",
                "value": "Asia/Shanghai",
                "is_secret": False,
            },
        ]

    def _get_feishu_configs(self) -> list[dict[str, Any]]:
        """飞书基础配置"""
        return [
            {
                "key": "FEISHU_APP_ID",
                "category": "feishu",
                "description": "飞书应用 App ID",
                "value": "cli_xxxxxxxx",
                "is_secret": False,
            },
            {
                "key": "FEISHU_APP_SECRET",
                "category": "feishu",
                "description": "飞书应用 App Secret",
                "is_secret": True,
            },
            {
                "key": "FEISHU_DEFAULT_OWNER_ID",
                "category": "feishu",
                "description": "飞书群聊默认群主 ID(open_id 格式:ou_xxxxxx)",
                "value": "ou_xxxxxxxx",
                "is_secret": False,
            },
            {
                "key": "FEISHU_TIMEOUT",
                "category": "feishu",
                "description": "飞书 API 超时时间(秒)",
                "value": "30",
                "is_secret": False,
            },
        ]

    def _get_feishu_chat_configs(self) -> list[dict[str, Any]]:
        """飞书群聊配置"""
        return [
            {
                "key": "CASE_CHAT_NAME_TEMPLATE",
                "category": "feishu",
                "description": (
                    "案件群聊名称模板,支持占位符:{stage}(案件阶段)、{case_name}(案件名称)、{case_type}(案件类型)"
                ),
                "value": "[{stage}]{case_name}",
                "is_secret": False,
            },
            {
                "key": "CASE_CHAT_DEFAULT_STAGE",
                "category": "feishu",
                "description": "案件阶段为空时的默认显示文本",
                "value": "待定",
                "is_secret": False,
            },
            {
                "key": "CASE_CHAT_NAME_MAX_LENGTH",
                "category": "feishu",
                "description": "群聊名称最大长度(飞书限制为60)",
                "value": "60",
                "is_secret": False,
            },
        ]

    def _get_court_sms_configs(self) -> list[dict[str, Any]]:
        """法院短信和文书送达配置"""
        return [
            {
                "key": "COURT_SMS_ENABLED",
                "category": "court_sms",
                "description": "启用法院短信处理功能",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "COURT_SMS_MAX_RETRIES",
                "category": "court_sms",
                "description": "法院短信处理最大重试次数",
                "value": "3",
                "is_secret": False,
            },
            {
                "key": "COURT_SMS_RETRY_DELAY",
                "category": "court_sms",
                "description": "法院短信处理重试延迟(秒)",
                "value": "60",
                "is_secret": False,
            },
            {
                "key": "COURT_SMS_AUTO_RECOVERY",
                "category": "court_sms",
                "description": "法院短信自动恢复",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "COURT_SMS_NOTIFY_ON_SUCCESS",
                "category": "court_sms",
                "description": "短信处理成功时发送通知",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "COURT_SMS_NOTIFY_ON_FAILURE",
                "category": "court_sms",
                "description": "短信处理失败时发送通知",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "COURT_SMS_AUTO_MATCH_CASE",
                "category": "court_sms",
                "description": "自动匹配案件",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "COURT_SMS_DOWNLOAD_TIMEOUT",
                "category": "court_sms",
                "description": "文书下载超时时间(秒)",
                "value": "120",
                "is_secret": False,
            },
            {
                "key": "DOCUMENT_DELIVERY_ENABLED",
                "category": "court_sms",
                "description": "启用文书送达自动处理",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "DOCUMENT_DELIVERY_SCHEDULE",
                "category": "court_sms",
                "description": "文书送达检查时间(cron 格式)",
                "value": "0 9,14,18 * * *",
                "is_secret": False,
            },
            {
                "key": "DOCUMENT_DELIVERY_BATCH_SIZE",
                "category": "court_sms",
                "description": "文书送达批量处理数量",
                "value": "10",
                "is_secret": False,
            },
        ]

    def _get_ai_configs(self) -> list[dict[str, Any]]:
        """AI 配置"""
        return [
            {
                "key": "AI_ENABLED",
                "category": "ai",
                "description": "启用 AI 功能",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "AI_PROVIDER",
                "category": "ai",
                "description": "AI 服务提供商(ollama/openai)",
                "value": "ollama",
                "is_secret": False,
            },
            {
                "key": "OLLAMA_MODEL",
                "category": "ai",
                "description": "Ollama 模型名称",
                "value": "qwen3:0.6b",
                "is_secret": False,
            },
            {
                "key": "OLLAMA_BASE_URL",
                "category": "ai",
                "description": "Ollama API 地址",
                "value": "http://localhost:11434",
                "is_secret": False,
            },
            {
                "key": "OLLAMA_TIMEOUT",
                "category": "ai",
                "description": "Ollama API 超时时间(秒)",
                "value": "120",
                "is_secret": False,
            },
            {
                "key": "OPENAI_API_KEY",
                "category": "ai",
                "description": "OpenAI API Key",
                "is_secret": True,
            },
            {
                "key": "OPENAI_BASE_URL",
                "category": "ai",
                "description": "OpenAI API 地址(可用于代理)",
                "value": "https://api.openai.com/v1",
                "is_secret": False,
            },
            {
                "key": "OPENAI_MODEL",
                "category": "ai",
                "description": "OpenAI 模型名称",
                "value": "gpt-3.5-turbo",
                "is_secret": False,
            },
            {
                "key": "AI_AUTO_NAMING_ENABLED",
                "category": "ai",
                "description": "启用 AI 自动命名功能",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "AI_CASE_ANALYSIS_ENABLED",
                "category": "ai",
                "description": "启用 AI 案件分析功能",
                "value": "False",
                "is_secret": False,
            },
        ]

    def _get_llm_configs(self) -> list[dict[str, Any]]:
        """LLM 大模型配置"""
        return [
            {
                "key": "LLM_DEFAULT_BACKEND",
                "category": "llm",
                "description": "默认 LLM 后端(siliconflow/ollama/moonshot)",
                "value": "siliconflow",
                "is_secret": False,
            },
            {
                "key": "LLM_BACKEND_SILICONFLOW_ENABLED",
                "category": "llm",
                "description": "启用 siliconflow 后端",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "LLM_BACKEND_SILICONFLOW_PRIORITY",
                "category": "llm",
                "description": "siliconflow 后端优先级(数字越小越优先)",
                "value": "1",
                "is_secret": False,
            },
            {
                "key": "LLM_BACKEND_OLLAMA_ENABLED",
                "category": "llm",
                "description": "启用 ollama 后端",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "LLM_BACKEND_OLLAMA_PRIORITY",
                "category": "llm",
                "description": "ollama 后端优先级(数字越小越优先)",
                "value": "2",
                "is_secret": False,
            },
            {
                "key": "LLM_BACKEND_MOONSHOT_ENABLED",
                "category": "llm",
                "description": "启用 moonshot 后端",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "LLM_BACKEND_MOONSHOT_PRIORITY",
                "category": "llm",
                "description": "moonshot 后端优先级(数字越小越优先)",
                "value": "3",
                "is_secret": False,
            },
            {
                "key": "SILICONFLOW_API_KEY",
                "category": "llm",
                "description": "硅基流动 API Key",
                "is_secret": True,
            },
            {
                "key": "SILICONFLOW_BASE_URL",
                "category": "llm",
                "description": "硅基流动 API 地址",
                "value": "https://api.siliconflow.cn/v1",
                "is_secret": False,
            },
            {
                "key": "SILICONFLOW_DEFAULT_MODEL",
                "category": "llm",
                "description": "硅基流动默认模型",
                "value": "Pro/zai-org/GLM-4",
                "is_secret": False,
            },
            {
                "key": "SILICONFLOW_TIMEOUT",
                "category": "llm",
                "description": "硅基流动 API 超时时间(秒)",
                "value": "60",
                "is_secret": False,
            },
            {
                "key": "SILICONFLOW_ENABLE_TRACKING",
                "category": "llm",
                "description": "启用 LLM 调用追踪(用于成本分析)",
                "value": "false",
                "is_secret": False,
            },
            {
                "key": "MOONSHOT_API_KEY",
                "category": "llm",
                "description": "Moonshot API Key",
                "is_secret": True,
            },
            {
                "key": "MOONSHOT_BASE_URL",
                "category": "llm",
                "description": "Moonshot API 地址",
                "value": "https://api.moonshot.cn/v1",
                "is_secret": False,
            },
            {
                "key": "MOONSHOT_DEFAULT_MODEL",
                "category": "llm",
                "description": "Moonshot 默认模型",
                "value": "moonshot-v1-auto",
                "is_secret": False,
            },
            {
                "key": "MOONSHOT_TIMEOUT",
                "category": "llm",
                "description": "Moonshot API 超时时间(秒)",
                "value": "120",
                "is_secret": False,
            },
            {
                "key": "LLM_TEMPERATURE",
                "category": "llm",
                "description": "LLM 生成温度(0.0-1.0,越低越稳定)",
                "value": "0.3",
                "is_secret": False,
            },
            {
                "key": "LLM_MAX_TOKENS",
                "category": "llm",
                "description": "LLM 最大输出 Token 数",
                "value": "2000",
                "is_secret": False,
            },
        ]

    def _get_scraper_configs(self) -> list[dict[str, Any]]:
        """爬虫和 Token 配置"""
        return [
            {
                "key": "SCRAPER_ENABLED",
                "category": "scraper",
                "description": "启用爬虫功能",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "SCRAPER_ENCRYPTION_KEY",
                "category": "scraper",
                "description": "爬虫加密密钥",
                "is_secret": True,
            },
            {
                "key": "SCRAPER_HEADLESS",
                "category": "scraper",
                "description": "爬虫是否使用无头模式",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "SCRAPER_TIMEOUT",
                "category": "scraper",
                "description": "爬虫页面加载超时时间(秒)",
                "value": "60",
                "is_secret": False,
            },
            {
                "key": "SCRAPER_MAX_CONCURRENT",
                "category": "scraper",
                "description": "爬虫最大并发数",
                "value": "3",
                "is_secret": False,
            },
            {
                "key": "SCRAPER_RETRY_COUNT",
                "category": "scraper",
                "description": "爬虫失败重试次数",
                "value": "3",
                "is_secret": False,
            },
            {
                "key": "SCRAPER_DOWNLOAD_DIR",
                "category": "scraper",
                "description": "爬虫下载目录",
                "value": "/tmp/scraper_downloads",  # nosec B108
                "is_secret": False,
            },
            {
                "key": "TOKEN_AUTO_REFRESH_ENABLED",
                "category": "scraper",
                "description": "启用 Token 自动刷新",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "TOKEN_REFRESH_INTERVAL",
                "category": "scraper",
                "description": "Token 刷新间隔(分钟)",
                "value": "30",
                "is_secret": False,
            },
            {
                "key": "TOKEN_CACHE_TTL",
                "category": "scraper",
                "description": "Token 缓存有效期(秒)",
                "value": "3600",
                "is_secret": False,
            },
        ]

    def _get_general_configs(self) -> list[dict[str, Any]]:
        """通用配置(CORS、文件存储、日志、通知、缓存)"""
        return [
            {
                "key": "CORS_ALLOWED_ORIGINS",
                "category": "general",
                "description": "CORS 允许的来源(逗号分隔)",
                "value": "http://localhost:5173",
                "is_secret": False,
            },
            {
                "key": "CSRF_TRUSTED_ORIGINS",
                "category": "general",
                "description": "CSRF 信任的来源(逗号分隔)",
                "value": "http://localhost:5173",
                "is_secret": False,
            },
            {
                "key": "FILE_STORAGE_BACKEND",
                "category": "general",
                "description": "文件存储后端(local/s3/oss)",
                "value": "local",
                "is_secret": False,
            },
            {
                "key": "FILE_UPLOAD_MAX_SIZE",
                "category": "general",
                "description": "文件上传最大大小(MB)",
                "value": "50",
                "is_secret": False,
            },
            {
                "key": "FILE_ALLOWED_EXTENSIONS",
                "category": "general",
                "description": "允许上传的文件扩展名(逗号分隔)",
                "value": "pdf,doc,docx,xls,xlsx,jpg,jpeg,png,zip",
                "is_secret": False,
            },
            {
                "key": "LOG_LEVEL",
                "category": "general",
                "description": "日志级别(DEBUG/INFO/WARNING/ERROR)",
                "value": "INFO",
                "is_secret": False,
            },
            {
                "key": "LOG_RETENTION_DAYS",
                "category": "general",
                "description": "日志保留天数",
                "value": "30",
                "is_secret": False,
            },
            {
                "key": "NOTIFICATION_PROVIDER",
                "category": "general",
                "description": "默认通知渠道(feishu)",
                "value": "feishu",
                "is_secret": False,
            },
            {
                "key": "NOTIFICATION_ENABLED",
                "category": "general",
                "description": "启用系统通知",
                "value": "True",
                "is_secret": False,
            },
            {
                "key": "DATABASE_POOL_SIZE",
                "category": "general",
                "description": "数据库连接池大小",
                "value": "10",
                "is_secret": False,
            },
            {
                "key": "CACHE_TTL_DEFAULT",
                "category": "general",
                "description": "默认缓存过期时间(秒)",
                "value": "300",
                "is_secret": False,
            },
        ]
