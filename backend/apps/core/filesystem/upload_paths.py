"""统一的 upload_to 路径工厂函数。

所有新 FileField/ImageField 应使用本模块提供的工厂函数生成 upload_to，
确保文件路径按 `{app_entity}/YYYY/MM/` 规范组织。

用法示例::

    from apps.core.filesystem.upload_paths import DatedUUIDPath

    class MyModel(models.Model):
        file = FileField(upload_to=DatedUUIDPath("my_entity"))
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from django.db.models.fields.files import FieldFile


def _sanitize(filename: str) -> str:
    """清理文件名，去除危险字符，保留中文。"""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^0-9A-Za-z一-鿿._-]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "file"


class DatedUUIDPath:
    """生成 `{entity}/YYYY/MM/{uuid_hex}{ext}` 路径。

    适用于需要匿名存储、防冲突的场景。
    """

    def __init__(self, entity: str) -> None:
        self.entity = entity

    def __call__(self, instance: Any, filename: str) -> str:
        now = datetime.now()
        ext = ""
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        return f"{self.entity}/{now:%Y/%m}/{uuid.uuid4().hex}{ext}"

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return (
            "apps.core.filesystem.upload_paths.DatedUUIDPath",
            (self.entity,),
            {},
        )


class DatedOriginalPath:
    """生成 `{entity}/YYYY/MM/{sanitized_name}` 路径。

    适用于需要保留原始文件名可读性的场景。
    """

    def __init__(self, entity: str) -> None:
        self.entity = entity

    def __call__(self, instance: Any, filename: str) -> str:
        now = datetime.now()
        safe_name = _sanitize(filename)
        return f"{self.entity}/{now:%Y/%m}/{safe_name}"

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return (
            "apps.core.filesystem.upload_paths.DatedOriginalPath",
            (self.entity,),
            {},
        )


class EntityIdPath:
    """生成 `{entity}/{instance_id}/{sanitized_name}` 路径。

    适用于按业务对象（如案件、任务）组织文件的场景。
    """

    def __init__(self, entity: str, id_attr: str = "pk") -> None:
        self.entity = entity
        self.id_attr = id_attr

    def __call__(self, instance: Any, filename: str) -> str:
        obj_id = getattr(instance, self.id_attr, None) or "unsaved"
        safe_name = _sanitize(filename)
        return f"{self.entity}/{obj_id}/{safe_name}"

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return (
            "apps.core.filesystem.upload_paths.EntityIdPath",
            (self.entity, self.id_attr),
            {},
        )


class EntitySubPath:
    """生成固定路径 `{entity}/{sub}/`。

    适用于无需动态计算的简单场景。
    """

    def __init__(self, entity: str, sub: str) -> None:
        self.entity = entity
        self.sub = sub

    def __call__(self, instance: Any, filename: str) -> str:
        return f"{self.entity}/{self.sub}/"

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return (
            "apps.core.filesystem.upload_paths.EntitySubPath",
            (self.entity, self.sub),
            {},
        )
