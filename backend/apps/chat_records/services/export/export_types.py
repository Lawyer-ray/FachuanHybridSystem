"""导出布局配置数据类 —— 独立模块，消除循环依赖。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)

__all__: list[str] = ["ExportLayout"]


@dataclass(frozen=True)
class ExportLayout:
    """导出布局配置，包含每页图片数、是否显示页码、页眉文本。"""

    images_per_page: int
    show_page_number: bool
    header_text: str

    @classmethod
    def from_payload(
        cls,
        export_type: str,
        payload: dict[str, Any],
        *,
        default_header_text: str = "",
    ) -> ExportLayout:
        """解析 payload，支持 default_header_text 回退值。

        当 payload 中 header_text 为空或缺失时，使用 default_header_text 作为回退。
        """
        data: dict[str, Any] = payload or {}
        images_per_page = int(data.get("images_per_page") or 2)
        show_page_number = bool(data.get("show_page_number", True))
        raw_header: str = str(data.get("header_text") or "").strip()
        header_text: str = raw_header if raw_header else default_header_text

        if images_per_page not in (1, 2):
            raise ValidationException(_("仅支持 1 张/页 或 2 张/页"))

        return cls(
            images_per_page=images_per_page,
            show_page_number=show_page_number,
            header_text=header_text,
        )
