"""
案件文件模板 Admin 服务

为案件编辑页的文件模板模块提供业务逻辑支持.
负责获取匹配的模板、可绑定的模板以及模板显示数据.

Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.3, 2.4
"""

from django.utils.translation import gettext_lazy as _
import logging
from typing import TYPE_CHECKING, Any, Optional

from .repo import CaseTemplateBindingRepo
from .wiring import get_document_service

if TYPE_CHECKING:
    from apps.core.interfaces import IDocumentService

    from .case_template_binding_service import CaseTemplateBindingService

logger = logging.getLogger(__name__)


class CaseDocumentTemplateAdminService:
    """
    案件文件模板 Admin 服务

    为案件编辑页的文件模板 Inline 模块提供业务逻辑支持.
    使用依赖注入模式,支持 DocumentService 和 CaseTemplateBindingService.

    Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.3, 2.4
    """

    def __init__(
        self,
        document_service: Optional["IDocumentService"] = None,
        binding_service: Optional["CaseTemplateBindingService"] = None,
        repo: CaseTemplateBindingRepo | None = None,
    ) -> None:
        self._document_service = document_service
        self._binding_service = binding_service
        self._repo = repo or CaseTemplateBindingRepo()

    @property
    def document_service(self) -> "IDocumentService":
        """延迟加载文档服务"""
        if self._document_service is None:
            self._document_service = get_document_service()
        return self._document_service

    @property
    def binding_service(self) -> "CaseTemplateBindingService":
        """延迟加载绑定服务"""
        if self._binding_service is None:
            from .wiring import get_case_template_binding_service

            self._binding_service = get_case_template_binding_service()
        return self._binding_service

    @property
    def repo(self) -> CaseTemplateBindingRepo:
        return self._repo

    def get_matched_templates_for_case(
        self, case_id: int, case_type: str, case_stage: str, legal_statuses: list[str]
    ) -> list[dict[str, Any]]:
        """
        获取案件匹配的文件模板

        根据案件类型、阶段和诉讼地位筛选匹配的模板.

        匹配规则:
        - 模板的 case_types 包含 'all' 或包含案件的 case_type,或为空列表
        - 模板的 case_stages 包含 'all' 或包含案件的 current_stage,或为空列表
        - 模板的 legal_statuses 为空时匹配任意诉讼地位(Requirements 1.6)
        - 模板的 legal_statuses 非空时,根据 legal_status_match_mode 进行匹配

        Args:
            case_id: 案件ID
            case_type: 案件类型
            case_stage: 案件阶段
            legal_statuses: 我方当事人的诉讼地位列表

        Returns:
            匹配的模板列表,每个元素包含:
            - id: 模板ID
            - name: 模板名称
            - description: 模板描述
            - case_sub_type: 案件文件子类型
            - case_sub_type_display: 案件文件子类型显示名称
            - function_code: 功能标识(可为 null)

        Requirements: 1.3, 1.4, 1.5, 1.6
        """

        if not case_type:
            logger.info(f"案件 {case_id} 未设置案件类型,返回空匹配列表")
            return []

        templates = self.document_service.list_case_templates_internal(is_active=True)

        matched: list[dict[str, Any]] = []
        case_legal_statuses_set = set(legal_statuses) if legal_statuses else set()
        sub_type_display: dict[str | None, str] = {}

        for template in templates:
            # 1. 匹配案件类型 (Requirements 1.3)
            template_case_types = getattr(template, "case_types", None) or []
            if template_case_types and "all" not in template_case_types and case_type not in template_case_types:
                continue

            # 2. 匹配案件阶段 (Requirements 1.4)
            template_case_stages = getattr(template, "case_stages", None) or []
            if template_case_stages and case_stage:
                # 规范化案件阶段(处理再审相关阶段)
                normalized_stages = self._normalize_case_stage(case_stage)
                if "all" not in template_case_stages and not any(
                    stage in template_case_stages for stage in normalized_stages
                ):
                    continue

            # 3. 匹配诉讼地位 (Requirements 1.5, 1.6)
            template_legal_statuses = getattr(template, "legal_statuses", None) or []
            match_mode = getattr(template, "legal_status_match_mode", None) or "any"

            if not self._match_legal_status(template_legal_statuses, case_legal_statuses_set, match_mode):
                continue

            # 模板匹配成功,添加到结果列表
            matched.append(
                {
                    "id": template.id,
                    "name": getattr(template, "name", "") or "",
                    "description": getattr(template, "description", "") or "",
                    "case_sub_type": getattr(template, "case_sub_type", None),
                    "case_sub_type_display": sub_type_display.get(
                        getattr(template, "case_sub_type", None), getattr(template, "case_sub_type", None) or ""
                    ),
                    "function_code": getattr(template, "function_code", None),
                }
            )

        logger.info(
            f"案件 {case_id} 匹配到 {len(matched)} 个文件模板,"
            f"case_type={case_type}, case_stage={case_stage}, "
            f"legal_statuses={legal_statuses}"
        )

        return matched

    def get_available_templates_for_binding(self, case_id: int, exclude_template_ids: set[int]) -> list[dict[str, Any]]:
        """
        获取可手动绑定的模板列表

        排除已自动匹配和已手动绑定的模板.

        Args:
            case_id: 案件ID
            exclude_template_ids: 需要排除的模板ID集合(已自动匹配 + 已手动绑定)

        Returns:
            可绑定的模板列表,每个元素包含:
            - template_id: 模板ID
            - name: 模板名称
            - description: 模板描述
            - case_sub_type: 案件文件子类型
            - case_sub_type_display: 案件文件子类型显示名称
            - function_code: 功能标识(可为 null)

        Requirements: 2.3, 2.4
        """

        templates = [
            t
            for t in self.document_service.list_case_templates_internal(is_active=True)
            if t.id not in exclude_template_ids
        ]
        templates.sort(key=lambda x: ((getattr(x, "case_sub_type", "") or ""), (getattr(x, "name", "") or "")))

        sub_type_display: dict[str | None, str] = {}

        result = [
            {
                "template_id": t.id,
                "name": getattr(t, "name", "") or "",
                "description": getattr(t, "description", "") or "",
                "case_sub_type": getattr(t, "case_sub_type", None),
                "case_sub_type_display": sub_type_display.get(
                    getattr(t, "case_sub_type", None), getattr(t, "case_sub_type", None) or ""
                ),
                "function_code": getattr(t, "function_code", None),
            }
            for t in templates
        ]

        logger.info(f"案件 {case_id} 可绑定模板数量: {len(result)},排除模板数量: {len(exclude_template_ids)}")

        return result

    def get_templates_display_data(self, case_id: int) -> dict[str, Any]:
        """
        获取模板显示数据

        返回自动匹配和手动绑定的模板,分组显示.

        Args:
            case_id: 案件ID

        Returns:
            包含以下字段的字典:
            - auto_matched: 自动匹配的模板列表
            - manual_bound: 手动绑定的模板列表
            - available_for_binding: 可手动绑定的模板列表
            - total_count: 总模板数量
        """
        from apps.cases.models import BindingSource
        from apps.core.exceptions import NotFoundError

        # 获取案件信息
        case = self.repo.get_case_optional(case_id)
        if not case:
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            )

        # 获取案件的诉讼地位列表(我方当事人)
        legal_statuses = self.repo.get_our_legal_statuses(case)

        # 1. 获取自动匹配的模板
        auto_matched = self.get_matched_templates_for_case(
            case_id=case_id,
            case_type=case.case_type or "",
            case_stage=case.current_stage or "",
            legal_statuses=legal_statuses,
        )
        auto_matched_ids = {t["id"] for t in auto_matched}

        # 2. 获取已手动绑定的模板
        # 这里的 filter 逻辑可以保留,或者也在 repo 中添加专门方法
        # 但既然我们有 get_bindings_by_case_id,可以复用并过滤
        bindings = self.repo.get_bindings_by_case_id(case_id)
        manual_bindings = [b for b in bindings if b.binding_source == BindingSource.MANUAL_BOUND]

        sub_type_display: dict[str | None, str] = {}
        manual_bound: list[dict[str, Any]] = []
        manual_bound_ids: set[int] = set()

        for binding in manual_bindings:
            template = binding.template
            manual_bound_ids.add(template.id)
            manual_bound.append(
                {
                    "binding_id": binding.id,
                    "id": template.id,
                    "name": template.name,
                    "description": template.description or "",
                    "case_sub_type": template.case_sub_type,
                    "case_sub_type_display": sub_type_display.get(template.case_sub_type, template.case_sub_type or ""),
                    "function_code": getattr(template, "function_code", None),
                    "created_at": binding.created_at.isoformat() if binding.created_at else None,
                }
            )

        # 3. 获取可手动绑定的模板(排除自动匹配和已手动绑定的)
        exclude_ids = auto_matched_ids | manual_bound_ids
        available_for_binding = self.get_available_templates_for_binding(
            case_id=case_id, exclude_template_ids=exclude_ids
        )

        total_count = len(auto_matched) + len(manual_bound)

        logger.info(
            f"案件 {case_id} 模板显示数据: "
            f"auto_matched={len(auto_matched)}, "
            f"manual_bound={len(manual_bound)}, "
            f"available={len(available_for_binding)}"
        )

        return {
            "auto_matched": auto_matched,
            "manual_bound": manual_bound,
            "available_for_binding": available_for_binding,
            "total_count": total_count,
        }

    def _match_legal_status(
        self, template_legal_statuses: list[str], case_legal_statuses_set: set[str], match_mode: str
    ) -> bool:
        """
        匹配诉讼地位

        根据模板的诉讼地位配置和匹配模式,判断是否匹配案件的诉讼地位.

        匹配规则:
        - 模板诉讼地位为空时,匹配任意诉讼地位(Requirements 1.6)
        - any 模式:案件诉讼地位与模板诉讼地位有交集,或案件诉讼地位为空
        - all 模式:案件诉讼地位包含模板的所有诉讼地位
        - exact 模式:案件诉讼地位与模板诉讼地位完全一致

        Args:
            template_legal_statuses: 模板配置的诉讼地位列表
            case_legal_statuses_set: 案件的诉讼地位集合
            match_mode: 匹配模式(any/all/exact)

        Returns:
            是否匹配

        Requirements: 1.5, 1.6
        """
        # 模板未配置诉讼地位,匹配任意 (Requirements 1.6)
        if not template_legal_statuses:
            return True

        template_legal_statuses_set = set(template_legal_statuses)

        if match_mode == "any":
            # 任意匹配:案件诉讼地位为空,或与模板诉讼地位有交集
            if not case_legal_statuses_set:
                return True
            return bool(case_legal_statuses_set & template_legal_statuses_set)

        elif match_mode == "all":
            # 全部包含:案件诉讼地位包含模板的所有诉讼地位
            return template_legal_statuses_set <= case_legal_statuses_set

        elif match_mode == "exact":
            # 完全一致:案件诉讼地位与模板诉讼地位完全相同
            return case_legal_statuses_set == template_legal_statuses_set

        # 未知匹配模式,默认使用 any 模式
        if not case_legal_statuses_set:
            return True
        return bool(case_legal_statuses_set & template_legal_statuses_set)

    def _normalize_case_stage(self, case_stage: str) -> list[str]:
        """
        规范化案件阶段

        将再审相关的多个阶段统一映射到 'retrial'.

        Args:
            case_stage: 原始案件阶段

        Returns:
            规范化后的阶段列表
        """
        if not case_stage:
            return []

        # 再审相关阶段映射
        retrial_related = {
            "retrial_first",
            "retrial_second",
            "apply_retrial",
            "rehearing_first",
            "rehearing_second",
            "review",
            "petition",
            "apply_protest",
            "petition_protest",
        }

        if case_stage in retrial_related:
            return ["retrial", case_stage]

        return [case_stage]
