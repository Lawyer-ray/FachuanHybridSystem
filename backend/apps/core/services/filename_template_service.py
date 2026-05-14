"""文件名模板服务

提供可配置的文件名模板渲染和通用碰撞处理。
模板通过 SystemConfig 存储，用户可在 admin 页面自定义。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from apps.core.interfaces import ISystemConfigService

logger = logging.getLogger(__name__)


def _get_system_config_service() -> ISystemConfigService:
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_system_config_service()


# 法院文书模板
COURT_DOC_KEY = "FILENAME_TEMPLATE_COURT_DOC"
COURT_DOC_DEFAULT = "{title}（{case_name}）_{date}收"
COURT_DOC_PLACEHOLDERS: ClassVar[set[str]] = {"title", "case_name", "date"}

# 生成文档模板
GENERATED_DOC_KEY = "FILENAME_TEMPLATE_GENERATED_DOC"
GENERATED_DOC_DEFAULT = "{doc_type}（{case_name}）V{version}_{date}"
GENERATED_DOC_PLACEHOLDERS: ClassVar[set[str]] = {"doc_type", "case_name", "version", "date"}


class FilenameTemplateService:
    """文件名模板服务

    负责：
    1. 从 SystemConfig 读取模板配置
    2. 渲染模板（替换占位符）
    3. 通用碰撞处理（不依赖特定字符）
    """

    _system_config_service: ISystemConfigService | None = None

    @classmethod
    def _config_service(cls) -> ISystemConfigService:
        if cls._system_config_service is None:
            cls._system_config_service = _get_system_config_service()
        return cls._system_config_service

    @classmethod
    def get_template(cls, key: str, default: str) -> str:
        """获取模板配置值，数据库无记录时返回 default"""
        return str(cls._config_service().get_value(key, default=default) or default)

    @classmethod
    def render_court_doc(cls, *, title: str, case_name: str, date: str) -> str:
        """渲染法院文书文件名（不含扩展名）

        Args:
            title: 文书标题
            case_name: 案件名称
            date: 日期字符串（YYYYMMDD）

        Returns:
            渲染后的文件名（不含 .pdf）
        """
        template = cls.get_template(COURT_DOC_KEY, COURT_DOC_DEFAULT)
        return cls._render(template, COURT_DOC_PLACEHOLDERS, title=title, case_name=case_name, date=date)

    @classmethod
    def render_generated_doc(cls, *, doc_type: str, case_name: str, version: str, date: str) -> str:
        """渲染生成文档文件名（不含扩展名）

        Args:
            doc_type: 文档类型（如"起诉状"、"合同"）
            case_name: 案件名称
            version: 版本号（纯数字，如 "1"）
            date: 日期字符串（YYYYMMDD）

        Returns:
            渲染后的文件名（不含 .docx）
        """
        template = cls.get_template(GENERATED_DOC_KEY, GENERATED_DOC_DEFAULT)
        return cls._render(
            template, GENERATED_DOC_PLACEHOLDERS, doc_type=doc_type, case_name=case_name, version=version, date=date
        )

    @classmethod
    def _render(cls, template: str, valid_placeholders: set[str], **kwargs: str) -> str:
        """渲染模板，替换占位符

        无效占位符保留原文并 warn。
        """
        # 检查无效占位符
        found = re.findall(r"\{(\w+)\}", template)
        for ph in found:
            if ph not in valid_placeholders:
                logger.warning("文件名模板中包含无效占位符: {%s}，将保留原文", ph)

        # 替换有效占位符
        result = template
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", value)

        return result

    @classmethod
    def get_unique_filepath(cls, target_dir: str | Path, filename: str) -> tuple[str, str]:
        """获取唯一的文件路径，文件名冲突时自动追加数字后缀

        通用碰撞处理，不依赖文件名中的特定字符（如"收"）。
        策略：在扩展名前追加 _1、_2、... 直到无冲突。

        Args:
            target_dir: 目标目录
            filename: 原始文件名

        Returns:
            (完整路径, 新文件名)
        """
        target = Path(target_dir)
        p = Path(filename)
        stem, ext = p.stem, p.suffix

        # 直接尝试原始文件名
        filepath = target / filename
        if not filepath.exists():
            return str(filepath), filename

        # 追加数字后缀
        counter = 1
        while counter <= 100:
            new_filename = f"{stem}_{counter}{ext}"
            filepath = target / new_filename
            if not filepath.exists():
                return str(filepath), new_filename
            counter += 1

        # 最终降级：时间戳
        import time

        timestamp = int(time.time())
        new_filename = f"{stem}_{timestamp}{ext}"
        filepath = target / new_filename
        return str(filepath), new_filename
