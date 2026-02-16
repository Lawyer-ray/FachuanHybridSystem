"""
Client 模块模型层

重新导出所有模型类、函数,保持向后兼容性.
所有旧的导入路径 `from apps.client.models import X` 继续有效.
"""

# client.py - 客户核心模型
from .client import Client

# identity_doc.py - 身份证件相关模型和函数
from .identity_doc import ClientIdentityDoc, client_identity_doc_upload_path

# property_clue.py - 财产线索相关模型
from .property_clue import PropertyClue, PropertyClueAttachment

__all__ = [
    # client.py
    "Client",
    # identity_doc.py
    "ClientIdentityDoc",
    "client_identity_doc_upload_path",
    # property_clue.py
    "PropertyClue",
    "PropertyClueAttachment",
]
