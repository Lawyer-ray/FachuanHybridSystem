"""Module for identity doc."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

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


class IdentityDocType(models.TextChoices):
    ID_CARD = "id_card", "身份证"
    PASSPORT = "passport", "护照"
    HK_MACAO_PERMIT = "hk_macao_permit", "港澳通行证"
    RESIDENCE_PERMIT = "residence_permit", "居住证"
    HOUSEHOLD_REGISTER = "household_register", "户口本"
    BUSINESS_LICENSE = "business_license", "营业执照"
    LEGAL_REP_ID_CARD = "legal_rep_id_card", "法定代表人/负责人身份证"


class ClientIdentityDoc(models.Model):
    id: int
    client_id: int
    # 枚举化前的历史常量别名（数据库值不变），消费方仍可 ClientIdentityDoc.ID_CARD 引用
    ID_CARD = IdentityDocType.ID_CARD
    PASSPORT = IdentityDocType.PASSPORT
    HK_MACAO_PERMIT = IdentityDocType.HK_MACAO_PERMIT
    RESIDENCE_PERMIT = IdentityDocType.RESIDENCE_PERMIT
    HOUSEHOLD_REGISTER = IdentityDocType.HOUSEHOLD_REGISTER
    BUSINESS_LICENSE = IdentityDocType.BUSINESS_LICENSE
    LEGAL_REP_ID_CARD = IdentityDocType.LEGAL_REP_ID_CARD
    DOC_TYPE_CHOICES: ClassVar[list[tuple[str, Any]]] = IdentityDocType.choices

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

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="identity_docs", verbose_name="当事人")
    doc_type = models.CharField(max_length=32, choices=IdentityDocType.choices, verbose_name="证件类型")
    file_path = models.CharField(max_length=512, blank=True, null=True, verbose_name="文件路径")
    expiry_date = models.DateField(null=True, blank=True, verbose_name="到期日期")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="上传时间")

    def __str__(self) -> str:
        # Admin inline 的首列会直接渲染 __str__，这里保持空字符串避免泄露冗余文案。
        return ""

    def save(self, *args: Any, **kwargs: Any) -> None:
        # file_path 进 (client, file_path) 唯一约束：待上传占位必须存 NULL 而不是 ''。
        # admin inline 一次保存多个新证件行时各行先以空值 INSERT、文件随后回填，
        # 存 '' 会第二行就互撞唯一约束（2026-10-09 实爆）；PG 多 NULL 共存。
        # 同 Client.id_number 的既有范式。
        if self.file_path == "":
            self.file_path = None
        super().save(*args, **kwargs)

    @cached_property
    def media_url(self) -> str | None:
        return resolve_media_url(self.file_path)

    def clean(self) -> None:
        if self.client:
            if self.client.client_type == Client.NATURAL and self.doc_type not in self._NATURAL_DOC_TYPES:
                raise ValidationError({"doc_type": "Invalid doc type for natural person"})
            if (
                self.client.client_type in {Client.LEGAL, Client.NON_LEGAL_ORG}
                and self.doc_type not in self._LEGAL_DOC_TYPES
            ):
                raise ValidationError({"doc_type": "Invalid doc type for organization"})

    class Meta:
        verbose_name = "证件"
        verbose_name_plural = "证件"
        db_table = "cases_clientidentitydoc"
        managed = True
        indexes: ClassVar = [
            models.Index(fields=["client", "doc_type"], name="idx_iddoc_clt_doctype"),
        ]
        constraints: ClassVar = [
            # 导入路径 get_or_create(client, file_path) 的查重键；NULL = 待上传占位行，
            # PG 下互不冲突，回填真实路径后即受约束保护
            models.UniqueConstraint(fields=["client", "file_path"], name="uniq_clientidentitydoc_client_file_path"),
            # 上传服务 get_or_create(client, doc_type)：一人一证件类型
            models.UniqueConstraint(fields=["client", "doc_type"], name="uniq_clientidentitydoc_client_doctype"),
        ]
