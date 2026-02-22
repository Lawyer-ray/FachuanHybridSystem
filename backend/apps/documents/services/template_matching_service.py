"""Business logic services."""

from __future__ import annotations

from apps.documents.models.choices import LegalStatusMatchMode, DocumentCaseStage
from django.utils.translation import gettext_lazy as _

import logging
from typing import Any, cast

from django.core.cache import cache

from apps.core.infrastructure import CacheKeys, CacheTimeout

logger = logging.getLogger(__name__)


class TemplateMatchingService:
    _MISSING_SENTINEL = "__documents_template_matching_missing__"

    def _get_document_templates_cache_version(self) -> int:
        version_key = CacheKeys.documents_matching_version_document_templates()
        cache.add(version_key, 1, timeout=CacheTimeout.get_day())
        return int(cache.get(version_key) or 1)

    def _get_folder_templates_cache_version(self) -> int:
        version_key = CacheKeys.documents_matching_version_folder_templates()
        cache.add(version_key, 1, timeout=CacheTimeout.get_day())
        return int(cache.get(version_key) or 1)

    def find_matching_case_document_template_names(self, case_type: str) -> list[str]:
        try:

            templates = DocumentTemplate.objects.filter(template_type="case", is_active=True)
            matched: list[str] = []
            for template in templates:
                case_types = template.case_types or []
                if not case_types or LegalStatusMatchMode.ALL in case_types or case_type in case_types:
                    matched.append(template.name)
            return matched
        except Exception:
            logger.exception("获取文书模板失败", extra={"case_type": case_type})
            raise

    def find_matching_case_folder_template_names_with_legal_status(
        self, case_type: str, legal_statuses: list[str] | None = None
    ) -> list[str]:
        try:

            templates = FolderTemplate.objects.filter(template_type="case", is_active=True)
            case_legal_statuses_set = set(legal_statuses or [])
            return [
                t.name for t in templates if self._matches_case_folder_template(t, case_type, case_legal_statuses_set)
            ]
        except Exception:
            logger.exception("获取文件夹模板失败", extra={"case_type": case_type, "legal_statuses": legal_statuses})
            raise

    def _matches_case_folder_template(self, template: Any, case_type: str, case_legal_statuses_set: set[Any]) -> bool:
        case_types = template.case_types or []
        if case_types and LegalStatusMatchMode.ALL not in case_types and case_type not in case_types:
            return False

        template_legal_statuses = template.legal_statuses or []
        if not template_legal_statuses:
            return True

        match_mode = template.legal_status_match_mode or LegalStatusMatchMode.ANY
        tls = set(template_legal_statuses)
        if match_mode == LegalStatusMatchMode.ANY:
            return not case_legal_statuses_set or bool(case_legal_statuses_set & tls)
        if match_mode == LegalStatusMatchMode.ALL:
            return tls <= case_legal_statuses_set
        if match_mode == "exact":
            return case_legal_statuses_set == tls
        return False

    def find_matching_contract_templates(self, case_type: str) -> list[dict[str, Any]]:
        version = self._get_document_templates_cache_version()
        cache_key = CacheKeys.documents_matching_contract_templates(case_type=case_type, version=version)
        cached = cache.get(cache_key)
        if cached is not None:
            if cached == self._MISSING_SENTINEL:
                return []
            return cast(list[dict[str, Any]], cached)
        try:
            from apps.documents.services.contract_template_query_service import ContractTemplateQueryService

            if not case_type:
                raise ValidationException(message=_("案件类型不能为空"), code="INVALID_CASE_TYPE")

            result = ContractTemplateQueryService().list_matching_template_summaries(case_type)
            cache.set(cache_key, result, CacheTimeout.get_long())
            return result
        except Exception:
            logger.exception("查找合同模板失败", extra={"case_type": case_type})
            raise

    def find_matching_folder_templates(self, template_type: str, case_type: str | None = None) -> list[dict[str, Any]]:
        version = self._get_folder_templates_cache_version()
        cache_key = CacheKeys.documents_matching_folder_templates(
            template_type=template_type,
            case_type=case_type or "",
            version=version,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            if cached == self._MISSING_SENTINEL:
                return []
            return cast(list[dict[str, Any]], cached)
        try:

            if not template_type:
                raise ValidationException(message=_("模板类型不能为空"), code="INVALID_TEMPLATE_TYPE")

            templates = FolderTemplate.objects.filter(template_type=template_type, is_active=True)

            matched: list[dict[str, Any]] = []
            for template in templates:
                type_list = template.contract_types if template_type == FolderTemplateType.CONTRACT else template.case_types
                type_list = type_list or []
                if not type_list or LegalStatusMatchMode.ALL in type_list or (case_type and case_type in type_list):
                    matched.append({"id": template.id, "name": template.name})
            cache.set(cache_key, matched, CacheTimeout.get_long())
            return matched
        except Exception:
            logger.exception("查找文件夹模板失败", extra={"template_type": template_type, "case_type": case_type})
            raise

    def check_has_matching_templates(self, case_type: str) -> dict[str, bool]:

        if not case_type:
            raise ValidationException(message=_("案件类型不能为空"), code="INVALID_CASE_TYPE")

        folder_templates = self.find_matching_folder_templates("contract", case_type)
        document_templates = self.find_matching_contract_templates(case_type)
        return cast(
            dict[str, bool], {"has_folder": len(folder_templates) > 0, "has_document": len(document_templates) > 0}
        )

    def find_matching_case_file_templates(self, case_type: str, case_stage: str) -> list[dict[str, Any]]:
        version = self._get_document_templates_cache_version()
        cache_key = CacheKeys.documents_matching_case_file_templates(
            case_type=case_type,
            case_stage=case_stage,
            version=version,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            if cached == self._MISSING_SENTINEL:
                return []
            return cast(list[dict[str, Any]], cached)
        try:

            if not case_type or not case_stage:
                return []

            normalized_stages = self._normalize_case_stage_for_document(case_stage)
            if not normalized_stages:
                return []

            templates = DocumentTemplate.objects.filter(template_type="case", is_active=True)

            matched: list[dict[str, Any]] = []
            for template in templates:
                template_case_types = template.case_types or []
                if LegalStatusMatchMode.ALL not in template_case_types and case_type not in template_case_types:
                    continue

                template_case_stages = template.case_stages or []
                if LegalStatusMatchMode.ALL not in template_case_stages and not any(
                    stage in template_case_stages for stage in normalized_stages
                ):
                    continue

                matched.append(
                    {
                        "id": template.id,
                        "name": template.name,
                        "type_display": template.template_type_display,
                        "case_types_display": template.case_types_display,
                        "case_stages_display": template.case_stages_display,
                    }
                )

            cache.set(cache_key, matched, CacheTimeout.get_long())
            return matched
        except Exception:
            logger.exception(
                "find_matching_case_file_templates_failed", extra={"case_type": case_type, "case_stage": case_stage}
            )
            raise

    def _normalize_case_stage_for_document(self, case_stage: str) -> list[str]:
        if not case_stage:
            return []

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
            return [DocumentCaseStage.RETRIAL]
        return [case_stage]
