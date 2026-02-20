"""
Core 模块数据模型

本模块定义系统级别的数据模型，包括：
- SystemConfig: 系统配置项存储
"""

from typing import ClassVar

from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _


class SystemConfig(models.Model):
    """系统配置模型"""

    class Category(models.TextChoices):
        """配置分类"""

        FEISHU = "feishu", _("飞书配置")
        DINGTALK = "dingtalk", _("钉钉配置")
        WECHAT_WORK = "wechat_work", _("企业微信配置")
        COURT_SMS = "court_sms", _("法院短信配置")
        AI = "ai", _("AI 服务配置")
        SCRAPER = "scraper", _("爬虫配置")
        GENERAL = "general", _("通用配置")

    key = models.CharField(
        max_length=100, unique=True, verbose_name=_("配置键"), help_text=_("配置项的唯一标识符，如 FEISHU_APP_ID")
    )
    value = models.TextField(blank=True, default="", verbose_name=_("配置值"), help_text=_("配置项的值"))
    category = models.CharField(
        max_length=50,
        choices=Category.choices,
        default=Category.GENERAL,
        verbose_name=_("分类"),
        help_text=_("配置项所属分类"),
    )
    description = models.CharField(
        max_length=255, blank=True, default="", verbose_name=_("描述"), help_text=_("配置项的说明")
    )
    is_secret = models.BooleanField(
        default=False, verbose_name=_("敏感信息"), help_text=_("是否为敏感信息（如密钥、密码等）")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("启用"), help_text=_("是否启用此配置项"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("系统配置")
        verbose_name_plural = _("系统配置")
        ordering: ClassVar[list[str]] = ["category", "key"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["category"]),
            models.Index(fields=["key"]),
        ]

    def __str__(self):
        return f"{self.get_category_display()} - {self.key}"

    def save(self, *args, **kwargs):
        """保存时清除缓存"""
        super().save(*args, **kwargs)
        # 清除配置缓存
        cache.delete(f"system_config:{self.key}")
        cache.delete("system_config:all")

    @classmethod
    def get_value(cls, key: str, default: str = "") -> str:
        """获取配置值

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值，如果不存在或未启用则返回默认值
        """
        cache_key = f"system_config:{key}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            config = cls.objects.get(key=key, is_active=True)
            cache.set(cache_key, config.value, timeout=300)  # 缓存 5 分钟
            return config.value
        except cls.DoesNotExist:
            return default

    @classmethod
    def get_category_configs(cls, category: str) -> dict:
        """获取某分类下的所有配置

        Args:
            category: 分类标识

        Returns:
            配置字典 {key: value}
        """
        configs = cls.objects.filter(category=category, is_active=True)
        return {c.key: c.value for c in configs}

    @classmethod
    def set_value(
        cls, key: str, value: str, category: str = "general", description: str = "", is_secret: bool = False
    ) -> "SystemConfig":
        """设置配置值

        Args:
            key: 配置键
            value: 配置值
            category: 分类
            description: 描述
            is_secret: 是否敏感信息

        Returns:
            SystemConfig 实例
        """
        config, created = cls.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "category": category,
                "description": description,
                "is_secret": is_secret,
            },
        )
        return config
