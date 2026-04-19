"""
系统配置模型

用于存储系统级别的配置项,支持在 Django Admin 中进行管理.
"""

# mypy: ignore-errors

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class SystemConfig(models.Model):
    """系统配置模型

    用于存储系统级别的配置项,支持在 Django Admin 中进行管理.
    配置项按分类组织,支持加密存储敏感信息.
    """

    id: int

    class Category(models.TextChoices):
        """配置分类"""

        FEISHU = "feishu", _("飞书配置")
        DINGTALK = "dingtalk", _("钉钉配置")
        WECHAT_WORK = "wechat_work", _("企业微信配置")
        TELEGRAM = "telegram", _("Telegram 配置")
        COURT_SMS = "court_sms", _("法院短信配置")
        AI = "ai", _("AI 服务配置")
        LLM = "llm", _("LLM 大模型配置")
        ENTERPRISE_DATA = "enterprise_data", _("企业数据配置")
        SCRAPER = "scraper", _("爬虫配置")
        OCR = "ocr", _("OCR 服务配置")
        GENERAL = "general", _("通用配置")

    key = models.CharField(
        max_length=100, unique=True, verbose_name=_("配置键"), help_text=_("配置项的唯一标识符,如 FEISHU_APP_ID")
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
        default=False,
        verbose_name=_("敏感信息"),
        help_text=_("是否为敏感信息(如密钥、密码等)"),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("启用"), help_text=_("是否启用此配置项"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("系统配置")
        verbose_name_plural = _("系统配置")
        ordering: ClassVar = ["category", "key"]
        indexes: ClassVar = [
            models.Index(fields=["category"], name="core_system_categor_aa7ba2_idx"),
            models.Index(fields=["key"], name="core_system_key_07f5b4_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_category_display()} - {self.key}"
