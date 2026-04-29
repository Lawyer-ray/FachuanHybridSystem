"""
证据文件存储配置

migration 引用了 apps.documents.models.evidence_storage.EvidenceFileStorage，
因此保留此类定义。实际实现继承自 apps.evidence.models.evidence_storage。
"""

import os

from django.conf import settings

from apps.evidence.models.evidence_storage import (
    EvidenceFileStorage as _BaseEvidenceFileStorage,
)


class EvidenceFileStorage(_BaseEvidenceFileStorage):
    """继承 evidence 模块的存储实现，保持 migration 兼容。"""


def get_evidence_storage() -> EvidenceFileStorage:
    """获取证据文件存储实例"""
    return EvidenceFileStorage(location=os.path.join(settings.MEDIA_ROOT, "evidence"), base_url="/media/evidence/")


evidence_file_storage = get_evidence_storage()
