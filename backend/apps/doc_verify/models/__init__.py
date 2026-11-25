"""doc_verify 模型注册表。

本文件是唯一让 Django 看见这些模型的地方：新增模型必须在这里 import 一次，
否则不会建表（且**不会报错**，只会在运行期报「表不存在」）。
"""

from .artifact import CaptureSource, OutboundArtifact
from .policy import VerificationPolicy
from .verification import VerificationDecision, VerificationRun, VerifyState

__all__ = [
    "CaptureSource",
    "OutboundArtifact",
    "VerificationDecision",
    "VerificationPolicy",
    "VerificationRun",
    "VerifyState",
]
