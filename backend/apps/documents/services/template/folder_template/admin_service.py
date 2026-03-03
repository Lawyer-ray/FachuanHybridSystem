"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from apps.core.exceptions import NotFoundError
from apps.documents.models import FolderTemplate
from apps.documents.models.choices import FolderTemplateType, LegalStatusMatchMode

from ..folder_service import FolderTemplateService

logger = logging.getLogger("apps.documents.services.folder_template_admin_service")


class FolderTemplateAdminService:
    """文件夹模板Admin服务"""

    def __init__(self, folder_template_service: FolderTemplateService | None = None) -> None:
        self._folder_template_service = folder_template_service

    @property
    def folder_template_service(self) -> FolderTemplateService:
        """延迟加载文件夹模板服务"""
        if self._folder_template_service is None:
            from apps.core.dependencies.documents import build_folder_template_service

            self._folder_template_service = build_folder_template_service()  # type: ignore[assignment]
        return self._folder_template_service

    def validate_and_fix_template_form(self, form_data: dict[str, Any]) -> dict[str, Any]:
        """
        验证并自动修复模板表单数据

        Args:
            request: HTTP请求
            form_data: 表单数据

        Returns:
            验证和修复结果
        """
        result: dict[str, Any] = {
            "is_valid": True,
            "is_fixed": False,
            "fixed_structure": None,
            "errors": [],
            "warnings": [],
            "fix_messages": [],
        }

        structure = form_data.get("structure")
        template_id = form_data.get("id")  # 更新时会有ID

        if structure:
            try:
                # 尝试自动修复重复ID
                is_fixed, fixed_structure, fix_messages = self.folder_template_service.validate_and_fix_structure_ids(
                    structure, template_id
                )

                if is_fixed:
                    result["is_fixed"] = True
                    result["fixed_structure"] = fixed_structure
                    result["fix_messages"] = fix_messages
                    result["warnings"].extend(fix_messages)

            except Exception as e:
                logger.exception(
                    "模板结构验证与修复失败",
                    extra={"template_id": template_id, "error": str(e)},
                )
                result["is_valid"] = False
                result["errors"].append(f"结构验证失败: {e!s}")

        return result

    def validate_template_form(self, form_data: dict[str, Any]) -> dict[str, Any]:
        """
        验证模板表单数据(保留原有方法用于向后兼容)

        Args:
            request: HTTP请求
            form_data: 表单数据

        Returns:
            验证结果
        """
        result: dict[str, Any] = {"is_valid": True, "errors": [], "warnings": []}

        structure = form_data.get("structure")
        template_id = form_data.get("id")  # 更新时会有ID

        if structure:
            try:
                is_valid, errors = self.folder_template_service.validate_structure_ids(structure, template_id)
                if not is_valid:
                    result["is_valid"] = False
                    result["errors"].extend(errors)
            except Exception as e:
                logger.exception(
                    "模板结构验证失败",
                    extra={"template_id": template_id, "error": str(e)},
                )
                result["is_valid"] = False
                result["errors"].append(f"结构验证失败: {e!s}")

        return result

    def validate_structure_ids(self, *, structure: Any, template_id: int | None = None) -> dict[str, Any]:
        if not structure:
            return {"success": False, "message": "缺少结构数据"}
        try:
            is_valid, errors = self.folder_template_service.validate_structure_ids(structure, template_id)
            return {"success": True, "is_valid": is_valid, "errors": errors}
        except Exception as e:
            logger.exception(
                "validate_structure_ids 失败",
                extra={"template_id": template_id, "error": str(e)},
            )
            return {"success": False, "message": f"验证失败: {e!s}"}

    def get_duplicate_report(self) -> dict[str, Any]:
        try:
            report = self.folder_template_service.get_duplicate_id_report()
            return {"success": True, "report": report}
        except Exception as e:
            logger.exception("获取重复 ID 报告失败", extra={"error": str(e)})
            return {"success": False, "error": str(e)}

    @transaction.atomic
    def initialize_default_templates(self) -> dict[str, Any]:
        """
        初始化默认文件夹模板

        Args:
            request: HTTP请求

        Returns:
            初始化结果
        """
        try:
            from .folder_template.default_templates import get_default_folder_templates

            default_templates = get_default_folder_templates()
            existing_names = set(
                FolderTemplate.objects.filter(name__in=[t["name"] for t in default_templates]).values_list(
                    "name", flat=True
                )
            )

            to_create = [
                FolderTemplate(**template_data)
                for template_data in default_templates
                if template_data["name"] not in existing_names
            ]
            FolderTemplate.objects.bulk_create(to_create, ignore_conflicts=True)

            created_count = len(to_create)
            skipped_count = len(default_templates) - created_count

            messages_out: list[dict[str, str]] = []
            if created_count > 0:
                messages_out.append({"level": "success", "message": f"✅ 成功初始化 {created_count} 个默认文件夹模板"})
            if skipped_count > 0:
                messages_out.append({"level": "info", "message": f"ℹ️ 跳过 {skipped_count} 个已存在的模板"})
            if created_count == 0 and skipped_count == 0:
                messages_out.append({"level": "warning", "message": "⚠️ 没有可初始化的模板"})

            return {
                "success": True,
                "created_count": created_count,
                "skipped_count": skipped_count,
                "messages": messages_out,
            }

        except Exception as e:
            logger.exception("初始化默认文件夹模板失败", extra={"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "messages": [{"level": "error", "message": f"❌ 初始化失败:{e!s}"}],
            }

    def prepare_save_data(
        self,
        template_type: str,
        contract_types_field: list[str],
        case_types_field: list[str],
        case_stage_field: str,
        legal_statuses_field: list[str] | None = None,
        legal_status_match_mode: str | None = None,
    ) -> dict[str, Any]:
        """
        准备保存数据

        Args:
            template_type: 模板类型
            contract_types_field: 合同类型列表
            case_types_field: 案件类型列表
            case_stage_field: 案件阶段
            legal_statuses_field: 诉讼地位列表
            legal_status_match_mode: 诉讼地位匹配模式

        Returns:
            准备好的数据字典
        """
        data = {
            "template_type": template_type,
            "contract_types": [],
            "case_types": [],
            "case_stages": [],
            "legal_statuses": [],
            "legal_status_match_mode": LegalStatusMatchMode.ANY,
        }

        if template_type == FolderTemplateType.CONTRACT:
            data["contract_types"] = contract_types_field or []
            # 合同模板清空诉讼地位字段
            data["legal_statuses"] = []
            data["legal_status_match_mode"] = LegalStatusMatchMode.ANY
        elif template_type == FolderTemplateType.CASE:
            data["case_types"] = case_types_field or []
            data["case_stages"] = [case_stage_field] if case_stage_field else []
            # 案件模板保存诉讼地位字段
            data["legal_statuses"] = legal_statuses_field or []
            data["legal_status_match_mode"] = legal_status_match_mode or LegalStatusMatchMode.ANY
        else:
            data["contract_types"] = contract_types_field or []
            data["case_types"] = case_types_field or []
            data["case_stages"] = [case_stage_field] if case_stage_field else []
            data["legal_statuses"] = legal_statuses_field or []
            data["legal_status_match_mode"] = legal_status_match_mode or LegalStatusMatchMode.ANY

        return data

    def render_structure_tree(self, structure: dict[str, Any], level: int = 0) -> str:
        """
        递归渲染文件夹树HTML

        Args:
            structure: 文件夹结构
            level: 当前层级

        Returns:
            HTML字符串
        """
        if not structure:
            return ""

        children = structure.get("children", [])
        if not children:
            return ""

        html_parts: list[Any] = []
        if level == 0:
            html_parts.append('<div style="font-family: monospace; line-height: 1.4; color: #333;">')

        html_parts.append(f'<ul style="list-style: none; margin: 0; padding-left: {20 if level > 0 else 0}px;">')

        for i, child in enumerate(children):
            name = child.get("name", "未命名")
            is_last = i == len(children) - 1

            prefix = "└── " if is_last else "├── "
            if level == 0:
                prefix = "📁 "

            html_parts.append('<li style="margin: 1px 0; white-space: nowrap;">')
            html_parts.append(f'<span style="color: #666; font-weight: normal;">{prefix}</span>')
            html_parts.append(f'<span style="color: #333; font-weight: 500;">{name}</span>')

            sub_html = self.render_structure_tree(child, level + 1)
            if sub_html:
                html_parts.append(sub_html)

            html_parts.append("</li>")

        html_parts.append("</ul>")

        if level == 0:
            html_parts.append("</div>")

        return "".join(html_parts)

    def duplicate_template(self, template: Any) -> Any:
        """
        复制文件夹模板

        Args:
            template: 要复制的模板

        Returns:
            新创建的模板
        """

        # 生成新名称
        new_name = f"{template.name} (副本)"
        suffix = 1
        while FolderTemplate.objects.filter(name=new_name).exists():
            new_name = f"{template.name} (副本 {suffix})"
            suffix += 1

        # 创建副本
        return FolderTemplate.objects.create(
            name=new_name,
            template_type=template.template_type,
            case_types=template.case_types.copy() if template.case_types else [],
            case_stages=template.case_stages.copy() if template.case_stages else [],
            contract_types=template.contract_types.copy() if template.contract_types else [],
            legal_statuses=template.legal_statuses.copy() if template.legal_statuses else [],
            legal_status_match_mode=template.legal_status_match_mode,
            structure=template.structure.copy() if template.structure else {},
            is_active=False,
        )

    def batch_duplicate_templates(self, queryset: Any) -> int:
        """
        批量复制文件夹模板

        Args:
            queryset: 要复制的模板查询集

        Returns:
            复制的数量
        """
        count = 0
        for template in queryset:
            self.duplicate_template(template)
            count += 1
        return count

    def get_structure_json(self, pk: int) -> dict[str, Any]:
        """
        查询 FolderTemplate 并返回结构 JSON

        Args:
            pk: 模板主键

        Returns:
            包含 success, structure, name 的字典

        Raises:
            NotFoundError: 模板不存在时抛出
        """

        try:
            template = FolderTemplate.objects.get(pk=pk)
        except FolderTemplate.DoesNotExist:
            raise NotFoundError(
                message=_("模板不存在"),
                code="FOLDER_TEMPLATE_NOT_FOUND",
                errors={"pk": pk},
            )
        return {
            "success": True,
            "structure": template.structure,
            "name": template.name,
        }

    def batch_activate(self, queryset: Any) -> int:
        """
        批量启用模板

        Args:
            queryset: 要启用的模板查询集

        Returns:
            实际启用的数量
        """
        return queryset.filter(is_active=False).update(is_active=True)

    def batch_deactivate(self, queryset: Any) -> int:
        """
        批量禁用模板

        Args:
            queryset: 要禁用的模板查询集

        Returns:
            实际禁用的数量
        """
        return queryset.filter(is_active=True).update(is_active=False)

    def get_folder_template_by_pk(self, pk: int | str) -> Any:
        """
        根据主键获取 FolderTemplate，供 FolderBindingForm 使用

        Args:
            pk: 模板主键

        Returns:
            FolderTemplate 实例

        Raises:
            NotFoundError: 模板不存在时抛出
        """

        try:
            return FolderTemplate.objects.get(pk=pk)
        except FolderTemplate.DoesNotExist:
            raise NotFoundError(
                message=_("模板不存在"),
                code="FOLDER_TEMPLATE_NOT_FOUND",
                errors={"pk": pk},
            )
