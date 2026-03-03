"""Module for property clue."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.client.utils.media import resolve_media_url

from .client import Client

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager


class PropertyClue(models.Model):
    """财产线索模型"""

    id: int
    BANK = "bank"
    ALIPAY = "alipay"
    WECHAT = "wechat"
    REAL_ESTATE = "real_estate"
    OTHER = "other"

    CLUE_TYPE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (BANK, _("银行账户")),
        (ALIPAY, _("支付宝账户")),
        (WECHAT, _("微信账户")),
        (REAL_ESTATE, _("不动产")),
        (OTHER, _("其他")),
    ]

    CONTENT_TEMPLATES: ClassVar[dict[str, str]] = {
        BANK: _("户名:\n开户行:\n银行账号:"),
        WECHAT: _("微信号:\n微信实名:"),
        ALIPAY: _("支付宝账号:\n支付宝实名:"),
        REAL_ESTATE: "",
        OTHER: "",
    }

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="property_clues", verbose_name=_("当事人")
    )
    clue_type = models.CharField(max_length=16, choices=CLUE_TYPE_CHOICES, default=BANK, verbose_name=_("线索类型"))
    content = models.TextField(blank=True, default="", verbose_name=_("线索内容"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    if TYPE_CHECKING:
        attachments: RelatedManager[PropertyClueAttachment]

    def __str__(self) -> str:
        return f"{self.client.name}-{self.get_clue_type_display()}"

    class Meta:
        verbose_name = _("财产线索")
        verbose_name_plural = _("财产线索")
        db_table = "cases_propertyclue"
        managed = True


class PropertyClueAttachment(models.Model):
    """财产线索附件模型"""

    id: int
    property_clue_id: int
    property_clue = models.ForeignKey(
        PropertyClue, on_delete=models.CASCADE, related_name="attachments", verbose_name=_("财产线索")
    )
    file_path = models.CharField(max_length=512, verbose_name=_("文件路径"))
    file_name = models.CharField(max_length=255, verbose_name=_("文件名"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("上传时间"))

    def __str__(self) -> str:
        return f"{self.property_clue}-{self.file_name}"

    @property
    def media_url(self) -> str | None:
        """返回附件的媒体 URL"""
        return resolve_media_url(self.file_path)

    class Meta:
        verbose_name = _("财产线索附件")
        verbose_name_plural = _("财产线索附件")
        db_table = "cases_propertyclueattachment"
        managed = True
