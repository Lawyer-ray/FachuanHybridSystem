"""证据文件存储配置，复用 apps.evidence.services 的实现。"""

from apps.evidence.services.evidence_storage import EvidenceFileStorage, evidence_file_storage

__all__ = ["EvidenceFileStorage", "evidence_file_storage"]
