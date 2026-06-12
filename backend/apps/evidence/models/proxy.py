"""Proxy models for admin registration under /admin/evidence/"""

from apps.evidence.models.evidence import EvidenceItem, EvidenceList


class EvidenceListProxy(EvidenceList):
    """代理模型：让证据清单 Admin 出现在 /admin/evidence/ 下"""

    class Meta:
        proxy = True
        app_label = "evidence"
        verbose_name = "证据清单"
        verbose_name_plural = "证据清单"
        ordering = ["case", "order"]


class EvidenceItemProxy(EvidenceItem):
    """代理模型：让证据条目 Admin 出现在 /admin/evidence/ 下"""

    class Meta:
        proxy = True
        app_label = "evidence"
        verbose_name = "证据明细"
        verbose_name_plural = "证据明细"
        ordering = ["evidence_list", "order"]
