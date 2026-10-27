"""Module for law firm."""

from django.db import models


class LawFirm(models.Model):
    """律所模型，代表一个律师事务所实体。"""

    id: int
    # 唯一约束：LawFirm 的去重完全依赖 `get_or_create(name=...)`（律师导入 4 处）。
    # 无数据库约束时并发导入会造出同名重复律所，而 Team 的唯一键是
    # (law_firm, team_type, name)——律所一旦重复，同一团队会被拆成两条，
    # 取团队成员时会漏人。约束 + get_or_create 的 IntegrityError 重查兜底才完整。
    name = models.CharField(max_length=255, unique=True, verbose_name="律所名称")
    address = models.CharField(max_length=255, blank=True, verbose_name="地址")
    phone = models.CharField(max_length=20, blank=True, verbose_name="联系电话")
    social_credit_code = models.CharField(max_length=18, blank=True, verbose_name="统一社会信用代码")
    bank_name = models.CharField(max_length=255, blank=True, verbose_name="开户行")
    bank_account = models.CharField(max_length=64, blank=True, verbose_name="银行账号")

    class Meta:
        verbose_name = "律所"
        verbose_name_plural = "律所"

    def __str__(self) -> str:
        return self.name
