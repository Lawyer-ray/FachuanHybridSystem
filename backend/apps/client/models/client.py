"""Module for client."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from .identity_doc import ClientIdentityDoc
    from .property_clue import PropertyClue


class Client(models.Model):
    id: int
    NATURAL = "natural"
    LEGAL = "legal"
    NON_LEGAL_ORG = "non_legal_org"
    CLIENT_TYPE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (NATURAL, _("自然人")),
        (LEGAL, _("法人")),
        (NON_LEGAL_ORG, _("非法人组织")),
    ]

    name = models.CharField(max_length=255, verbose_name=_("名称"))
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("联系电话"))
    address = models.CharField(max_length=255, blank=True, null=True, default="", verbose_name=_("住所地"))
    client_type = models.CharField(
        max_length=16, choices=CLIENT_TYPE_CHOICES, default=LEGAL, verbose_name=_("主体类型")
    )
    id_number = models.CharField(
        max_length=64, blank=True, null=True, unique=True, verbose_name=_("身份证号码或统一社会信用代码")
    )
    legal_representative = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("法定代表人或负责人"))
    legal_representative_id_number = models.CharField(
        max_length=64, blank=True, null=True, verbose_name=_("法定代表人/负责人身份证号码")
    )
    is_our_client = models.BooleanField(default=False, verbose_name=_("是否为我方当事人"))

    if TYPE_CHECKING:
        identity_docs: RelatedManager[ClientIdentityDoc]
        property_clues: RelatedManager[PropertyClue]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if self.client_type == self.LEGAL and not self.legal_representative:
            raise ValidationError({"legal_representative": _("Required for legal organizations")})

    class Meta:
        verbose_name = _("当事人")
        verbose_name_plural = _("当事人")
        db_table = "cases_client"
        managed = True
