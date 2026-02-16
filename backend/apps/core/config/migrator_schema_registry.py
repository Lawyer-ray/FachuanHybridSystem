"""
配置迁移 Schema 注册器

负责注册配置 schema 字段
"""

from __future__ import annotations

import logging

from .schema.field import ConfigField
from .schema.schema import ConfigSchema

logger = logging.getLogger(__name__)


class SchemaRegistry:
    """Schema 注册器"""

    @staticmethod
    def register_django_core_fields(schema: ConfigSchema) -> None:
        """
        注册 Django 核心字段

        Args:
            schema: 配置 schema
        """
        # Django 核心配置
        schema.register(
            ConfigField(
                name="django.secret_key", type=str, required=True, sensitive=True, description="Django SECRET_KEY"
            )
        )

        schema.register(
            ConfigField(name="django.debug", type=bool, required=True, default=False, description="Django DEBUG 模式")
        )

        schema.register(
            ConfigField(
                name="django.allowed_hosts", type=list, required=True, default=[], description="Django ALLOWED_HOSTS"
            )
        )

        # 国际化配置
        schema.register(ConfigField(name="django.language_code", type=str, default="zh-hans", description="语言代码"))

        schema.register(ConfigField(name="django.time_zone", type=str, default="Asia/Shanghai", description="时区"))

        schema.register(ConfigField(name="django.use_i18n", type=bool, default=True, description="启用国际化"))

        schema.register(ConfigField(name="django.use_tz", type=bool, default=True, description="启用时区支持"))

        # 静态文件配置
        schema.register(ConfigField(name="django.static_url", type=str, default="/static/", description="静态文件 URL"))

        schema.register(ConfigField(name="django.media_url", type=str, default="/media/", description="媒体文件 URL"))

        schema.register(ConfigField(name="django.media_root", type=str, description="媒体文件根目录"))

    @staticmethod
    def register_service_fields(schema: ConfigSchema) -> None:
        """
        注册服务字段

        Args:
            schema: 配置 schema
        """
        # CORS 配置
        schema.register(
            ConfigField(name="cors.allow_all_origins", type=bool, default=False, description="允许所有来源")
        )

        schema.register(ConfigField(name="cors.allowed_origins", type=list, default=[], description="允许的来源列表"))

        schema.register(
            ConfigField(name="cors.allow_credentials", type=bool, default=False, description="允许携带凭证")
        )

        schema.register(
            ConfigField(name="cors.csrf_trusted_origins", type=list, default=[], description="CSRF 信任的来源")
        )

        # 第三方服务配置
        schema.register(ConfigField(name="services.moonshot.base_url", type=str, description="Moonshot API 基础 URL"))

        schema.register(
            ConfigField(name="services.moonshot.api_key", type=str, sensitive=True, description="Moonshot API 密钥")
        )

        schema.register(ConfigField(name="services.ollama", type=dict, default={}, description="Ollama 服务配置"))

    @staticmethod
    def register_business_fields(schema: ConfigSchema) -> None:
        """
        注册业务字段

        Args:
            schema: 配置 schema
        """
        # 群聊平台配置
        schema.register(ConfigField(name="chat_platforms.feishu", type=dict, default={}, description="飞书配置"))

        schema.register(ConfigField(name="chat_platforms.dingtalk", type=dict, default={}, description="钉钉配置"))

        schema.register(
            ConfigField(name="chat_platforms.wechat_work", type=dict, default={}, description="企业微信配置")
        )

        schema.register(ConfigField(name="chat_platforms.telegram", type=dict, default={}, description="Telegram 配置"))

        schema.register(ConfigField(name="chat_platforms.slack", type=dict, default={}, description="Slack 配置"))

        # 业务功能配置
        schema.register(ConfigField(name="features.case_chat", type=dict, default={}, description="案件群聊功能配置"))

        schema.register(ConfigField(name="features.court_sms", type=dict, default={}, description="法院短信处理配置"))

        schema.register(
            ConfigField(name="features.document_processing", type=dict, default={}, description="文档处理配置")
        )

        # 性能配置
        schema.register(ConfigField(name="performance.q_cluster", type=dict, default={}, description="Q Cluster 配置"))

        schema.register(ConfigField(name="performance.rate_limit", type=dict, default={}, description="速率限制配置"))

        schema.register(ConfigField(name="performance.cache", type=dict, default={}, description="缓存配置"))

        # 安全配置
        schema.register(
            ConfigField(name="security.scraper_encryption_key", type=str, sensitive=True, description="爬虫加密密钥")
        )

        schema.register(
            ConfigField(name="security.perm_open_access", type=bool, default=False, description="开放权限访问")
        )
