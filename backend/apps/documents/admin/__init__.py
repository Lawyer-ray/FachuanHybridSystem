"""
Documents Admin 模块

包含所有文书生成相关的 Django Admin 配置.
"""

from .document_template_admin import DocumentTemplateAdmin
from .external_template_admin import ExternalTemplateAdmin
from .folder_binding_admin import DocumentTemplateFolderBindingAdmin
from .folder_template_admin import FolderTemplateAdmin
from .proxy_matter_rule_admin import ProxyMatterRuleAdmin

__all__ = [
    "FolderTemplateAdmin",
    "DocumentTemplateAdmin",
    "DocumentTemplateFolderBindingAdmin",
    # Prompt 版本管理
    # 授权委托书
    "ProxyMatterRuleAdmin",
    # 外部模板
    "ExternalTemplateAdmin",
]
