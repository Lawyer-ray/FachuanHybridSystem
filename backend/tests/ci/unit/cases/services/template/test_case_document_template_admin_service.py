"""Tests for cases/services/template/case_document_template_admin_service.py

Covers: get_matched_templates_for_case, get_available_templates_for_binding,
get_templates_display_data, _match_legal_status, _normalize_case_stage.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.template.case_document_template_admin_service import (
    CaseDocumentTemplateAdminService,
)


def _make_template(
    *,
    id: int = 1,
    name: str = "tpl",
    description: str = "",
    case_types: list[str] | None = None,
    case_stages: list[str] | None = None,
    legal_statuses: list[str] | None = None,
    legal_status_match_mode: str = "any",
    case_sub_type: str | None = None,
    function_code: str | None = None,
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        name=name,
        description=description,
        case_types=case_types or [],
        case_stages=case_stages or [],
        legal_statuses=legal_statuses or [],
        legal_status_match_mode=legal_status_match_mode,
        case_sub_type=case_sub_type,
        function_code=function_code,
        is_active=is_active,
    )


class TestMatchLegalStatus:
    def setup_method(self):
        self.svc = CaseDocumentTemplateAdminService()

    def test_empty_template_statuses_matches_any(self):
        assert self.svc._match_legal_status([], {"plaintiff"}, "any") is True

    def test_any_mode_intersection(self):
        assert self.svc._match_legal_status(["plaintiff", "defendant"], {"plaintiff"}, "any") is True

    def test_any_mode_no_intersection(self):
        assert self.svc._match_legal_status(["defendant"], {"plaintiff"}, "any") is False

    def test_any_mode_empty_case_statuses(self):
        assert self.svc._match_legal_status(["plaintiff"], set(), "any") is True

    def test_all_mode_subset(self):
        assert self.svc._match_legal_status(["plaintiff", "defendant"], {"plaintiff", "defendant", "third_party"}, "all") is True

    def test_all_mode_not_subset(self):
        assert self.svc._match_legal_status(["plaintiff", "third_party"], {"plaintiff", "defendant"}, "all") is False

    def test_exact_mode_match(self):
        assert self.svc._match_legal_status(["a", "b"], {"a", "b"}, "exact") is True

    def test_exact_mode_mismatch(self):
        assert self.svc._match_legal_status(["a", "b"], {"a", "b", "c"}, "exact") is False

    def test_unknown_mode_defaults_to_any(self):
        assert self.svc._match_legal_status(["x"], {"x"}, "unknown_mode") is True

    def test_unknown_mode_empty_case_statuses(self):
        assert self.svc._match_legal_status(["x"], set(), "unknown_mode") is True


class TestNormalizeCaseStage:
    def setup_method(self):
        self.svc = CaseDocumentTemplateAdminService()

    def test_empty_stage(self):
        assert self.svc._normalize_case_stage("") == []

    def test_normal_stage(self):
        assert self.svc._normalize_case_stage("first_instance") == ["first_instance"]

    def test_retrial_stage(self):
        result = self.svc._normalize_case_stage("retrial_first")
        assert "retrial" in result
        assert "retrial_first" in result

    def test_apply_retrial(self):
        result = self.svc._normalize_case_stage("apply_retrial")
        assert "retrial" in result

    def test_review_stage(self):
        result = self.svc._normalize_case_stage("review")
        assert "retrial" in result
        assert "review" in result

    def test_petition_stage(self):
        result = self.svc._normalize_case_stage("petition")
        assert "retrial" in result


class TestGetMatchedTemplatesForCase:
    def setup_method(self):
        self.doc_svc = MagicMock()
        self.svc = CaseDocumentTemplateAdminService(document_service=self.doc_svc)

    def test_empty_case_type_returns_empty(self):
        result = self.svc.get_matched_templates_for_case(1, "", "first_instance", ["plaintiff"])
        assert result == []

    def test_case_type_match(self):
        tpl = _make_template(id=1, case_types=["litigation"], case_sub_type="sub1")
        self.doc_svc.list_case_templates_internal.return_value = [tpl]
        result = self.svc.get_matched_templates_for_case(1, "litigation", "first_instance", [])
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_case_type_all_matches_any(self):
        tpl = _make_template(id=1, case_types=["all"])
        self.doc_svc.list_case_templates_internal.return_value = [tpl]
        result = self.svc.get_matched_templates_for_case(1, "litigation", "first_instance", [])
        assert len(result) == 1

    def test_case_type_mismatch_excludes(self):
        tpl = _make_template(id=1, case_types=["criminal"])
        self.doc_svc.list_case_templates_internal.return_value = [tpl]
        result = self.svc.get_matched_templates_for_case(1, "litigation", "first_instance", [])
        assert len(result) == 0

    def test_case_stages_mismatch_excludes(self):
        tpl = _make_template(id=1, case_types=["litigation"], case_stages=["second_instance"])
        self.doc_svc.list_case_templates_internal.return_value = [tpl]
        result = self.svc.get_matched_templates_for_case(1, "litigation", "first_instance", [])
        assert len(result) == 0

    def test_case_stages_all_matches(self):
        tpl = _make_template(id=1, case_types=["litigation"], case_stages=["all"])
        self.doc_svc.list_case_templates_internal.return_value = [tpl]
        result = self.svc.get_matched_templates_for_case(1, "litigation", "first_instance", [])
        assert len(result) == 1

    def test_retrial_stage_normalization(self):
        tpl = _make_template(id=1, case_types=["litigation"], case_stages=["retrial"])
        self.doc_svc.list_case_templates_internal.return_value = [tpl]
        result = self.svc.get_matched_templates_for_case(1, "litigation", "retrial_first", [])
        assert len(result) == 1

    def test_empty_case_stages_matches_all(self):
        tpl = _make_template(id=1, case_types=["litigation"], case_stages=[])
        self.doc_svc.list_case_templates_internal.return_value = [tpl]
        result = self.svc.get_matched_templates_for_case(1, "litigation", "first_instance", [])
        assert len(result) == 1

    def test_legal_status_mismatch_excludes(self):
        tpl = _make_template(
            id=1,
            case_types=["litigation"],
            legal_statuses=["defendant"],
            legal_status_match_mode="all",
        )
        self.doc_svc.list_case_templates_internal.return_value = [tpl]
        result = self.svc.get_matched_templates_for_case(1, "litigation", "first_instance", ["plaintiff"])
        assert len(result) == 0

    def test_result_includes_function_code(self):
        tpl = _make_template(id=1, case_types=["litigation"], function_code="preservation_application")
        self.doc_svc.list_case_templates_internal.return_value = [tpl]
        result = self.svc.get_matched_templates_for_case(1, "litigation", "first_instance", [])
        assert result[0]["function_code"] == "preservation_application"


class TestGetAvailableTemplatesForBinding:
    def setup_method(self):
        self.doc_svc = MagicMock()
        self.svc = CaseDocumentTemplateAdminService(document_service=self.doc_svc)

    def test_excludes_ids(self):
        t1 = _make_template(id=1, name="A", case_sub_type="sub")
        t2 = _make_template(id=2, name="B", case_sub_type="sub")
        self.doc_svc.list_case_templates_internal.return_value = [t1, t2]
        result = self.svc.get_available_templates_for_binding(1, exclude_template_ids={1})
        assert len(result) == 1
        assert result[0]["template_id"] == 2

    def test_sorts_by_sub_type_then_name(self):
        t1 = _make_template(id=1, name="B", case_sub_type="z_sub")
        t2 = _make_template(id=2, name="A", case_sub_type="a_sub")
        self.doc_svc.list_case_templates_internal.return_value = [t1, t2]
        result = self.svc.get_available_templates_for_binding(1, exclude_template_ids=set())
        assert result[0]["template_id"] == 2
        assert result[1]["template_id"] == 1

    def test_empty_templates(self):
        self.doc_svc.list_case_templates_internal.return_value = []
        result = self.svc.get_available_templates_for_binding(1, exclude_template_ids=set())
        assert result == []


class TestGetTemplatesDisplayData:
    def setup_method(self):
        self.doc_svc = MagicMock()
        self.repo = MagicMock()
        self.svc = CaseDocumentTemplateAdminService(document_service=self.doc_svc, repo=self.repo)

    def test_case_not_found_raises(self):
        self.repo.get_case_optional.return_value = None
        with pytest.raises(Exception, match="案件不存在"):
            self.svc.get_templates_display_data(999)

    def test_full_flow(self):
        case = SimpleNamespace(
            case_type="litigation",
            current_stage="first_instance",
        )
        self.repo.get_case_optional.return_value = case
        self.repo.get_our_legal_statuses.return_value = ["plaintiff"]

        tpl = _make_template(id=1, case_types=["litigation"], case_sub_type="sub")
        self.doc_svc.list_case_templates_internal.return_value = [tpl]

        binding_tpl = SimpleNamespace(
            id=10,
            name="手动模板",
            description="desc",
            case_sub_type="sub2",
            function_code=None,
        )
        binding = SimpleNamespace(
            id=100,
            template_id=10,
            binding_source="manual_bound",
            template=binding_tpl,
            created_at=None,
        )
        self.repo.get_bindings_by_case_id.return_value = [binding]

        # Mock get_template_by_id_internal for the binding template lookup
        self.doc_svc.get_templates_by_ids_internal.return_value = [binding_tpl]

        result = self.svc.get_templates_display_data(1)
        assert "auto_matched" in result
        assert "manual_bound" in result
        assert "available_for_binding" in result
        assert "total_count" in result
        assert len(result["manual_bound"]) == 1
