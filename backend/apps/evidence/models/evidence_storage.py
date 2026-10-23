"""
证据文件存储配置

此模块解决 models 和 services 之间的循环导入问题。
"""

import re

from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class EvidenceFileStorage(FileSystemStorage):
    def deconstruct(self) -> tuple[str, list[object], dict[str, object]]:
        """不序列化 location/base_url，避免本机路径写入 migration。"""
        return (f"{self.__class__.__module__}.{self.__class__.__qualname__}", [], {})

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

    def generate_filename(self, name: str) -> str:  # type: ignore[override]
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
    """获取证据文件存储实例。

    注意：不要给 location/base_url 再加 ``evidence`` 前缀。
    两个使用本 storage 的字段都通过 ``DatedUUIDPath`` 生成路径，其
    ``MediaEntity`` 已自带 ``evidence/`` 前缀（``evidence/files``、
    ``evidence/merged``）；若 location 再加一层 ``evidence``，最终 URL 会变成
    ``/media/evidence/evidence/merged/...``（历史上就是如此，已修正）。
    """
    return EvidenceFileStorage()


evidence_file_storage = get_evidence_storage()
