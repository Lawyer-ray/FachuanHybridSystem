"""Module for law firm."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class LawFirm(models.Model):
    """
    律所模型
    代表一个律师事务所实体
    """

    id: int
    name = models.CharField(max_length=255, verbose_name=_("律所名称"))
    address = models.CharField(max_length=255, blank=True, verbose_name=_("地址"))
    phone = models.CharField(max_length=20, blank=True, verbose_name=_("联系电话"))
    social_credit_code = models.CharField(max_length=18, blank=True, verbose_name=_("统一社会信用代码"))
    bank_name = models.CharField(max_length=255, blank=True, verbose_name=_("开户行"))
    bank_account = models.CharField(max_length=64, blank=True, verbose_name=_("银行账号"))

    class Meta:
        verbose_name = _("律所")
        verbose_name_plural = _("律所")

    def __str__(self) -> str:
        return self.name
