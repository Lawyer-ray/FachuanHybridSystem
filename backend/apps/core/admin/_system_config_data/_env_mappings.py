"""环境变量到配置的映射数据"""

from typing import Any

__all__ = ["get_env_mappings"]


def get_env_mappings() -> dict[str, dict[str, Any]]:
    """获取环境变量到配置的映射"""
    return {
        "DJANGO_SECRET_KEY": {
            "key": "DJANGO_SECRET_KEY",
            "category": "general",
            "description": "Django 密钥",
            "is_secret": True,
        },
        "DJANGO_DEBUG": {
            "key": "DJANGO_DEBUG",
            "category": "general",
            "description": "Django 调试模式",
            "is_secret": False,
        },
        "DJANGO_ALLOWED_HOSTS": {
            "key": "DJANGO_ALLOWED_HOSTS",
            "category": "general",
            "description": "允许的主机列表",
            "is_secret": False,
        },
        "FEISHU_APP_ID": {
            "key": "FEISHU_APP_ID",
            "category": "feishu",
            "description": "飞书应用 App ID",
            "is_secret": False,
        },
        "CASE_CHAT_NAME_TEMPLATE": {
            "key": "CASE_CHAT_NAME_TEMPLATE",
            "category": "feishu",
            "description": "群聊名称模板",
            "is_secret": False,
        },
        "CASE_CHAT_DEFAULT_STAGE": {
            "key": "CASE_CHAT_DEFAULT_STAGE",
            "category": "feishu",
            "description": "默认阶段显示文本",
            "is_secret": False,
        },
        "CASE_CHAT_NAME_MAX_LENGTH": {
            "key": "CASE_CHAT_NAME_MAX_LENGTH",
            "category": "feishu",
            "description": "群聊名称最大长度",
            "is_secret": False,
        },
        "FEISHU_APP_SECRET": {
            "key": "FEISHU_APP_SECRET",
            "category": "feishu",
            "description": "飞书应用 App Secret",
            "is_secret": True,
        },
        "FEISHU_DEFAULT_OWNER_ID": {
            "key": "FEISHU_DEFAULT_OWNER_ID",
            "category": "feishu",
            "description": "飞书群聊默认群主 ID",
            "is_secret": False,
        },
        "FEISHU_WEBHOOK_URL": {
            "key": "FEISHU_WEBHOOK_URL",
            "category": "feishu",
            "description": "飞书 Webhook URL",
            "is_secret": False,
        },
        "FEISHU_TIMEOUT": {
            "key": "FEISHU_TIMEOUT",
            "category": "feishu",
            "description": "飞书 API 超时时间",
            "is_secret": False,
        },
        "DINGTALK_APP_KEY": {
            "key": "DINGTALK_APP_KEY",
            "category": "dingtalk",
            "description": "钉钉应用 App Key",
            "is_secret": False,
        },
        "DINGTALK_APP_SECRET": {
            "key": "DINGTALK_APP_SECRET",
            "category": "dingtalk",
            "description": "钉钉应用 App Secret",
            "is_secret": True,
        },
        "DINGTALK_AGENT_ID": {
            "key": "DINGTALK_AGENT_ID",
            "category": "dingtalk",
            "description": "钉钉应用 Agent ID",
            "is_secret": False,
        },
        "DINGTALK_TIMEOUT": {
            "key": "DINGTALK_TIMEOUT",
            "category": "dingtalk",
            "description": "钉钉 API 超时时间",
            "is_secret": False,
        },
        "WECHAT_WORK_CORP_ID": {
            "key": "WECHAT_WORK_CORP_ID",
            "category": "wechat_work",
            "description": "企业微信 Corp ID",
            "is_secret": False,
        },
        "WECHAT_WORK_AGENT_ID": {
            "key": "WECHAT_WORK_AGENT_ID",
            "category": "wechat_work",
            "description": "企业微信 Agent ID",
            "is_secret": False,
        },
        "WECHAT_WORK_SECRET": {
            "key": "WECHAT_WORK_SECRET",
            "category": "wechat_work",
            "description": "企业微信应用 Secret",
            "is_secret": True,
        },
        "WECHAT_WORK_TIMEOUT": {
            "key": "WECHAT_WORK_TIMEOUT",
            "category": "wechat_work",
            "description": "企业微信 API 超时时间",
            "is_secret": False,
        },
        "TELEGRAM_BOT_TOKEN": {
            "key": "TELEGRAM_BOT_TOKEN",
            "category": "general",
            "description": "Telegram Bot Token",
            "is_secret": True,
        },
        "SLACK_BOT_TOKEN": {
            "key": "SLACK_BOT_TOKEN",
            "category": "general",
            "description": "Slack Bot Token",
            "is_secret": True,
        },
        "SLACK_SIGNING_SECRET": {
            "key": "SLACK_SIGNING_SECRET",
            "category": "general",
            "description": "Slack Signing Secret",
            "is_secret": True,
        },
        "COURT_SMS_MAX_RETRIES": {
            "key": "COURT_SMS_MAX_RETRIES",
            "category": "court_sms",
            "description": "法院短信最大重试次数",
            "is_secret": False,
        },
        "COURT_SMS_RETRY_DELAY": {
            "key": "COURT_SMS_RETRY_DELAY",
            "category": "court_sms",
            "description": "法院短信重试延迟",
            "is_secret": False,
        },
        "COURT_SMS_AUTO_RECOVERY": {
            "key": "COURT_SMS_AUTO_RECOVERY",
            "category": "court_sms",
            "description": "法院短信自动恢复",
            "is_secret": False,
        },
        "OLLAMA_MODEL": {
            "key": "OLLAMA_MODEL",
            "category": "ai",
            "description": "Ollama 模型名称",
            "is_secret": False,
        },
        "OLLAMA_BASE_URL": {
            "key": "OLLAMA_BASE_URL",
            "category": "ai",
            "description": "Ollama API 地址",
            "is_secret": False,
        },
        "MOONSHOT_API_KEY": {
            "key": "MOONSHOT_API_KEY",
            "category": "ai",
            "description": "Moonshot AI API Key",
            "is_secret": True,
        },
        "MOONSHOT_BASE_URL": {
            "key": "MOONSHOT_BASE_URL",
            "category": "ai",
            "description": "Moonshot AI API 地址",
            "is_secret": False,
        },
        "SCRAPER_ENCRYPTION_KEY": {
            "key": "SCRAPER_ENCRYPTION_KEY",
            "category": "scraper",
            "description": "爬虫加密密钥",
            "is_secret": True,
        },
        "SCRAPER_HEADLESS": {
            "key": "SCRAPER_HEADLESS",
            "category": "scraper",
            "description": "爬虫无头模式",
            "is_secret": False,
        },
        "CORS_ALLOWED_ORIGINS": {
            "key": "CORS_ALLOWED_ORIGINS",
            "category": "general",
            "description": "CORS 允许的来源",
            "is_secret": False,
        },
        "CSRF_TRUSTED_ORIGINS": {
            "key": "CSRF_TRUSTED_ORIGINS",
            "category": "general",
            "description": "CSRF 信任的来源",
            "is_secret": False,
        },
    }
