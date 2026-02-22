"""
Cases 模块模型层

重新导出所有模型类、枚举类和函数,保持向后兼容性.
所有旧的导入路径 `from apps.cases.models import X` 继续有效.
"""

from __future__ import annotations

# 从 core.enums 重新导出的枚举(向后兼容)
from apps.core.enums import CaseStage, CaseStatus, CaseType, LegalStatus, SimpleCaseType

# case.py - 案件核心模型
from .case import Case, CaseFilingNumberSequence, CaseNumber, SupervisingAuthority

# chat.py - 群聊相关模型
from .chat import CaseChat, ChatAuditLog

# log.py - 日志相关模型
from .log import CaseLog, CaseLogAttachment, CaseLogVersion, validate_log_attachment

# material.py - 材料相关模型和枚举
from .material import (
    CaseFolderBinding,
    CaseMaterial,
    CaseMaterialCategory,
    CaseMaterialGroupOrder,
    CaseMaterialSide,
    CaseMaterialType,
)

# party.py - 当事人相关模型
from .party import CaseAccessGrant, CaseAssignment, CaseParty

# template_binding.py - 模板绑定相关模型和枚举
from .template_binding import BindingSource, CaseTemplateBinding

__all__ = [
    # 从 core.enums 重新导出(向后兼容)
    "CaseStage",
    "CaseStatus",
    "CaseType",
    "LegalStatus",
    "SimpleCaseType",
    # case.py
    "Case",
    "CaseFilingNumberSequence",
    "CaseNumber",
    "SupervisingAuthority",
    # party.py
    "CaseParty",
    "CaseAssignment",
    "CaseAccessGrant",
    # log.py
    "CaseLog",
    "CaseLogAttachment",
    "CaseLogVersion",
    "validate_log_attachment",
    # chat.py
    "CaseChat",
    "ChatAuditLog",
    # material.py
    "CaseMaterialCategory",
    "CaseMaterialSide",
    "CaseMaterialType",
    "CaseMaterial",
    "CaseMaterialGroupOrder",
    "CaseFolderBinding",
    # template_binding.py
    "BindingSource",
    "CaseTemplateBinding",
]
