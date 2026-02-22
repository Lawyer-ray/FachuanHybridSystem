"""Module for property clue."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .client import Client

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

logger = logging.getLogger(__name__)


class PropertyClue(models.Model):
    """财产线索模型"""

    id: int
    BANK = "bank"
    ALIPAY = "alipay"
    WECHAT = "wechat"
    REAL_ESTATE = "real_estate"
    OTHER = "other"

    CLUE_TYPE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (BANK, "银行账户"),
        (ALIPAY, "支付宝账户"),
        (WECHAT, "微信账户"),
        (REAL_ESTATE, "不动产"),
        (OTHER, "其他"),
    ]

    CONTENT_TEMPLATES: ClassVar[dict[str, str]] = {
        BANK: "户名:\n开户行:\n银行账号:",
        WECHAT: "微信号:\n微信实名:",
        ALIPAY: "支付宝账号:\n支付宝实名:",
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

    def media_url(self) -> str | None:
        """返回附件的媒体 URL"""
        if not self.file_path:
            return None
        try:
            root = Path(settings.MEDIA_ROOT)
            file_path = Path(self.file_path)
            if file_path.is_absolute() and str(file_path).startswith(str(root)):
                rel = file_path.relative_to(root)
                return settings.MEDIA_URL + str(rel).replace("\\", "/")
            elif not file_path.is_absolute():
                return settings.MEDIA_URL + str(file_path).replace("\\", "/")
        except Exception:
            logger.exception("操作失败")
            return None
        return None

    class Meta:
        verbose_name = _("财产线索附件")
        verbose_name_plural = _("财产线索附件")
        db_table = "cases_propertyclueattachment"
        managed = True
