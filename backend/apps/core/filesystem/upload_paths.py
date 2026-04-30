"""统一的 upload_to 路径工厂函数。

所有新 FileField/ImageField 应使用本模块提供的工厂函数生成 upload_to，
确保文件路径按 `{app_entity}/YYYY/MM/` 规范组织。

用法示例::

    from apps.core.filesystem.upload_paths import dated_uuid_path

    class MyModel(models.Model):
        file = FileField(upload_to=dated_uuid_path("my_entity"))
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


def _sanitize(filename: str) -> str:
    """清理文件名，去除危险字符，保留中文。"""
    import re

    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^0-9A-Za-z一-鿿._-]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "file"


def dated_uuid_path(entity: str) -> Any:
    """返回 `{entity}/YYYY/MM/{uuid_hex}{ext}` 路径生成函数。

    适用于需要匿名存储、防冲突的场景。
    """

    def _upload_to(instance: Any, filename: str) -> str:
        now = datetime.now()
        ext = ""
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        return f"{entity}/{now:%Y/%m}/{uuid.uuid4().hex}{ext}"

    return _upload_to


def dated_original_path(entity: str) -> Any:
    """返回 `{entity}/YYYY/MM/{sanitized_name}` 路径生成函数。

    适用于需要保留原始文件名可读性的场景。
    """

    def _upload_to(instance: Any, filename: str) -> str:
        now = datetime.now()
        safe_name = _sanitize(filename)
        return f"{entity}/{now:%Y/%m}/{safe_name}"

    return _upload_to


def entity_id_path(entity: str, id_attr: str = "pk") -> Any:
    """返回 `{entity}/{instance_id}/{sanitized_name}` 路径生成函数。

    适用于按业务对象（如案件、任务）组织文件的场景。
    """

    def _upload_to(instance: Any, filename: str) -> str:
        obj_id = getattr(instance, id_attr, None) or "unsaved"
        safe_name = _sanitize(filename)
        return f"{entity}/{obj_id}/{safe_name}"

    return _upload_to


def entity_sub_path(entity: str, sub: str) -> Any:
    """返回固定路径 `{entity}/{sub}/`。

    适用于无需动态计算的简单场景。
    """

    def _upload_to(instance: Any, filename: str) -> str:
        return f"{entity}/{sub}/"

    return _upload_to
