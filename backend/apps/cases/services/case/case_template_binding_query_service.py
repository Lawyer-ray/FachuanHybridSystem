"""Business logic services."""

from __future__ import annotations

import logging

from apps.cases.models import CaseTemplateBinding
from apps.core.dtos import CaseTemplateBindingDTO

logger = logging.getLogger("apps.cases")


class CaseTemplateBindingQueryService:
    def get_case_template_binding_internal(self, case_id: int) -> CaseTemplateBindingDTO | None:
        try:
            binding = CaseTemplateBinding.objects.select_related("template").filter(case_id=case_id).first()
            if not binding:
                return None

            return CaseTemplateBindingDTO(
                id=binding.id,
                case_id=binding.case_id,
                template_id=binding.template_id,
                template_name=binding.template.name if binding.template else "",
                template_function_code=None,
                binding_source=binding.binding_source,
                created_at=str(binding.created_at) if binding.created_at else None,
            )
        except Exception:
            logger.exception("get_case_template_binding_internal_failed", extra={"case_id": case_id})
            raise

    def get_case_template_bindings_by_name_internal(
        self, case_id: int, template_name: str
    ) -> list[CaseTemplateBindingDTO]:
        try:
            bindings = CaseTemplateBinding.objects.filter(
                case_id=case_id,
                template__name=template_name,
                template__is_active=True,
            ).select_related("template")

            result: list[CaseTemplateBindingDTO] = []
            for binding in bindings:
                result.append(
                    CaseTemplateBindingDTO(
                        id=binding.id,
                        case_id=binding.case_id,
                        template_id=binding.template_id,
                        template_name=binding.template.name if binding.template else "",
                        template_function_code=None,
                        binding_source=getattr(binding, "binding_source", "manual"),
                        created_at=str(binding.created_at) if binding.created_at else None,
                    )
                )
            return result
        except Exception:
            logger.exception(
                "get_case_template_bindings_by_name_internal_failed",
                extra={"case_id": case_id, "template_name": template_name},
            )
            raise
