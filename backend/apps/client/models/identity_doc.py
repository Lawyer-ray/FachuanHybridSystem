"""Module for identity doc."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .client import Client

logger = logging.getLogger(__name__)


def client_identity_doc_upload_path(instance: Any, filename: str) -> str:
    """生成当事人证件文件上传路径"""
    # 获取文件扩展名
    ext = Path(filename).suffix

    # 清理当事人名称
    client_name = instance.client.name if instance.client else "未知"
    client_name = slugify(client_name) or "unknown"

    # 获取证件类型显示名称
    doc_type_display = dict(ClientIdentityDoc.DOC_TYPE_CHOICES).get(instance.doc_type, instance.doc_type)
    doc_type_display = slugify(doc_type_display) or instance.doc_type

    # 生成文件名:当事人名称_证件类型.扩展名
    new_filename = f"{client_name}_{doc_type_display}{ext}"

    return f"client_identity_docs/{new_filename}"


class ClientIdentityDoc(models.Model):
    id: int
    client_id: int
    ID_CARD = "id_card"
    PASSPORT = "passport"
    HK_MACAO_PERMIT = "hk_macao_permit"
    RESIDENCE_PERMIT = "residence_permit"
    HOUSEHOLD_REGISTER = "household_register"
    BUSINESS_LICENSE = "business_license"
    LEGAL_REP_ID_CARD = "legal_rep_id_card"
    DOC_TYPE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (ID_CARD, "身份证"),
        (PASSPORT, "护照"),
        (HK_MACAO_PERMIT, "港澳通行证"),
        (RESIDENCE_PERMIT, "居住证"),
        (HOUSEHOLD_REGISTER, "户口本"),
        (BUSINESS_LICENSE, "营业执照"),
        (LEGAL_REP_ID_CARD, "法定代表人/负责人身份证"),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="identity_docs", verbose_name=_("当事人"))
    doc_type = models.CharField(max_length=32, choices=DOC_TYPE_CHOICES, verbose_name=_("证件类型"))
    file_path = models.CharField(max_length=512, verbose_name=_("文件路径"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("到期日期"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("上传时间"))

    def __str__(self) -> str:
        return f"{self.client.name}-{self.doc_type}"

    def media_url(self) -> str | None:
        if not self.file_path:
            return None
        try:
            root = Path(settings.MEDIA_ROOT)
            file_path = Path(self.file_path)
            # 如果是绝对路径,转换为相对路径
            if file_path.is_absolute() and str(file_path).startswith(str(root)):
                rel = file_path.relative_to(root)
                return settings.MEDIA_URL + str(rel).replace("\\", "/")
            # 如果已经是相对路径,直接拼接
            elif not file_path.is_absolute():
                return settings.MEDIA_URL + str(file_path).replace("\\", "/")
        except Exception:
            logger.exception("媒体URL解析失败", extra={"file_path": self.file_path})
            return None
        return None

    def clean(self) -> None:
        if self.client:
            natural_docs = {
                self.ID_CARD,
                self.PASSPORT,
                self.HK_MACAO_PERMIT,
                self.RESIDENCE_PERMIT,
                self.HOUSEHOLD_REGISTER,
            }
            legal_docs = {self.BUSINESS_LICENSE, self.LEGAL_REP_ID_CARD}
            if self.client.client_type == Client.NATURAL and self.doc_type not in natural_docs:
                raise ValidationError({"doc_type": "Invalid doc type for natural person"})
            if (
                self.client.client_type in {Client.LEGAL, Client.NON_LEGAL_ORG}
                and self.doc_type not in natural_docs | legal_docs
            ):
                raise ValidationError({"doc_type": "Invalid doc type for organization"})

    class Meta:
        verbose_name = _("当事人证件文件")
        verbose_name_plural = _("当事人证件文件")
        db_table = "cases_clientidentitydoc"
        managed = True
