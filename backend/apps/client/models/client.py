"""Module for client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from .identity_doc import ClientIdentityDoc
    from .property_clue import PropertyClue


class ClientType(models.TextChoices):
    NATURAL = "natural", "自然人"
    LEGAL = "legal", "法人"
    NON_LEGAL_ORG = "non_legal_org", "非法人组织"


class Client(models.Model):
    id: int
    # 枚举化前的历史常量别名（数据库值不变），消费方仍可 Client.NATURAL 引用
    NATURAL = ClientType.NATURAL
    LEGAL = ClientType.LEGAL
    NON_LEGAL_ORG = ClientType.NON_LEGAL_ORG
    CLIENT_TYPE_CHOICES: ClassVar[list[tuple[str, Any]]] = ClientType.choices

    name = models.CharField(max_length=255, verbose_name="名称")
    phone = models.CharField(max_length=20, blank=True, default="", verbose_name="联系电话")
    address = models.CharField(max_length=255, blank=True, default="", verbose_name="住所地")
    client_type = models.CharField(
        max_length=16, choices=ClientType.choices, default=ClientType.LEGAL, verbose_name="主体类型"
    )
    id_number = models.CharField(
        max_length=64, blank=True, null=True, unique=True, verbose_name="身份证号码或统一社会信用代码"
    )
    legal_representative = models.CharField(max_length=255, blank=True, default="", verbose_name="法定代表人或负责人")
    legal_representative_id_number = models.CharField(
        max_length=64, blank=True, default="", verbose_name="法定代表人/负责人身份证号码"
    )
    is_our_client = models.BooleanField(default=False, verbose_name="是否为我方当事人")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    history = HistoricalRecords()

    if TYPE_CHECKING:
        identity_docs: RelatedManager[ClientIdentityDoc]
        property_clues: RelatedManager[PropertyClue]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        # id_number 是 unique 字段：空值必须存 NULL 而不是 ''（PG 多 NULL 共存，
        # '' 会与存量空串互撞唯一约束）。同 Lawyer.phone/email 的既有范式。
        if self.id_number == "":
            self.id_number = None
        super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.client_type == self.LEGAL and not self.legal_representative:
            raise ValidationError({"legal_representative": "Required for legal organizations"})

    class Meta:
        verbose_name = "当事人"
        verbose_name_plural = "当事人"
        db_table = "cases_client"
        managed = True
        indexes: ClassVar = [
            models.Index(fields=["name"]),
            models.Index(fields=["client_type"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["is_our_client"]),
            # 全局搜索 name__icontains 走 trigram（随数据增长上保险）
            GinIndex(fields=["name"], name="client_client_name_trgm", opclasses=["gin_trgm_ops"]),
        ]
