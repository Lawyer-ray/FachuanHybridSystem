"""
Schema 基类和 Mixin
提供通用的字段解析方法，减少重复代码
"""
from typing import Any, Optional
from datetime import datetime
from django.utils import timezone


class TimestampMixin:
    """
    时间戳字段解析 Mixin
    为 Schema 提供统一的时间字段处理
    """

    @staticmethod
    def _resolve_datetime(value: Any) -> Optional[datetime]:
        """
        统一处理 datetime 字段，转换为本地时间

        Args:
            value: datetime 对象或 None

        Returns:
            本地化的 datetime 或 None
        """
        if value is None:
            return None
        try:
            return timezone.localtime(value)
        except Exception:
            return value

    @staticmethod
    def _resolve_datetime_iso(value: Any) -> Optional[str]:
        """
        统一处理 datetime 字段，转换为 ISO 格式字符串

        Args:
            value: datetime 对象或 None

        Returns:
            ISO 格式字符串或 None
        """
        if value is None:
            return None
        try:
            local_time = timezone.localtime(value)
            return local_time.isoformat()
        except Exception:
            return value.isoformat() if hasattr(value, 'isoformat') else str(value)


class DisplayLabelMixin:
    """
    显示标签解析 Mixin
    为 choices 字段提供统一的 label 获取方法
    """

    @staticmethod
    def _get_display(obj: Any, field_name: str) -> Optional[str]:
        """
        获取 choices 字段的显示值

        Args:
            obj: Model 实例
            field_name: 字段名

        Returns:
            显示值或 None
        """
        try:
            getter = getattr(obj, f"get_{field_name}_display", None)
            if getter:
                return getter()
            return getattr(obj, field_name, None)
        except Exception:
            return None


class FileFieldMixin:
    """
    文件字段解析 Mixin
    为 FileField 提供统一的 URL 和路径获取方法
    """

    @staticmethod
    def _get_file_url(file_field: Any) -> Optional[str]:
        """
        获取文件的 URL

        Args:
            file_field: FileField 实例

        Returns:
            文件 URL 或 None
        """
        if not file_field:
            return None
        try:
            return file_field.url
        except Exception:
            return None

    @staticmethod
    def _get_file_path(file_field: Any) -> Optional[str]:
        """
        获取文件的路径

        Args:
            file_field: FileField 实例

        Returns:
            文件路径或 None
        """
        if not file_field:
            return None
        try:
            return file_field.path
        except Exception:
            return None


# 组合所有 Mixin 的基类
class SchemaMixin(TimestampMixin, DisplayLabelMixin, FileFieldMixin):
    """
    Schema 通用 Mixin
    组合所有常用的字段解析方法
    """
    pass
