"""
Organization 模块模型层

重新导出所有模型类、枚举类、函数,保持向后兼容性.
所有旧的导入路径 `from apps.organization.models import X` 继续有效.
"""

# credential.py - 账号凭证模型
from .credential import AccountCredential

# law_firm.py - 律所模型
from .law_firm import LawFirm

# lawyer.py - 律师模型和上传路径函数
from .lawyer import Lawyer, lawyer_license_upload_path

# storage.py - 自定义存储类
from .storage import KeepOriginalNameStorage

# team.py - 团队相关模型和枚举
from .team import Team, TeamType

__all__ = [
    # storage.py
    "KeepOriginalNameStorage",
    # law_firm.py
    "LawFirm",
    # team.py
    "Team",
    "TeamType",
    # lawyer.py
    "Lawyer",
    "lawyer_license_upload_path",
    # credential.py
    "AccountCredential",
]
