"""证据管理枚举定义"""

from django.db import models


class EvidenceDirection(models.TextChoices):
    """证据方向"""

    OUR = "our", "我方证据"
    OPPONENT = "opponent", "对方证据"
    COURT = "court", "法院调取"


class EvidenceType(models.TextChoices):
    """证据种类（民事诉讼法第六十六条）"""

    DOCUMENTARY = "documentary", "书证"
    PHYSICAL = "physical", "物证"
    AUDIOVISUAL = "audiovisual", "视听资料"
    ELECTRONIC = "electronic", "电子数据"
    WITNESS = "witness", "证人证言"
    APPRAISAL = "appraisal", "鉴定意见"
    INSPECTION = "inspection", "勘验笔录"
    STATEMENT = "statement", "当事人陈述"


class OriginalStatus(models.TextChoices):
    """原件状态"""

    HAS_ORIGINAL = "has_original", "有原件"
    COPY_ONLY = "copy_only", "仅复印件"
    ELECTRONIC = "electronic", "电子原件"
