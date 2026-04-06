"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any, cast

from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from apps.core.infrastructure import CacheKeys, CacheTimeout
from apps.documents.models.choices import (
    DocumentCaseStage,
    DocumentTemplateType,
    FolderTemplateType,
    LegalStatusMatchMode,
)
from apps.documents.models.document_template import DocumentTemplate
from apps.documents.models.folder_template import FolderTemplate

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
            templates = DocumentTemplate.objects.filter(template_type=DocumentTemplateType.CASE, is_active=True)
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
            templates = FolderTemplate.objects.filter(template_type=FolderTemplateType.CASE, is_active=True)
            case_legal_statuses_set = set(legal_statuses or [])
            return [
                t.name for t in templates if self._matches_case_folder_template(t, case_type, case_legal_statuses_set)
            ]
        except Exception:
            logger.exception("获取文件夹模板失败", extra={"case_type": case_type, "legal_statuses": legal_statuses})
            raise

    def find_matching_case_folder_templates_list(
        self, case_type: str, legal_statuses: list[str] | None = None
    ) -> list[dict[str, Any]]:
        templates = FolderTemplate.objects.filter(template_type=FolderTemplateType.CASE, is_active=True)
        case_legal_statuses_set = set(legal_statuses or [])
        return [
            {"id": t.id, "name": t.name}
            for t in templates
            if self._matches_case_folder_template(t, case_type, case_legal_statuses_set)
        ]

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
            from apps.documents.services.template.contract_template.query_service import ContractTemplateQueryService

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
                type_list = (
                    template.contract_types if template_type == FolderTemplateType.CONTRACT else template.case_types
                )
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

        folder_templates = self.find_matching_folder_templates(FolderTemplateType.CONTRACT, case_type)
        document_templates = self.find_matching_contract_templates(case_type)
        return cast(dict[str, bool], {"has_folder": bool(folder_templates), "has_document": bool(document_templates)})

    def find_matching_case_file_templates(
        self,
        case_type: str,
        case_stage: str,
        applicable_institutions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        version = self._get_document_templates_cache_version()
        normalized_institutions = self._normalize_institutions(applicable_institutions)
        institutions_cache_key = "|".join(normalized_institutions)
        cache_key = CacheKeys.documents_matching_case_file_templates(
            case_type=case_type,
            case_stage=case_stage,
            institutions=institutions_cache_key,
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

            templates = DocumentTemplate.objects.filter(template_type=DocumentTemplateType.CASE, is_active=True)

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

                if not self._matches_template_institutions(template, normalized_institutions):
                    continue

                matched.append(
                    {
                        "id": template.id,
                        "name": template.name,
                        "type_display": template.template_type_display,
                        "case_types_display": template.case_types_display,
                        "case_stages_display": template.case_stages_display,
                        "case_sub_type": template.case_sub_type or "other_materials",
                    }
                )

            cache.set(cache_key, matched, CacheTimeout.get_long())
            return matched
        except Exception:
            logger.exception(
                "find_matching_case_file_templates_failed", extra={"case_type": case_type, "case_stage": case_stage}
            )
            raise

    def _normalize_institutions(self, names: list[str] | None) -> list[str]:
        if not names:
            return []
        seen: set[str] = set()
        normalized: list[str] = []
        for name in names:
            text = str(name or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    def _matches_template_institutions(self, template: DocumentTemplate, case_institutions: list[str]) -> bool:
        template_names = self._normalize_institutions(cast(list[str] | None, template.applicable_institutions))

        # 兼容历史模板：若未配置适用机构，但模板名称带有地域标识，则按地域限制
        if not template_names:
            if "广州" in str(template.name or ""):
                template_names = ["广州", "广州市"]
            else:
                return True

        if not case_institutions:
            return False
        return any(
            (case_name == template_name)
            or (template_name in case_name)
            or (case_name in template_name)
            for case_name in case_institutions
            for template_name in template_names
        )

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
