"""
Cases App Admin模块主文件
统一管理所有案件的Admin界面
"""

from __future__ import annotations

from .case_admin import CaseAdmin
from .case_chat_admin import CaseChatAdmin
from .caseassignment_admin import CaseAssignmentAdmin
from .caselog_admin import CaseLogAdmin, CaseLogAttachmentAdmin
from .caseparty_admin import CasePartyAdmin

# 所有Admin类通过装饰器自动注册
# 无需手动注册，admin/__init__.py中的类会自动处理

__all__ = [
    "CaseAdmin",
    "CasePartyAdmin",
    "CaseAssignmentAdmin",
    "CaseLogAdmin",
    "CaseLogAttachmentAdmin",
    "CaseChatAdmin",
]
