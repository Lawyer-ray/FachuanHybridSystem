"""归档分类映射 - 合同类型 → 归档分类"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class ArchiveCategory(models.TextChoices):
    """归档分类"""

    NON_LITIGATION = "non_litigation", _("法律顾问及非诉事务")
    LITIGATION = "litigation", _("诉讼/仲裁")
    CRIMINAL = "criminal", _("刑事案件")


# 合同类型 → 归档分类映射
_CONTRACT_TYPE_TO_ARCHIVE_CATEGORY: dict[str, str] = {
    # 法律顾问及非诉事务
    "advisor": ArchiveCategory.NON_LITIGATION,
    "special": ArchiveCategory.NON_LITIGATION,
    # 诉讼/仲裁
    "civil": ArchiveCategory.LITIGATION,
    "intl": ArchiveCategory.LITIGATION,
    "labor": ArchiveCategory.LITIGATION,
    "administrative": ArchiveCategory.LITIGATION,
    # 刑事案件
    "criminal": ArchiveCategory.CRIMINAL,
}


def get_archive_category(case_type: str) -> str:
    """
    根据合同类型获取归档分类。

    Args:
        case_type: 合同类型代码 (CaseType value)

    Returns:
        归档分类代码 (ArchiveCategory value)，默认为 litigation
    """
    return _CONTRACT_TYPE_TO_ARCHIVE_CATEGORY.get(case_type, ArchiveCategory.LITIGATION)
