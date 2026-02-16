"""Module for lawyer."""

from django.contrib.auth.models import AbstractUser
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from .law_firm import LawFirm
from .storage import KeepOriginalNameStorage
from .team import Team, TeamType


def lawyer_license_upload_path(instance, filename) -> None:
    """
    生成律师执业证文件上传路径
    """
    return f"lawyers/licenses/{filename}"


class Lawyer(AbstractUser):
    """
    律师模型
    扩展自 Django AbstractUser,代表系统用户
    """

    real_name = models.CharField(max_length=255, blank=True, verbose_name=_("真实姓名"))
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name=_("手机号码"))
    license_no = models.CharField(max_length=64, blank=True, verbose_name=_("执业证号"))
    id_card = models.CharField(max_length=32, blank=True, verbose_name=_("身份证号"))
    law_firm = models.ForeignKey(
        LawFirm,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lawyers",
        verbose_name=_("所属律所"),
    )
    is_admin = models.BooleanField(default=False, verbose_name=_("是否律所管理员"))
    license_pdf = models.FileField(
        upload_to=lawyer_license_upload_path,
        storage=KeepOriginalNameStorage(),
        null=True,
        blank=True,
        validators=[FileExtensionValidator(["pdf"])],
        verbose_name=_("执业证文件"),
    )

    # 团队关系
    lawyer_teams = models.ManyToManyField(
        Team,
        blank=True,
        related_name="lawyers",
        limit_choices_to={"team_type": TeamType.LAWYER},
        verbose_name=_("所属律师团队"),
    )

    biz_teams = models.ManyToManyField(
        Team,
        blank=True,
        related_name="biz_members",
        limit_choices_to={"team_type": TeamType.BIZ},
        verbose_name=_("所属业务团队"),
    )

    class Meta:
        verbose_name = _("律师")
        verbose_name_plural = _("律师")

    def __str__(self) -> str:
        return self.username or self.real_name
