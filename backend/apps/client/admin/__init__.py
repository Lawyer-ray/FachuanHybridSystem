"""
Client App Admin模块主文件
统一管理所有客户的Admin界面
"""

from .client_admin import ClientAdmin, ClientAdminForm, ClientIdentityDocInline, ClientIdentityDocInlineForm
from .clientidentitydoc_admin import ClientIdentityDocAdmin
from .property_clue_admin import PropertyClueAdmin, PropertyClueAttachmentInline

# 所有Admin类通过装饰器自动注册
# 无需手动注册，admin/__init__.py中的类会自动处理

__all__ = [
    'ClientAdmin',
    'ClientAdminForm',
    'ClientIdentityDocInline',
    'ClientIdentityDocInlineForm',
    'ClientIdentityDocAdmin',
    'PropertyClueAdmin',
    'PropertyClueAttachmentInline'
]
