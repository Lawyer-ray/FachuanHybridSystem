"""JTN OA 盖章申请自动化脚本。

所函盖章申请：登录 → 搜索案件 → 填表 → 上传文件 → 保存。
"""

from .service import JtnStampScript
from .stamp_models import StampFormData

__all__ = ["JtnStampScript", "StampFormData"]
