"""Module for identity doc."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.client.utils.media import resolve_media_url

from .client import Client


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
    DOC_TYPE_CHOICES: ClassVar[list[tuple[str, Any]]] = [
        (ID_CARD, _("身份证")),
        (PASSPORT, _("护照")),
        (HK_MACAO_PERMIT, _("港澳通行证")),
        (RESIDENCE_PERMIT, _("居住证")),
        (HOUSEHOLD_REGISTER, _("户口本")),
        (BUSINESS_LICENSE, _("营业执照")),
        (LEGAL_REP_ID_CARD, _("法定代表人/负责人身份证")),
    ]

    _NATURAL_DOC_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            ID_CARD,
            PASSPORT,
            HK_MACAO_PERMIT,
            RESIDENCE_PERMIT,
            HOUSEHOLD_REGISTER,
        }
    )
    _LEGAL_DOC_TYPES: ClassVar[frozenset[str]] = frozenset({BUSINESS_LICENSE, LEGAL_REP_ID_CARD})

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="identity_docs", verbose_name=_("当事人"))
    doc_type = models.CharField(max_length=32, choices=DOC_TYPE_CHOICES, verbose_name=_("证件类型"))
    file_path = models.CharField(max_length=512, verbose_name=_("文件路径"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("到期日期"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("上传时间"))

    def __str__(self) -> str:
        # Admin inline 的首列会直接渲染 __str__，这里保持空字符串避免泄露冗余文案。
        return ""

    @property
    def media_url(self) -> str | None:
        return resolve_media_url(self.file_path)

    def clean(self) -> None:
        if self.client:
            if self.client.client_type == Client.NATURAL and self.doc_type not in self._NATURAL_DOC_TYPES:
                raise ValidationError({"doc_type": _("Invalid doc type for natural person")})
            if (
                self.client.client_type in {Client.LEGAL, Client.NON_LEGAL_ORG}
                and self.doc_type not in self._NATURAL_DOC_TYPES | self._LEGAL_DOC_TYPES
            ):
                raise ValidationError({"doc_type": _("Invalid doc type for organization")})

    class Meta:
        verbose_name = _("证件")
        verbose_name_plural = _("证件")
        db_table = "cases_clientidentitydoc"
        managed = True
