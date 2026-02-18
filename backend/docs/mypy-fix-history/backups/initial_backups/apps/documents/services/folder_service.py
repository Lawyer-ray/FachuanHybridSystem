"""Business logic services."""

from __future__ import annotations

from typing import Any

"""
文件夹模板服务

提供文件夹模板的 CRUD 操作、结构验证和ID唯一性验证功能.

Requirements: 1.2, 1.4, 1.7, 1.8
"""

import re

from apps.documents.models import FolderTemplate
from apps.documents.usecases.folder_template.folder_template_usecases import FolderTemplateUsecases


class FolderTemplateService:
    """
    文件夹模板服务

    负责文件夹模板的创建、更新、查询、验证和ID唯一性检查.
    """

    # 文件系统无效字符
    INVALID_CHARS = r'[/\\:*?"<>|]'
    INVALID_CHARS_PATTERN = re.compile(INVALID_CHARS)

    def __init__(self, *, usecases: FolderTemplateUsecases) -> None:
        self.usecases = usecases

    def validate_and_fix_structure_ids(
        self, structure: dict[str, Any], template_id: int | None = None
    ) -> tuple[bool, dict, list[str]]:
        """
        验证并自动修复文件夹结构中的重复ID

        Args:
            structure: 文件夹结构JSON
            template_id: 当前模板ID(更新时使用,排除自身)

        Returns:
            (is_fixed, fixed_structure, fix_messages)
        """
        return self.usecases.validate_and_fix_structure_ids(structure=structure, template_id=template_id)

    def validate_structure_ids(
        self, structure: dict[str, Any], template_id: int | None = None
    ) -> tuple[bool, list[str]]:
        """
        验证文件夹结构中的ID唯一性

        Args:
            structure: 文件夹结构JSON
            template_id: 当前模板ID(更新时使用,排除自身)

        Returns:
            (is_valid, error_messages)
        """
        return self.usecases.validate_structure_ids(structure=structure, template_id=template_id)

    def get_duplicate_id_report(self) -> dict[str, Any]:
        return self.usecases.get_duplicate_id_report()

    def create_template(
        self,
        name: str,
        case_type: str,
        case_stage: str,
        structure: dict[str, Any],
        is_default: bool = False,
        is_active: bool = True,
        **kwargs,
    ) -> FolderTemplate:
        return self.usecases.create_template(
            name=name,
            case_type=case_type,
            case_stage=case_stage,
            structure=structure,
            is_default=is_default,
            is_active=is_active,
            **kwargs,
        )

    def update_structure(self, template_id: int, structure: dict[str, Any]) -> FolderTemplate:
        """
        更新文件夹结构

        Args:
            template_id: 模板 ID
            structure: 新的文件夹结构

        Returns:
            更新后的 FolderTemplate 实例

        Raises:
            NotFoundError: 模板不存在
            ValidationException: 结构验证失败
        """
        return self.usecases.update_structure(template_id=template_id, structure=structure)

    def get_template_for_case(self, case_type: str, case_stage: str) -> FolderTemplate | None:
        """
        获取匹配的文件夹模板

        返回匹配指定案件类型和阶段的最新更新的模板.

        Args:
            case_type: 案件类型
            case_stage: 案件阶段

        Returns:
            匹配的 FolderTemplate 实例,如果没有匹配则返回 None

        Requirements: 1.4
        """
        return self.usecases.get_template_for_case(case_type=case_type, case_stage=case_stage)

    def get_template_by_id(self, template_id: int) -> FolderTemplate:
        """
        根据 ID 获取模板

        Args:
            template_id: 模板 ID

        Returns:
            FolderTemplate 实例

        Raises:
            NotFoundError: 模板不存在
        """
        return self.usecases.get_template_by_id(template_id=template_id)

    def validate_structure(self, structure: dict[str, Any]) -> tuple[bool, str]:
        """
        验证文件夹结构

        检查:
        1. 循环引用(Requirements: 1.2)
        2. 无效文件名字符(Requirements: 1.8)

        Args:
            structure: 文件夹结构 JSON

        Returns:
            (is_valid, error_message) 元组
        """
        return self.usecases.validate_structure(structure=structure)

    def _check_circular_reference(
        self, structure: dict[str, Any], visited_ids: set | None = None, path: list | None = None
    ) -> tuple[bool, str]:
        """
        检测循环引用

        通过追踪已访问的节点 ID 来检测循环.

        Args:
            structure: 文件夹结构
            visited_ids: 已访问的节点 ID 集合
            path: 当前路径

        Returns:
            (has_cycle, cycle_path) 元组
        """
        if visited_ids is None:
            visited_ids = set()
        if path is None:
            path: list[Any] = []

        children = structure.get("children", [])
        if not isinstance(children, list):
            return False, ""

        for child in children:
            if not isinstance(child, dict):
                continue

            node_id = child.get("id")
            node_name = child.get("name", "unknown")
            current_path = path + [node_name]

            if node_id is not None:
                if node_id in visited_ids:
                    return True, " -> ".join(current_path)
                visited_ids.add(node_id)

            # 递归检查子节点
            has_cycle, cycle_path = self._check_circular_reference(child, visited_ids.copy(), current_path)
            if has_cycle:
                return True, cycle_path

        return False, ""

    def _check_invalid_chars(self, structure: dict[str, Any], path: list | None = None) -> tuple[bool, str]:
        """
        检测无效文件名字符

        检查文件夹名称是否包含文件系统不允许的字符.
        无效字符: / \\ : * ? " < > |

        Args:
            structure: 文件夹结构
            path: 当前路径

        Returns:
            (has_invalid, invalid_info) 元组
        """
        if path is None:
            path: list[Any] = []

        children = structure.get("children", [])
        if not isinstance(children, list):
            return False, ""

        for child in children:
            if not isinstance(child, dict):
                continue

            name = child.get("name", "")
            current_path = path + [name]

            # 检查名称是否包含无效字符
            if name and self.INVALID_CHARS_PATTERN.search(name):
                invalid_chars = self.INVALID_CHARS_PATTERN.findall(name)
                return True, f"'{name}' 包含无效字符: {invalid_chars}"

            # 递归检查子节点
            has_invalid, invalid_info = self._check_invalid_chars(child, current_path)
            if has_invalid:
                return True, invalid_info

        return False, ""

    def list_templates(
        self, case_type: str | None = None, case_stage: str | None = None, is_active: bool | None = None
    ) -> list[FolderTemplate]:
        """
        列出文件夹模板

        Args:
            case_type: 按案件类型过滤
            case_stage: 按案件阶段过滤
            is_active: 按启用状态过滤

        Returns:
            FolderTemplate 列表
        """
        return self.usecases.list_templates(case_type=case_type, case_stage=case_stage, is_active=is_active)

    def delete_template(self, template_id: int) -> bool:
        """
        删除模板(软删除)

        Args:
            template_id: 模板 ID

        Returns:
            是否成功

        Raises:
            NotFoundError: 模板不存在
        """
        return self.usecases.delete_template(template_id=template_id)

    def create_template_from_dict(self, data: dict[str, Any]) -> FolderTemplate:
        """
        从字典数据创建文件夹模板

        用于 API 层调用,接收 Schema 转换后的字典数据.

        Args:
            data: 包含模板字段的字典

        Returns:
            创建的 FolderTemplate 实例

        Raises:
            ValidationException: 验证失败

        Requirements: 1.1
        """
        return self.usecases.create_template_from_dict(data=data)

    def update_template_from_dict(self, template_id: int, data: dict[str, Any]) -> FolderTemplate:
        """
        从字典数据更新文件夹模板

        用于 API 层调用,接收 Schema 转换后的字典数据.

        Args:
            template_id: 模板 ID
            data: 包含更新字段的字典

        Returns:
            更新后的 FolderTemplate 实例

        Raises:
            NotFoundError: 模板不存在
            ValidationException: 验证失败

        Requirements: 1.1
        """
        return self.usecases.update_template_from_dict(template_id=template_id, data=data)
