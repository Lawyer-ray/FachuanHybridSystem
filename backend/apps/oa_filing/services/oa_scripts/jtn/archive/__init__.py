"""JTN OA 归档材料提交自动化脚本。

结案归档：登录 → 搜索案件 → 填写案件小结 → 上传归档文件 → 保存。
"""

from .archive_models import ArchiveFormData
from .service import JtnArchiveScript

__all__ = ["ArchiveFormData", "JtnArchiveScript"]
