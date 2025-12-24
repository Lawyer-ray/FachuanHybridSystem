from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _


class LawFirm(models.Model):
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    social_credit_code = models.CharField(max_length=64, blank=True)
    bank_name = models.CharField(max_length=255, blank=True, verbose_name="开户行")
    bank_account = models.CharField(max_length=64, blank=True, verbose_name="银行账号")

    def __str__(self) -> str:
        return self.name


class Lawyer(AbstractUser):
    real_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    license_no = models.CharField(max_length=64, blank=True)
    id_card = models.CharField(max_length=32, blank=True)
    law_firm = models.ForeignKey(LawFirm, on_delete=models.SET_NULL, null=True, blank=True, related_name="lawyers")
    is_admin = models.BooleanField(default=False)
    license_pdf = models.FileField(upload_to="lawyers/licenses/", null=True, blank=True, validators=[FileExtensionValidator(["pdf"])])

    def __str__(self) -> str:
        return self.username or self.real_name


class TeamType(models.TextChoices):
    LAWYER = "lawyer", _("律师团队")
    BIZ = "biz", _("业务团队")


class Team(models.Model):
    name = models.CharField(max_length=255)
    team_type = models.CharField(max_length=16, choices=TeamType.choices)
    law_firm = models.ForeignKey(LawFirm, on_delete=models.CASCADE, related_name="teams")

    def __str__(self) -> str:
        return f"{self.law_firm_id}-{self.team_type}-{self.name}"


Lawyer.add_to_class(
    "lawyer_teams",
    models.ManyToManyField(
        Team,
        blank=True,
        related_name="lawyers",
        limit_choices_to={"team_type": TeamType.LAWYER},
    ),
)


class AccountCredential(models.Model):
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE, related_name="credentials", verbose_name="律师")
    site_name = models.CharField(max_length=255, verbose_name="网站名称")
    url = models.URLField(blank=True, verbose_name="URL")
    account = models.CharField(max_length=255, verbose_name="账号")
    password = models.CharField(max_length=255, verbose_name="密码")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # 新增登录统计字段
    last_login_success_at = models.DateTimeField(null=True, blank=True, verbose_name="最后成功登录时间")
    login_success_count = models.PositiveIntegerField(default=0, verbose_name="成功登录次数")
    login_failure_count = models.PositiveIntegerField(default=0, verbose_name="失败登录次数")
    is_preferred = models.BooleanField(default=False, verbose_name="是否优先使用")

    class Meta:
        verbose_name = "账号密码"
        verbose_name_plural = "账号密码"
        ordering = ['-last_login_success_at', '-login_success_count', 'login_failure_count']
        indexes = [
            models.Index(fields=['site_name', '-last_login_success_at']),
            models.Index(fields=['site_name', 'is_preferred']),
        ]

    def __str__(self) -> str:
        return f"{self.site_name} - {self.account}"

    @property
    def success_rate(self) -> float:
        """计算登录成功率"""
        total_attempts = self.login_success_count + self.login_failure_count
        if total_attempts == 0:
            return 0.0
        return self.login_success_count / total_attempts

Lawyer.add_to_class(
    "biz_teams",
    models.ManyToManyField(
        Team,
        blank=True,
        related_name="biz_members",
        limit_choices_to={"team_type": TeamType.BIZ},
    ),
)
