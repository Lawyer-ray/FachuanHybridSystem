"""
证据文件存储配置

此模块解决 models 和 services 之间的循环导入问题。
"""

import os
import re

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class EvidenceFileStorage(FileSystemStorage):
    """
    证据文件存储类

    保留中文文件名中的特殊字符(如括号),
    只移除真正危险的字符.
    """

    def get_valid_name(self, name: str) -> str:
        from pathlib import Path

        original_name = name
        name = super().get_valid_name(name)
        if not name:
            return original_name

        path = Path(name)
        stem = path.stem
        ext = path.suffix

        stem = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", stem)
        if not stem:
            stem = "file"

        return stem + ext

    def generate_filename(self, name: str) -> str:
        from pathlib import Path

        original_name = name
        name = super().generate_filename(name)
        if not name:
            return original_name

        path = Path(name)
        stem = path.stem
        ext = path.suffix

        stem = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", stem)
        if not stem:
            stem = "file"

        return str(path.parent / (stem + ext))


def get_evidence_storage() -> EvidenceFileStorage:
    """获取证据文件存储实例"""
    return EvidenceFileStorage(location=os.path.join(settings.MEDIA_ROOT, "evidence"), base_url="/media/evidence/")


evidence_file_storage = get_evidence_storage()
