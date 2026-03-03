"""Data repository layer."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.cases.models import BindingSource, Case, CaseTemplateBinding
from apps.core.exceptions import NotFoundError


class CaseTemplateBindingRepo:
    """
    案件模板绑定仓储

    负责处理 CaseTemplateBinding 及相关 Case 数据的数据库操作.
    """

    def get_case(self, case_id: int) -> Case:
        """获取案件,如果不存在抛出 NotFoundError"""
        try:
            return Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            ) from None

    def get_case_optional(self, case_id: int) -> Case | None:
        """获取案件,不存在返回 None"""
        return Case.objects.filter(id=case_id).first()

    def get_bindings_by_case_id(self, case_id: int) -> list[CaseTemplateBinding]:
        """获取案件的所有绑定记录,按创建时间排序"""
        return list(CaseTemplateBinding.objects.filter(case_id=case_id).order_by("created_at"))

    def get_binding(self, case_id: int, binding_id: int) -> CaseTemplateBinding:
        """获取单个绑定记录,不存在抛出 NotFoundError"""
        try:
            return CaseTemplateBinding.objects.get(id=binding_id, case_id=case_id)
        except CaseTemplateBinding.DoesNotExist:
            raise NotFoundError(
                message=_("绑定记录不存在"),
                code="BINDING_NOT_FOUND",
                errors={"binding_id": f"ID 为 {binding_id} 的绑定记录不存在"},
            ) from None

    def exists_binding(self, case_id: int, template_id: int) -> bool:
        """检查是否存在绑定"""
        return CaseTemplateBinding.objects.filter(case_id=case_id, template_id=template_id).exists()

    def create_binding(self, case_id: int, template_id: int, source: str) -> CaseTemplateBinding:
        """创建绑定记录"""
        return CaseTemplateBinding.objects.create(case_id=case_id, template_id=template_id, binding_source=source)

    def delete_binding(self, binding: CaseTemplateBinding) -> None:
        """删除绑定记录"""
        binding.delete()

    def get_bound_template_ids(self, case_id: int) -> set[int]:
        """获取所有已绑定的模板ID集合"""
        return set(CaseTemplateBinding.objects.filter(case_id=case_id).values_list("template_id", flat=True))

    def get_auto_bound_template_ids(self, case_id: int) -> set[int]:
        """获取所有自动推荐的模板ID集合"""
        return set(
            CaseTemplateBinding.objects.filter(
                case_id=case_id, binding_source=BindingSource.AUTO_RECOMMENDED
            ).values_list("template_id", flat=True)
        )

    def get_manual_bound_template_ids(self, case_id: int) -> set[int]:
        """获取所有手动绑定的模板ID集合"""
        return set(
            CaseTemplateBinding.objects.filter(case_id=case_id, binding_source=BindingSource.MANUAL_BOUND).values_list(
                "template_id", flat=True
            )
        )

    def delete_auto_bindings(self, case_id: int, template_ids: set[int]) -> None:
        """批量删除指定的自动推荐绑定"""
        if not template_ids:
            return
        CaseTemplateBinding.objects.filter(
            case_id=case_id, template_id__in=template_ids, binding_source=BindingSource.AUTO_RECOMMENDED
        ).delete()

    def bulk_create_auto_bindings(self, case_id: int, template_ids: set[int]) -> None:
        """批量创建自动推荐绑定"""
        if not template_ids:
            return
        bindings_to_create = [
            CaseTemplateBinding(case_id=case_id, template_id=template_id, binding_source=BindingSource.AUTO_RECOMMENDED)
            for template_id in template_ids
        ]
        CaseTemplateBinding.objects.bulk_create(bindings_to_create)

    def get_our_legal_statuses(self, case: Case) -> list[str]:
        """
        获取案件中我方当事人的诉讼地位列表
        """
        return list(
            case.parties.filter(client__is_our_client=True)
            .exclude(legal_status__isnull=True)
            .exclude(legal_status="")
            .values_list("legal_status", flat=True)
            .distinct()
        )
