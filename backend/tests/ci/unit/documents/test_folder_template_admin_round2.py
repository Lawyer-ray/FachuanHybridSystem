"""Round 2 coverage tests for FolderTemplateAdminService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


def _make_service(**kwargs):
    from apps.documents.services.template.folder_template.admin_service import FolderTemplateAdminService
    svc = FolderTemplateAdminService(folder_template_service=kwargs.get("folder_template_service", MagicMock()))
    return svc


class TestValidateAndFixTemplateForm:
    def test_structure_fix_applied(self):
        svc = _make_service()
        svc.folder_template_service.validate_and_fix_structure_ids.return_value = (
            True, {"fixed": True}, ["修复了重复ID"]
        )
        result = svc.validate_and_fix_template_form({"structure": {"key": "val"}, "id": 1})
        assert result["is_valid"] is True
        assert result["is_fixed"] is True
        assert result["fixed_structure"] == {"fixed": True}
        assert "修复了重复ID" in result["warnings"]

    def test_structure_no_fix_needed(self):
        svc = _make_service()
        svc.folder_template_service.validate_and_fix_structure_ids.return_value = (
            False, {"key": "val"}, []
        )
        result = svc.validate_and_fix_template_form({"structure": {"key": "val"}})
        assert result["is_valid"] is True
        assert result["is_fixed"] is False

    def test_no_structure_key(self):
        svc = _make_service()
        result = svc.validate_and_fix_template_form({})
        assert result["is_valid"] is True

    def test_exception_during_fix(self):
        svc = _make_service()
        svc.folder_template_service.validate_and_fix_structure_ids.side_effect = Exception("boom")
        result = svc.validate_and_fix_template_form({"structure": {"k": "v"}, "id": 1})
        assert result["is_valid"] is False
        assert len(result["errors"]) == 1
        assert "boom" in result["errors"][0]


class TestValidateTemplateForm:
    def test_valid_structure(self):
        svc = _make_service()
        svc.folder_template_service.validate_structure_ids.return_value = (True, [])
        result = svc.validate_template_form({"structure": {"k": "v"}})
        assert result["is_valid"] is True

    def test_invalid_structure(self):
        svc = _make_service()
        svc.folder_template_service.validate_structure_ids.return_value = (False, ["错误1"])
        result = svc.validate_template_form({"structure": {"k": "v"}, "id": 1})
        assert result["is_valid"] is False
        assert "错误1" in result["errors"]

    def test_exception_in_validation(self):
        svc = _make_service()
        svc.folder_template_service.validate_structure_ids.side_effect = Exception("val_err")
        result = svc.validate_template_form({"structure": {"k": "v"}})
        assert result["is_valid"] is False
        assert "val_err" in result["errors"][0]


class TestValidateStructureIds:
    def test_no_structure(self):
        svc = _make_service()
        result = svc.validate_structure_ids(structure=None)
        assert result["success"] is False
        assert "缺少结构数据" in result["message"]

    def test_empty_structure(self):
        svc = _make_service()
        result = svc.validate_structure_ids(structure={})
        assert result["success"] is False

    def test_valid_structure(self):
        svc = _make_service()
        svc.folder_template_service.validate_structure_ids.return_value = (True, [])
        result = svc.validate_structure_ids(structure={"key": "val"})
        assert result["success"] is True
        assert result["is_valid"] is True

    def test_invalid_structure(self):
        svc = _make_service()
        svc.folder_template_service.validate_structure_ids.return_value = (False, ["err"])
        result = svc.validate_structure_ids(structure={"k": "v"}, template_id=5)
        assert result["success"] is True
        assert result["is_valid"] is False
        assert "err" in result["errors"]

    def test_exception(self):
        svc = _make_service()
        svc.folder_template_service.validate_structure_ids.side_effect = Exception("boom")
        result = svc.validate_structure_ids(structure={"k": "v"})
        assert result["success"] is False
        assert "boom" in result["message"]


class TestGetDuplicateReport:
    def test_success(self):
        svc = _make_service()
        svc.folder_template_service.get_duplicate_id_report.return_value = {"dupes": []}
        result = svc.get_duplicate_report()
        assert result["success"] is True
        assert "report" in result

    def test_exception(self):
        svc = _make_service()
        svc.folder_template_service.get_duplicate_id_report.side_effect = Exception("err")
        result = svc.get_duplicate_report()
        assert result["success"] is False
        assert "err" in result["error"]


class TestPrepareSaveData:
    def test_contract_type(self):
        svc = _make_service()
        result = svc.prepare_save_data(
            template_type="contract",
            contract_types_field=["租赁合同"],
            case_types_field=[],
            case_stage_field="",
        )
        assert result["contract_types"] == ["租赁合同"]
        assert result["legal_statuses"] == []

    def test_case_type(self):
        svc = _make_service()
        result = svc.prepare_save_data(
            template_type="case",
            contract_types_field=[],
            case_types_field=["民事"],
            case_stage_field="一审",
            legal_statuses_field=["原告"],
            legal_status_match_mode="all",
        )
        assert result["case_types"] == ["民事"]
        assert result["case_stages"] == ["一审"]
        assert result["legal_statuses"] == ["原告"]
        assert result["legal_status_match_mode"] == "all"

    def test_case_type_no_stage(self):
        svc = _make_service()
        result = svc.prepare_save_data(
            template_type="case",
            contract_types_field=[],
            case_types_field=[],
            case_stage_field="",
        )
        assert result["case_stages"] == []

    def test_unknown_type_fallback(self):
        svc = _make_service()
        result = svc.prepare_save_data(
            template_type="unknown",
            contract_types_field=["c1"],
            case_types_field=["ca1"],
            case_stage_field="stage1",
            legal_statuses_field=["ls1"],
            legal_status_match_mode="any",
        )
        assert result["contract_types"] == ["c1"]
        assert result["case_types"] == ["ca1"]

    def test_contract_type_clears_legal_statuses(self):
        svc = _make_service()
        result = svc.prepare_save_data(
            template_type="contract",
            contract_types_field=[],
            case_types_field=[],
            case_stage_field="",
            legal_statuses_field=["原告"],
        )
        assert result["legal_statuses"] == []


class TestRenderStructureTree:
    def test_empty_structure(self):
        svc = _make_service()
        assert svc.render_structure_tree({}) == ""

    def test_no_children(self):
        svc = _make_service()
        assert svc.render_structure_tree({"name": "root"}) == ""

    def test_single_child(self):
        svc = _make_service()
        result = svc.render_structure_tree({"children": [{"name": "sub1"}]})
        assert "sub1" in result
        assert "font-family" in result

    def test_nested_children(self):
        svc = _make_service()
        structure = {
            "children": [
                {
                    "name": "parent",
                    "children": [{"name": "child1"}],
                }
            ]
        }
        result = svc.render_structure_tree(structure)
        assert "parent" in result
        assert "child1" in result

    def test_multiple_children_prefixes(self):
        svc = _make_service()
        structure = {
            "children": [
                {"name": "first"},
                {"name": "last"},
            ]
        }
        result = svc.render_structure_tree(structure)
        assert "first" in result
        assert "last" in result

    def test_level_zero_prefix(self):
        svc = _make_service()
        structure = {"children": [{"name": "a"}, {"name": "b"}]}
        result = svc.render_structure_tree(structure, level=0)
        assert "📁" in result

    def test_level_nonzero_prefix(self):
        svc = _make_service()
        structure = {"children": [{"name": "a"}]}
        result = svc.render_structure_tree(structure, level=1)
        assert "└──" in result

    def test_default_name_for_missing(self):
        svc = _make_service()
        structure = {"children": [{}]}
        result = svc.render_structure_tree(structure)
        assert "未命名" in result


class TestRenderStructurePreview:
    def test_returns_mark_safe(self):
        svc = _make_service()
        result = svc.render_structure_preview({"children": [{"name": "a"}]})
        assert "folder-structure-preview" in str(result)


class TestGetStructureJson:
    def test_found(self):
        svc = _make_service()
        mock_tpl = MagicMock()
        mock_tpl.structure = {"k": "v"}
        mock_tpl.name = "模板"
        with patch("apps.documents.services.template.folder_template.admin_service.FolderTemplate") as mock_model:
            mock_model.objects.get.return_value = mock_tpl
            result = svc.get_structure_json(pk=1)
        assert result["success"] is True
        assert result["structure"] == {"k": "v"}

    def test_not_found(self):
        svc = _make_service()
        from apps.core.exceptions import NotFoundError
        from apps.documents.models import FolderTemplate
        with patch.object(FolderTemplate, "objects") as mock_objects:
            mock_objects.get.side_effect = FolderTemplate.DoesNotExist
            with pytest.raises(NotFoundError):
                svc.get_structure_json(pk=999)


class TestGetFolderTemplateByPk:
    def test_found(self):
        svc = _make_service()
        mock_tpl = MagicMock()
        with patch("apps.documents.services.template.folder_template.admin_service.FolderTemplate") as mock_model:
            mock_model.objects.get.return_value = mock_tpl
            result = svc.get_folder_template_by_pk(1)
        assert result is mock_tpl

    def test_not_found(self):
        svc = _make_service()
        from apps.core.exceptions import NotFoundError
        from apps.documents.models import FolderTemplate
        with patch.object(FolderTemplate, "objects") as mock_objects:
            mock_objects.get.side_effect = FolderTemplate.DoesNotExist
            with pytest.raises(NotFoundError):
                svc.get_folder_template_by_pk(999)


class TestBatchActivate:
    def test_activates_inactive(self):
        svc = _make_service()
        mock_qs = MagicMock()
        mock_qs.filter.return_value.update.return_value = 3
        result = svc.batch_activate(mock_qs)
        assert result == 3


class TestBatchDeactivate:
    def test_deactivates_active(self):
        svc = _make_service()
        mock_qs = MagicMock()
        mock_qs.filter.return_value.update.return_value = 2
        result = svc.batch_deactivate(mock_qs)
        assert result == 2


class TestBatchDuplicateTemplates:
    def test_duplicates_each(self):
        svc = _make_service()
        svc.duplicate_template = MagicMock()
        templates = [MagicMock(), MagicMock()]
        result = svc.batch_duplicate_templates(templates)
        assert result == 2
        assert svc.duplicate_template.call_count == 2
