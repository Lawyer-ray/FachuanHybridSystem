"""
Documents Admin 模块

包含所有文书生成相关的 Django Admin 配置.
"""

from .audit_log_admin import TemplateAuditLogAdmin
from .document_template_admin import DocumentTemplateAdmin
from .evidence_admin import EvidenceListAdmin
from .folder_binding_admin import DocumentTemplateFolderBindingAdmin
from .folder_template_admin import FolderTemplateAdmin
from .placeholder_admin import PlaceholderAdmin
from .prompt_version_admin import PromptVersionAdmin
from .proxy_matter_rule_admin import ProxyMatterRuleAdmin

__all__ = [
    "FolderTemplateAdmin",
    "DocumentTemplateAdmin",
    "DocumentTemplateFolderBindingAdmin",
    "PlaceholderAdmin",
    "TemplateAuditLogAdmin",
    # 证据清单
    "EvidenceListAdmin",
    # Prompt 版本管理
    "PromptVersionAdmin",
    # 授权委托书
    "ProxyMatterRuleAdmin",
]
