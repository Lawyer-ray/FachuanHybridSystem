"""Tests for cases/services/template/case_template_binding_service.py

Covers: get_bindings_for_case, get_available_templates, bind_template,
unbind_template, sync_auto_recommendations, get_unified_templates,
_match_templates_for_case, document_service property.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.cases.services.template.case_template_binding_service import (
    CaseTemplateBindingService,
)


def _make_svc(
    *,
    document_service: MagicMock | None = None,
    match_policy: MagicMock | None = None,
    assembler: MagicMock | None = None,
    repo: MagicMock | None = None,
) -> tuple[CaseTemplateBindingService, MagicMock, MagicMock, MagicMock, MagicMock]:
    ds = document_service or MagicMock()
    mp = match_policy or MagicMock()
    asm = assembler or MagicMock()
    r = repo or MagicMock()
    svc = CaseTemplateBindingService(
        document_service=ds, match_policy=mp, assembler=asm, repo=r
    )
    return svc, ds, mp, asm, r


class TestDocumentServiceProperty:
    def test_raises_when_not_injected(self):
        svc = CaseTemplateBindingService(document_service=None)
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.document_service

    def test_returns_injected(self):
        ds = MagicMock()
        svc = CaseTemplateBindingService(document_service=ds)
        assert svc.document_service is ds


class TestGetBindingsForCase:
    def test_basic_flow(self):
        svc, ds, mp, asm, r = _make_svc()
        case = SimpleNamespace(case_type="litigation", current_stage="first_instance")
        r.get_case.return_value = case
        r.get_our_legal_statuses.return_value = ["plaintiff"]

        binding = SimpleNamespace(template_id=1, binding_source="manual_bound")
        r.get_bindings_by_case_id.return_value = [binding]

        template = SimpleNamespace(id=1, case_sub_type="sub1", name="T1")
        ds.get_templates_by_ids_internal.return_value = [template]
        ds.list_case_templates_internal.return_value = []

        asm.binding_to_dict.return_value = {"id": 1}
        asm.categories_response.return_value = {"categories": {}, "total_count": 0}

        result = svc.get_bindings_for_case(1)
        asm.categories_response.assert_called_once()
        r.get_case.assert_called_once_with(1)

    def test_uses_case_type_and_stage_from_case(self):
        svc, ds, mp, asm, r = _make_svc()
        case = SimpleNamespace(case_type="criminal", current_stage="second_instance")
        r.get_case.return_value = case
        r.get_our_legal_statuses.return_value = []
        r.get_bindings_by_case_id.return_value = []
        ds.list_case_templates_internal.return_value = []
        mp.filter.return_value = []
        asm.categories_response.return_value = {"categories": {}, "total_count": 0}

        svc.get_bindings_for_case(1)
        # Verify case_type was used (not overridden)
        r.get_case.assert_called_once_with(1)

    def test_with_general_templates(self):
        svc, ds, mp, asm, r = _make_svc()
        case = SimpleNamespace(case_type="litigation", current_stage="first_instance")
        r.get_case.return_value = case
        r.get_our_legal_statuses.return_value = ["plaintiff"]
        r.get_bindings_by_case_id.return_value = []
        ds.list_case_templates_internal.return_value = []

        general_tpl = SimpleNamespace(id=10, case_sub_type="general_sub")
        mp.filter.return_value = [general_tpl]
        asm.general_to_dict.return_value = {"general": True}
        asm.categories_response.return_value = {"categories": {}, "total_count": 0}

        result = svc.get_bindings_for_case(1, case_type="litigation", case_stage="first_instance")
        asm.general_to_dict.assert_called_once_with(template=general_tpl)


class TestGetAvailableTemplates:
    def test_excludes_bound_and_general(self):
        svc, ds, mp, asm, r = _make_svc()
        case = SimpleNamespace(case_type="litigation", current_stage="first_instance")
        r.get_case.return_value = case
        r.get_bound_template_ids.return_value = {1}
        r.get_our_legal_statuses.return_value = []

        general_tpl = SimpleNamespace(id=2)
        mp.filter.return_value = [general_tpl]

        available_tpl = SimpleNamespace(id=3, case_sub_type="sub", name="Avail")
        ds.list_case_templates_internal.return_value = [available_tpl]
        asm.available_to_dict.return_value = {"id": 3}

        result = svc.get_available_templates(1)
        assert len(result) == 1

    def test_no_case_type_skips_general(self):
        svc, ds, mp, asm, r = _make_svc()
        case = SimpleNamespace(case_type=None, current_stage=None)
        r.get_case.return_value = case
        r.get_bound_template_ids.return_value = set()
        r.get_our_legal_statuses.return_value = []

        ds.list_case_templates_internal.return_value = []

        result = svc.get_available_templates(1)
        assert result == []


class TestBindTemplate:
    @pytest.mark.django_db
    def test_template_not_found_raises(self):
        svc, ds, mp, asm, r = _make_svc()
        r.get_case.return_value = SimpleNamespace()
        ds.get_template_by_id_internal.return_value = None

        with pytest.raises(Exception, match="模板不存在"):
            svc.bind_template(1, 999)

    @pytest.mark.django_db
    def test_already_bound_raises(self):
        svc, ds, mp, asm, r = _make_svc()
        r.get_case.return_value = SimpleNamespace()
        ds.get_template_by_id_internal.return_value = SimpleNamespace(id=1, name="T")
        r.exists_binding.return_value = True

        with pytest.raises(Exception, match="绑定关系已存在"):
            svc.bind_template(1, 1)

    @pytest.mark.django_db
    def test_success(self):
        svc, ds, mp, asm, r = _make_svc()
        r.get_case.return_value = SimpleNamespace()
        tpl = SimpleNamespace(id=1, name="T", description="D")
        ds.get_template_by_id_internal.return_value = tpl
        r.exists_binding.return_value = False

        from datetime import datetime

        binding = SimpleNamespace(
            id=100,
            binding_source="manual_bound",
            get_binding_source_display=lambda: "手动绑定",
            created_at=datetime(2024, 1, 1),
        )
        r.create_binding.return_value = binding

        result = svc.bind_template(1, 1)
        assert result["binding_id"] == 100
        assert result["template_id"] == 1
        assert result["name"] == "T"


class TestUnbindTemplate:
    @pytest.mark.django_db
    def test_auto_recommended_raises(self):
        svc, ds, mp, asm, r = _make_svc()
        r.get_case.return_value = SimpleNamespace()
        binding = SimpleNamespace(binding_source="auto_recommended", template_id=1)
        r.get_binding.return_value = binding

        with pytest.raises(Exception, match="自动推荐的模板不能手动移除"):
            svc.unbind_template(1, 100)

    @pytest.mark.django_db
    def test_manual_bound_deletes(self):
        svc, ds, mp, asm, r = _make_svc()
        r.get_case.return_value = SimpleNamespace()
        binding = SimpleNamespace(binding_source="manual_bound", template_id=1)
        r.get_binding.return_value = binding

        svc.unbind_template(1, 100)
        r.delete_binding.assert_called_once_with(binding)


class TestSyncAutoRecommendations:
    @pytest.mark.django_db
    def test_adds_new_removes_old(self):
        svc, ds, mp, asm, r = _make_svc()
        case = SimpleNamespace(case_type="litigation", current_stage="first_instance")
        r.get_case.return_value = case
        r.get_auto_bound_template_ids.return_value = {1, 2}
        r.get_our_legal_statuses.return_value = ["plaintiff"]
        r.get_manual_bound_template_ids.return_value = set()

        ds.list_case_templates_internal.return_value = []
        mp.filter.return_value = [SimpleNamespace(id=2), SimpleNamespace(id=3)]

        svc.sync_auto_recommendations(1)
        r.delete_auto_bindings.assert_called_once_with(1, {1})
        r.bulk_create_auto_bindings.assert_called_once_with(1, {3})

    @pytest.mark.django_db
    def test_no_changes(self):
        svc, ds, mp, asm, r = _make_svc()
        case = SimpleNamespace(case_type="litigation", current_stage="first_instance")
        r.get_case.return_value = case
        r.get_auto_bound_template_ids.return_value = {1}
        r.get_our_legal_statuses.return_value = []
        r.get_manual_bound_template_ids.return_value = set()

        ds.list_case_templates_internal.return_value = []
        mp.filter.return_value = [SimpleNamespace(id=1)]

        svc.sync_auto_recommendations(1)
        r.delete_auto_bindings.assert_not_called()
        r.bulk_create_auto_bindings.assert_not_called()

    @pytest.mark.django_db
    def test_excludes_manual_bound_from_auto(self):
        svc, ds, mp, asm, r = _make_svc()
        case = SimpleNamespace(case_type="litigation", current_stage="first_instance")
        r.get_case.return_value = case
        r.get_auto_bound_template_ids.return_value = set()
        r.get_our_legal_statuses.return_value = []
        r.get_manual_bound_template_ids.return_value = {1}

        ds.list_case_templates_internal.return_value = []
        # Policy returns template 1, but it's manually bound so should be excluded
        mp.filter.return_value = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

        svc.sync_auto_recommendations(1)
        r.bulk_create_auto_bindings.assert_called_once_with(1, {2})


class TestGetUnifiedTemplates:
    def test_basic_flow(self):
        svc, ds, mp, asm, r = _make_svc()
        case = SimpleNamespace(case_type="litigation", current_stage="first_instance")
        r.get_case.return_value = case
        r.get_our_legal_statuses.return_value = ["plaintiff"]

        binding = SimpleNamespace(template_id=1, binding_source="manual_bound", get_binding_source_display=lambda: "手动绑定")
        r.get_bindings_by_case_id.return_value = [binding]

        tpl = SimpleNamespace(id=1, name="T", function_code="fc", description="D")
        ds.get_templates_by_ids_internal.return_value = [tpl]

        general_tpl = SimpleNamespace(id=2, name="General", function_code=None)
        mp.filter.return_value = [general_tpl]

        ds.list_case_templates_internal.return_value = []

        result = svc.get_unified_templates(1)
        assert len(result) == 2
        assert result[0]["template_id"] == 1
        assert result[1]["binding_source"] == "general"

    def test_no_template_for_binding(self):
        svc, ds, mp, asm, r = _make_svc()
        case = SimpleNamespace(case_type="litigation", current_stage="first_instance")
        r.get_case.return_value = case
        r.get_our_legal_statuses.return_value = []

        binding = SimpleNamespace(template_id=1, binding_source="manual_bound", get_binding_source_display=lambda: "手动绑定")
        r.get_bindings_by_case_id.return_value = [binding]
        ds.get_templates_by_ids_internal.return_value = []  # template not found
        mp.filter.return_value = []
        ds.list_case_templates_internal.return_value = []

        result = svc.get_unified_templates(1)
        assert len(result) == 1
        assert result[0]["name"] == ""


class TestMatchTemplatesForCase:
    def test_filters_templates(self):
        svc, ds, mp, asm, r = _make_svc()
        tpl = SimpleNamespace(id=1)
        ds.list_case_templates_internal.return_value = [tpl]
        mp.filter.return_value = [tpl]

        result = svc._match_templates_for_case("litigation", "first_instance", ["plaintiff"])
        assert result == [1]
