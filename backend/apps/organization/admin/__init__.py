"""
Organization App Admin模块主文件
统一管理所有组织的Admin界面
"""
from .lawfirm_admin import LawFirmAdmin
from .lawyer_admin import LawyerAdmin, LawyerAdminForm, AccountCredentialInline, AccountCredentialInlineForm
from .team_admin import TeamAdmin
from .accountcredential_admin import AccountCredentialAdmin

# 所有Admin类通过装饰器自动注册
# 无需手动注册，admin/__init__.py中的类会自动处理

__all__ = [
    'LawFirmAdmin',
    'LawyerAdmin',
    'LawyerAdminForm',
    'AccountCredentialInline',
    'AccountCredentialInlineForm',
    'TeamAdmin',
    'AccountCredentialAdmin'
]
