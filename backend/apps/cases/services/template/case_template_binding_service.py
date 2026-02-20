"""
案件模板绑定服务

管理案件与文书模板的绑定关系,支持自动推荐和手动绑定.
"""

from django.utils.translation import gettext_lazy as _
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional, cast

from django.db import transaction

from apps.core.exceptions import ConflictError

from .repo import CaseTemplateBindingRepo
from .template_binding_assembler import TemplateBindingAssembler
from .template_match_policy import CaseTemplateMatchInput, CaseTemplateMatchPolicy

if TYPE_CHECKING:
    from apps.core.interfaces import IDocumentService

logger = logging.getLogger(__name__)


class CaseTemplateBindingService:
    """案件模板绑定服务"""

    def __init__(
        self,
        document_service: Optional["IDocumentService"] = None,
        match_policy: CaseTemplateMatchPolicy | None = None,
        assembler: TemplateBindingAssembler | None = None,
        repo: CaseTemplateBindingRepo | None = None,
    ) -> None:
        self._document_service = document_service
        self._match_policy = match_policy or CaseTemplateMatchPolicy()
        self._assembler = assembler or TemplateBindingAssembler()
        self._repo = repo or CaseTemplateBindingRepo()

    @property
    def document_service(self) -> "IDocumentService":
        if self._document_service is None:
            raise RuntimeError("CaseTemplateBindingService.document_service 未注入")
        return self._document_service

    @property
    def match_policy(self) -> CaseTemplateMatchPolicy:
        return self._match_policy

    @property
    def assembler(self) -> TemplateBindingAssembler:
        return self._assembler

    @property
    def repo(self) -> CaseTemplateBindingRepo:
        return self._repo

    def get_bindings_for_case(
        self, case_id: int, case_type: str | None = None, case_stage: str | None = None
    ) -> dict[str, Any]:
        """
        获取案件的所有模板(绑定模板 + 通用模板),按分类分组

        Args:
            case_id: 案件ID
            case_type: 案件类型(用于匹配通用模板)
            case_stage: 案件阶段(用于匹配通用模板)

        Returns:
            包含 categories 和 total_count 的字典
        """
        # 验证案件存在
        case = self.repo.get_case(case_id)

        # 使用案件自身的类型和阶段(如果未传入)
        case_type = case_type or case.case_type
        case_stage = case_stage or case.current_stage

        # 获取案件的诉讼地位列表(我方当事人)
        legal_statuses = self.repo.get_our_legal_statuses(case)

        # 查询绑定记录
        bindings = self.repo.get_bindings_by_case_id(case_id)
        bound_template_ids = {b.template_id for b in bindings}
        bound_templates = self.document_service.get_templates_by_ids_internal(list(bound_template_ids))
        templates_by_id = {t.id: t for t in bound_templates}

        # 按 case_sub_type 分组
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list[Any])
        for binding in bindings:
            template = templates_by_id.get(binding.template_id)
            category = getattr(template, "case_sub_type", None) or "other_materials"
            grouped[category].append(self.assembler.binding_to_dict(binding=binding, template=template))

        # 获取通用模板(根据案件类型、阶段和诉讼地位匹配,排除已绑定的)
        if case_type:
            general_templates = self._get_general_templates(case_type, case_stage, bound_template_ids, legal_statuses)
            for t in general_templates:
                category = t.case_sub_type or "other_materials"
                grouped[category].append(self.assembler.general_to_dict(template=t))

        return self.assembler.categories_response(grouped=grouped)

    def _get_general_templates(
        self, case_type: str, case_stage: str | None, exclude_ids: set[Any], legal_statuses: list[str] | None = None
    ) -> list[Any]:
        """
        获取通用模板(根据案件类型、阶段和诉讼地位匹配)

        Args:
            case_type: 案件类型
            case_stage: 案件阶段
            exclude_ids: 需要排除的模板ID集合
            legal_statuses: 我方当事人的诉讼地位列表

        Returns:
            匹配的模板列表
        """
        templates = [
            t for t in self.document_service.list_case_templates_internal(is_active=True) if t.id not in exclude_ids
        ]
        match_input = CaseTemplateMatchInput(
            case_type=case_type,
            case_stage=case_stage,
            legal_statuses=set(legal_statuses or []),
        )
        return self.match_policy.filter(templates, match_input)

    def get_available_templates(self, case_id: int) -> list[dict[str, Any]]:
        """
        获取可绑定的模板列表(排除已绑定和通用模板)

        Args:
            case_id: 案件ID

        Returns:
            可绑定模板列表
        """
        # 验证案件存在并获取案件信息
        case = self.repo.get_case(case_id)

        # 获取已绑定的模板ID
        bound_template_ids = self.repo.get_bound_template_ids(case_id)

        # 获取案件的诉讼地位列表(我方当事人)
        legal_statuses = self.repo.get_our_legal_statuses(case)

        # 获取通用模板ID(根据案件类型、阶段和诉讼地位匹配的)
        general_template_ids = set()
        if case.case_type:
            general_templates = self._get_general_templates(case.case_type, case.current_stage, set(), legal_statuses)
            general_template_ids = {t.id for t in general_templates}

        # 需要排除的模板ID = 已绑定 + 通用
        exclude_ids = bound_template_ids | general_template_ids

        templates = [
            t for t in self.document_service.list_case_templates_internal(is_active=True) if t.id not in exclude_ids
        ]
        templates.sort(key=lambda x: ((getattr(x, "case_sub_type", "") or ""), (getattr(x, "name", "") or "")))

        return [self.assembler.available_to_dict(template=t) for t in templates]

    @transaction.atomic
    def bind_template(self, case_id: int, template_id: int) -> dict[str, Any]:
        """
        手动绑定模板

        Args:
            case_id: 案件ID
            template_id: 模板ID

        Returns:
            绑定记录信息
        """
        # 验证案件存在
        self.repo.get_case(case_id)

        template = self.document_service.get_template_by_id_internal(template_id)
        if not template:
            from apps.core.exceptions import NotFoundError

            raise NotFoundError(
                message=_("模板不存在"),
                code="TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            )

        # 检查是否已绑定
        if self.repo.exists_binding(case_id, template_id):
            raise ConflictError(
                message=_("绑定关系已存在"),
                code="BINDING_ALREADY_EXISTS",
                errors={"template_id": f"模板 {template_id} 已绑定到该案件"},
            )

        # 创建绑定记录
        # 注意:这里需要导入 BindingSource,但为了避免跨模块,我们使用字符串字面量或从 repo/models 导入
        # 由于 Repo 已经处理了 ORM,这里我们假设 source 传递字符串即可,但 create_binding 内部可能需要 BindingSource
        # 我们可以让 Service 传递字符串,Repo 处理转换,或者 Service 导入 BindingSource (Internal Import, OK)
        from apps.cases.models import BindingSource

        binding = self.repo.create_binding(case_id=case_id, template_id=template_id, source=BindingSource.MANUAL_BOUND)

        logger.info(f"手动绑定模板: case_id={case_id}, template_id={template_id}")

        return {
            "binding_id": binding.id,
            "template_id": template.id,
            "name": getattr(template, "name", "") or "",
            "description": getattr(template, "description", "") or "",
            "binding_source": binding.binding_source,
            "binding_source_display": binding.get_binding_source_display(),
            "created_at": binding.created_at.isoformat() if binding.created_at else None,
        }

    @transaction.atomic
    def unbind_template(self, case_id: int, binding_id: int) -> None:
        """
        解绑模板

        Args:
            case_id: 案件ID
            binding_id: 绑定记录ID

        Raises:
            NotFoundError: 案件或绑定记录不存在
            ValidationException: 自动推荐的绑定不允许删除 (Requirements 3.4)
        """
        from apps.cases.models import BindingSource
        from apps.core.exceptions import ValidationException

        # 验证案件存在
        self.repo.get_case(case_id)

        # 验证绑定记录存在
        binding = self.repo.get_binding(case_id, binding_id)

        # 检查是否为自动推荐的绑定 (Requirements 3.4)
        if binding.binding_source == BindingSource.AUTO_RECOMMENDED:
            raise ValidationException(
                message=_("自动推荐的模板不能手动移除"),
                code="CANNOT_DELETE_AUTO_RECOMMENDED",
                errors={"binding_id": "自动推荐的绑定不允许删除"},
            )

        template_id = binding.template_id
        self.repo.delete_binding(binding)

        logger.info(f"解绑模板: case_id={case_id}, binding_id={binding_id}, template_id={template_id}")

    @transaction.atomic
    def sync_auto_recommendations(self, case_id: int) -> None:
        """
        同步自动推荐的模板绑定

        根据案件的 case_type、current_stage 和诉讼地位重新计算匹配的模板,
        更新自动推荐的绑定,保留手动绑定不变.

        Args:
            case_id: 案件ID
        """
        # 获取案件
        case = self.repo.get_case(case_id)

        # 获取当前自动推荐的绑定
        current_auto_bindings = self.repo.get_auto_bound_template_ids(case_id)

        # 获取案件的诉讼地位列表(我方当事人)
        legal_statuses = self.repo.get_our_legal_statuses(case)

        # 计算新的匹配模板(包含诉讼地位匹配)
        new_matched_ids = set(
            self._match_templates_for_case(
                case_type=case.case_type, case_stage=case.current_stage, legal_statuses=legal_statuses
            )
        )

        # 获取手动绑定的模板ID(这些不应该被自动推荐覆盖)
        manual_bound_ids = self.repo.get_manual_bound_template_ids(case_id)

        # 从新匹配中排除已手动绑定的
        new_matched_ids -= manual_bound_ids

        # 计算需要删除和添加的
        to_remove = current_auto_bindings - new_matched_ids
        to_add = new_matched_ids - current_auto_bindings

        # 删除不再匹配的自动推荐绑定
        if to_remove:
            self.repo.delete_auto_bindings(case_id, to_remove)
            logger.info(f"删除自动推荐绑定: case_id={case_id}, template_ids={to_remove}")

        # 添加新匹配的自动推荐绑定
        if to_add:
            self.repo.bulk_create_auto_bindings(case_id, to_add)
            logger.info(f"添加自动推荐绑定: case_id={case_id}, template_ids={to_add}")

    def get_unified_templates(self, case_id: int) -> list[dict[str, Any]]:
        """
        获取统一模板列表(用于新 Tab 展示)

        返回案件绑定的所有模板(包括手动绑定和通用模板),
        每个模板包含 function_code 字段.

        Args:
            case_id: 案件ID

        Returns:
            模板列表,每个模板包含:
            - template_id: 模板ID
            - name: 模板名称
            - function_code: 功能标识(可为 null)
            - description: 模板描述
            - binding_source: 绑定来源
            - binding_source_display: 绑定来源显示名称
        """
        # 验证案件存在
        case = self.repo.get_case(case_id)

        # 获取案件类型、阶段和诉讼地位
        case_type = case.case_type
        case_stage = case.current_stage
        legal_statuses = self.repo.get_our_legal_statuses(case)

        bindings = self.repo.get_bindings_by_case_id(case_id)
        bound_template_ids = {b.template_id for b in bindings}
        bound_templates = self.document_service.get_templates_by_ids_internal(list(bound_template_ids))
        templates_by_id = {t.id: t for t in bound_templates}

        templates = []
        for binding in bindings:
            template = templates_by_id.get(binding.template_id)
            templates.append(
                {
                    "template_id": binding.template_id,
                    "name": getattr(template, "name", "") if template else "",
                    "function_code": getattr(template, "function_code", None) if template else None,
                    "description": getattr(template, "description", "") if template else "",
                    "binding_source": binding.binding_source,
                    "binding_source_display": str(binding.get_binding_source_display()),
                }
            )

        # 获取通用模板(根据案件类型、阶段和诉讼地位匹配,排除已绑定的)
        if case_type:
            general_templates = self._get_general_templates(case_type, case_stage, bound_template_ids, legal_statuses)
            for t in general_templates:
                templates.append(
                    {
                        "template_id": t.id,
                        "name": t.name,
                        "function_code": getattr(t, "function_code", None),
                        "description": t.description or "",
                        "binding_source": "general",
                        "binding_source_display": "通用",
                    }
                )

        logger.info(f"获取统一模板列表: case_id={case_id}, count={len(templates)}")

        return templates

    def _match_templates_for_case(
        self, case_type: str | None, case_stage: str | None, legal_statuses: list[str] | None = None
    ) -> list[int]:
        templates = self.document_service.list_case_templates_internal(is_active=True)
        match_input = CaseTemplateMatchInput(
            case_type=case_type,
            case_stage=case_stage,
            legal_statuses=set(legal_statuses or []),
        )
        return [cast(Any, t).id for t in self.match_policy.filter(templates, match_input)]
