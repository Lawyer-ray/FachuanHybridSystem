"""证据管理枚举定义"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class EvidenceDirection(models.TextChoices):
    """证据方向"""

    OUR = "our", _("我方证据")
    OPPONENT = "opponent", _("对方证据")
    COURT = "court", _("法院调取")


class EvidenceType(models.TextChoices):
    """证据种类（民事诉讼法第六十六条）"""

    DOCUMENTARY = "documentary", _("书证")
    PHYSICAL = "physical", _("物证")
    AUDIOVISUAL = "audiovisual", _("视听资料")
    ELECTRONIC = "electronic", _("电子数据")
    WITNESS = "witness", _("证人证言")
    APPRAISAL = "appraisal", _("鉴定意见")
    INSPECTION = "inspection", _("勘验笔录")
    STATEMENT = "statement", _("当事人陈述")


class OriginalStatus(models.TextChoices):
    """原件状态"""

    HAS_ORIGINAL = "has_original", _("有原件")
    COPY_ONLY = "copy_only", _("仅复印件")
    ELECTRONIC = "electronic", _("电子原件")
