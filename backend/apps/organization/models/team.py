"""Module for team."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from .law_firm import LawFirm


class TeamType(models.TextChoices):
    """
    团队类型枚举
    """

    LAWYER = "lawyer", _("律师团队")
    BIZ = "biz", _("业务团队")


class Team(models.Model):
    """
    团队模型
    律所下的分组单元,分为律师团队和业务团队
    """

    id: int
    law_firm_id: int  # 外键ID字段
    name = models.CharField(max_length=255, verbose_name=_("团队名称"))
    team_type = models.CharField(max_length=16, choices=TeamType.choices, verbose_name=_("团队类型"))
    law_firm = models.ForeignKey(LawFirm, on_delete=models.CASCADE, related_name="teams", verbose_name=_("所属律所"))

    class Meta:
        verbose_name = _("团队")
        verbose_name_plural = _("团队")

    def __str__(self) -> str:
        return f"{self.law_firm.name}-{self.get_team_type_display()}-{self.name}"
