"""
文书模板 Admin 服务

处理Admin层的复杂业务逻辑

Requirements: 3.1, 3.2, 3.3
"""

import logging
from typing import Any

from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class DocumentTemplateAdminService:
    """文书模板Admin服务"""

    def __init__(self, template_service: Any | None = None) -> None:
        self._template_service = template_service

    @property
    def template_service(self) -> Any:
        """延迟加载模板服务"""
        if self._template_service is None:
            from .template_service import DocumentTemplateService

            self._template_service = DocumentTemplateService()
        return self._template_service

    def get_form_initial_values(self, instance: Any, existing_files: list[tuple[str, str]]) -> dict[str, Any]:
        """
        获取表单初始值

        Args:
            instance: 模板实例
            existing_files: 已有文件列表 [(path, display_name), ...]

        Returns:
            初始值字典
        """
        initial = {
            "template_type": instance.template_type,
            "contract_sub_type": instance.contract_sub_type or "",
            "case_sub_type": instance.case_sub_type or "",
            "contract_types_field": instance.contract_types or [],
            "case_types_field": instance.case_types or [],
            "case_stage_field": "",
            "existing_file": "",
            "file_path": "",
            "legal_statuses_field": instance.legal_statuses or [],
            "legal_status_match_mode": instance.legal_status_match_mode or "any",
        }

        # 案件阶段:从列表取第一个值或空
        case_stages = instance.case_stages or []
        initial["case_stage_field"] = case_stages[0] if case_stages else ""

        # 处理文件字段
        if instance.file_path:
            current_path = instance.file_path
            for path, _ in existing_files:
                if path == current_path:
                    initial["existing_file"] = path
                    initial["file_path"] = ""  # 清空file_path避免冲突
                    break
        elif instance.file:
            current_file_name = instance.file.name
            for path, _ in existing_files:
                if path == current_file_name:
                    initial["existing_file"] = path
                    break

        return initial

    def validate_file_sources(
        self, existing_file: str, uploaded_file, file_path: str, instance, is_editing: bool
    ) -> dict[str, Any]:
        """
        验证文件来源

        Args:
            existing_file: 从模板库选择的文件
            uploaded_file: 上传的文件
            file_path: 手动输入的路径
            instance: 模板实例
            is_editing: 是否是编辑模式

        Returns:
            验证结果字典,包含 is_valid, error, cleaned_data
        """
        result = {
            "is_valid": True,
            "error": None,
            "cleaned_data": {"existing_file": existing_file, "file": uploaded_file, "file_path": file_path},
        }

        # 检查是否是编辑现有记录且没有修改文件相关字段
        if is_editing:
            _original_file = instance.file
            original_file_path = instance.file_path

            file_modified = (
                bool(existing_file) or bool(uploaded_file) or (file_path and file_path.strip() != original_file_path)
            )

            if not file_modified:
                result["skip_file_validation"] = True
                return result

        # 统计有多少种文件来源被选择
        sources = sum([bool(existing_file), bool(uploaded_file), bool(file_path and file_path.strip())])

        if sources > 1:
            result["is_valid"] = False
            result["error"] = _("只能选择一种文件来源:从模板库选择、上传新文件、或手动输入路径")
            return result

        # 如果选择了已有文件,将其设置为file_path
        if existing_file:
            result["cleaned_data"]["file_path"] = existing_file
            result["cleaned_data"]["file"] = None
            result["cleaned_data"]["existing_file"] = ""

        # 检查是否有文件来源
        has_file_source = bool(existing_file) or bool(uploaded_file) or bool(file_path and file_path.strip())
        has_existing_file = is_editing and (instance.file or instance.file_path)

        if not has_file_source and not has_existing_file:
            result["is_valid"] = False
            result["error"] = _("必须选择一种文件来源")

        return result

    def validate_template_type(
        self,
        template_type: str,
        contract_sub_type: str,
        case_sub_type: str,
        is_editing: bool,
        original_template_type: str | None,
    ) -> dict[str, Any]:
        """
        验证模板类型

        Args:
            template_type: 模板类型
            contract_sub_type: 合同子类型

        Returns:
            验证结果字典
        """
        result = {
            "is_valid": True,
            "errors": {},
            "contract_sub_type": contract_sub_type,
            "case_sub_type": case_sub_type,
        }

        if template_type == "contract":
            if not contract_sub_type:
                result["is_valid"] = False
                result["errors"]["contract_sub_type"] = _("选择合同文书模板时,必须选择合同子类型")
            result["case_sub_type"] = None
        elif template_type == "case":
            result["contract_sub_type"] = None
            should_require_case_sub_type = (not is_editing) or (
                original_template_type is not None and original_template_type != "case"
            )
            if should_require_case_sub_type and not case_sub_type:
                result["is_valid"] = False
                result["errors"]["case_sub_type"] = _("选择案件文书模板时,必须选择案件文件子类型")

        return result

    def prepare_save_data(
        self,
        template_type: str,
        contract_sub_type: str,
        case_sub_type: str,
        contract_types_field: list[str],
        case_types_field: list[str],
        case_stage_field: str,
        file: Any,
        file_path: str,
        legal_statuses_field: list[str] | None = None,
        legal_status_match_mode: str | None = None,
    ) -> dict[str, Any]:
        """
        准备保存数据

        Args:
            template_type: 模板类型
            contract_sub_type: 合同子类型
            case_sub_type: 案件子类型
            contract_types_field: 合同类型列表
            case_types_field: 案件类型列表
            case_stage_field: 案件阶段
            file: 上传的文件
            file_path: 文件路径
            legal_statuses_field: 诉讼地位列表
            legal_status_match_mode: 诉讼地位匹配模式

        Returns:
            准备好的数据字典
        """
        data = {
            "template_type": template_type,
            "contract_sub_type": contract_sub_type if template_type == "contract" else None,
            "case_sub_type": case_sub_type if template_type == "case" else None,
            "contract_types": [],
            "case_types": [],
            "case_stages": [],
            "legal_statuses": [],
            "legal_status_match_mode": "any",
            "file": file,
            "file_path": file_path,
        }

        if template_type == "contract":
            data["contract_types"] = contract_types_field or []
        elif template_type == "case":
            data["case_types"] = case_types_field or []
            data["case_stages"] = [case_stage_field] if case_stage_field else []
            # 仅案件模板保存诉讼地位
            data["legal_statuses"] = legal_statuses_field or []
            data["legal_status_match_mode"] = legal_status_match_mode or "any"
        else:
            data["contract_types"] = contract_types_field or []
            data["case_types"] = case_types_field or []
            data["case_stages"] = [case_stage_field] if case_stage_field else []

        # 确保file和file_path互斥
        if file:
            data["file_path"] = ""
        elif file_path:
            data["file"] = ""

        return data

    def render_placeholders_table(self, placeholders: list[str], undefined: set[str]) -> str:
        """
        渲染占位符表格HTML

        Args:
            placeholders: 占位符列表
            undefined: 未定义的占位符集合

        Returns:
            HTML字符串
        """
        if not placeholders:
            return str(_("未找到占位符"))

        html_parts = ['<div style="max-height: 300px; overflow-y: auto;">']
        html_parts.append('<table style="width: 100%; border-collapse: collapse;">')
        html_parts.append('<tr style="background: #f5f5f5;">')
        html_parts.append('<th style="padding: 8px; text-align: left; border: 1px solid #ddd;">占位符</th>')
        html_parts.append('<th style="padding: 8px; text-align: left; border: 1px solid #ddd;">状态</th>')
        html_parts.append("</tr>")

        for placeholder in placeholders:
            if placeholder in undefined:
                status = '<span style="color: #c62828; font-weight: bold;">⚠️ 未定义</span>'
                row_style = "background: #ffebee;"
            else:
                status = '<span style="color: #2e7d32;">✓ 已定义</span>'
                row_style = ""

            html_parts.append(f'<tr style="{row_style}">')
            html_parts.append(
                f'<td style="padding: 8px; border: 1px solid #ddd; font-family: monospace;">'
                f"{{{{ {placeholder} }}}}</td>"
            )
            html_parts.append(f'<td style="padding: 8px; border: 1px solid #ddd;">{status}</td>')
            html_parts.append("</tr>")

        html_parts.append("</table>")
        html_parts.append("</div>")

        return mark_safe("".join(html_parts))

    def render_undefined_placeholders_warning(self, undefined: list[str]) -> str:
        """
        渲染未定义占位符警告HTML

        Args:
            undefined: 未定义的占位符列表

        Returns:
            HTML字符串
        """
        if not undefined:
            return mark_safe('<span style="color: #2e7d32;">✓ 所有占位符均已定义</span>')

        html_parts = [
            '<div style="background: #fff3e0; padding: 10px; border-radius: 4px; border: 1px solid #ffcc80;">'
        ]
        html_parts.append(
            f'<p style="margin: 0 0 10px 0; color: #e65100; font-weight: bold;">'
            f"⚠️ 发现 {len(undefined)} 个未定义的占位符:</p>"
        )
        html_parts.append('<ul style="margin: 0; padding-left: 20px;">')

        for placeholder in undefined:
            html_parts.append(f'<li style="font-family: monospace; color: #bf360c;">{{{{ {placeholder} }}}}</li>')

        html_parts.append("</ul>")
        html_parts.append(
            '<p style="margin: 10px 0 0 0; font-size: 12px; color: #666;">请在"替换词管理"中注册这些占位符.</p>'
        )
        html_parts.append("</div>")

        return mark_safe("".join(html_parts))

    def duplicate_template(self, template: Any) -> Any:
        """
        复制文书模板

        Args:
            template: 要复制的模板

        Returns:
            新创建的模板
        """
        from apps.documents.models import DocumentTemplate

        # 生成新名称
        new_name = f"{template.name} (副本)"
        suffix = 1
        while DocumentTemplate.objects.filter(name=new_name).exists():
            new_name = f"{template.name} (副本 {suffix})"
            suffix += 1

        # 创建副本(不复制文件,只复制配置)
        return DocumentTemplate.objects.create(
            name=new_name,
            description=template.description,
            template_type=template.template_type,
            file_path=template.file_path,
            contract_types=template.contract_types.copy() if template.contract_types else [],
            case_types=template.case_types.copy() if template.case_types else [],
            case_stages=template.case_stages.copy() if template.case_stages else [],
            is_active=False,
        )

    def batch_duplicate_templates(self, queryset: Any) -> int:
        """
        批量复制文书模板

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

    def match_legal_status(
        self, template_legal_statuses: list[str], case_legal_statuses: list[str], match_mode: str = "any"
    ) -> bool:
        """
        检查案件诉讼地位是否匹配模板配置

        实现三种匹配模式:
        - any: 任意匹配,有交集即可
        - all: 全部包含,案件诉讼地位包含模板所有配置
        - exact: 完全一致,两者相等

        Args:
            template_legal_statuses: 模板配置的诉讼地位列表
            case_legal_statuses: 案件的诉讼地位列表
            match_mode: 匹配模式 ('any', 'all', 'exact')

        Returns:
            是否匹配

        Validates: Requirements 3.2, 3.3, 3.4
        """
        # 模板未配置诉讼地位,匹配任意案件
        if not template_legal_statuses:
            return True

        # 案件无诉讼地位,不匹配任何配置了诉讼地位的模板
        if not case_legal_statuses:
            return False

        template_set = set(template_legal_statuses)
        case_set = set(case_legal_statuses)

        if match_mode == "any":
            # 任意匹配:有交集即可
            return bool(template_set & case_set)
        elif match_mode == "all":
            # 全部包含:案件诉讼地位包含模板所有配置
            return template_set <= case_set
        elif match_mode == "exact":
            # 完全一致:两者相等
            return template_set == case_set
        else:
            # 默认使用任意匹配
            return bool(template_set & case_set)
