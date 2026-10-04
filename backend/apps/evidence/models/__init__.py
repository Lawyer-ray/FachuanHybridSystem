"""证据管理模型

历史归属说明：EvidenceList / EvidenceItem 原属 documents 应用，后拆分为独立的
evidence 应用；为保持既有数据库表名（documents_evidencelist /
documents_evidenceitem）与外键引用不变，模型 Meta 仍显式声明
app_label="documents" + db_table="documents_*"。此为刻意的兼容性设计，勿"修复"。
"""

from .enums import EvidenceDirection, EvidenceType, OriginalStatus
from .evidence import LIST_TYPE_ORDER, LIST_TYPE_PREVIOUS, EvidenceItem, EvidenceList, ListType, MergeStatus
from .group import EvidenceGroup
from .proxy import EvidenceItemProxy, EvidenceListProxy

__all__ = [
    "EvidenceList",
    "EvidenceItem",
    "EvidenceListProxy",
    "EvidenceItemProxy",
    "MergeStatus",
    "ListType",
    "LIST_TYPE_PREVIOUS",
    "LIST_TYPE_ORDER",
    "EvidenceDirection",
    "EvidenceType",
    "OriginalStatus",
    "EvidenceGroup",
]
