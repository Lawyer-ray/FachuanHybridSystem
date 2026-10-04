"""template_matching_service.py 第二轮补覆盖测试。

聚焦非 pragma 方法：案件文件夹模板匹配（含诉讼地位匹配模式）、
check_has_matching_templates、机构归一化与匹配、案件阶段归一化、async 包装。
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.documents.models.choices import DocumentCaseStage, LegalStatusMatchMode
from apps.documents.services.template.template_matching_service import TemplateMatchingService

SVC_PATH = "apps.documents.services.template.template_matching_service"


def _folder_template(name: str, *, case_types=None, legal_statuses=None, match_mode=None) -> MagicMock:
    tpl = MagicMock()
    tpl.name = name
    tpl.case_types = case_types
    tpl.legal_statuses = legal_statuses
    tpl.legal_status_match_mode = match_mode
    return tpl


class TestFindMatchingCaseDocumentTemplateNamesError:
    @patch(f"{SVC_PATH}.DocumentTemplate")
    def test_orm_error_reraised(self, mock_model):
        mock_model.objects.filter.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError, match="db down"):
            TemplateMatchingService().find_matching_case_document_template_names("civil")


class TestFindMatchingCaseFolderTemplateNames:
    @patch(f"{SVC_PATH}.FolderTemplate")
    def test_returns_matched_names(self, mock_model):
        matched = _folder_template("民商事文件夹", case_types=["civil"])
        unmatched = _folder_template("刑事文件夹", case_types=["criminal"])
        mock_model.objects.filter.return_value = [matched, unmatched]

        result = TemplateMatchingService().find_matching_case_folder_template_names_with_legal_status(
            "civil", legal_statuses=["plaintiff"]
        )
        assert result == ["民商事文件夹"]

    @patch(f"{SVC_PATH}.FolderTemplate")
    def test_error_reraised(self, mock_model):
        mock_model.objects.filter.side_effect = ValueError("boom")
        with pytest.raises(ValueError, match="boom"):
            TemplateMatchingService().find_matching_case_folder_template_names_with_legal_status("civil")

    @patch(f"{SVC_PATH}.FolderTemplate")
    def test_list_variant_returns_id_and_name(self, mock_model):
        matched = _folder_template("文件夹A", case_types=["civil"])
        matched.id = 7
        unmatched = _folder_template("文件夹B", case_types=None)
        unmatched.id = 8
        # case_types=None 视为空列表 -> 匹配任意案件类型，二者都应命中
        mock_model.objects.filter.return_value = [matched, unmatched]

        result = TemplateMatchingService().find_matching_case_folder_templates_list("civil")
        assert {"id": 7, "name": "文件夹A"} in result
        assert {"id": 8, "name": "文件夹B"} in result

    @patch(f"{SVC_PATH}.FolderTemplate")
    def test_list_variant_filters_by_legal_status(self, mock_model):
        tpl = _folder_template("文件夹A", case_types=["civil"], legal_statuses=["defendant"])
        tpl.id = 7
        mock_model.objects.filter.return_value = [tpl]

        result = TemplateMatchingService().find_matching_case_folder_templates_list("civil", ["plaintiff"])
        assert result == []


class TestMatchesCaseFolderTemplate:
    def setup_method(self):
        self.svc = TemplateMatchingService()

    def test_case_type_mismatch_returns_false(self):
        tpl = _folder_template("t", case_types=["criminal"])
        assert self.svc._matches_case_folder_template(tpl, "civil", set()) is False

    def test_all_match_mode_matches_any_case_type(self):
        tpl = _folder_template("t", case_types=[LegalStatusMatchMode.ALL])
        assert self.svc._matches_case_folder_template(tpl, "civil", set()) is True

    def test_empty_legal_statuses_matches(self):
        tpl = _folder_template("t", case_types=["civil"], legal_statuses=[])
        assert self.svc._matches_case_folder_template(tpl, "civil", {"defendant"}) is True

    def test_any_mode_with_empty_case_set_matches(self):
        tpl = _folder_template("t", case_types=["civil"], legal_statuses=["plaintiff"], match_mode="any")
        assert self.svc._matches_case_folder_template(tpl, "civil", set()) is True

    def test_any_mode_intersection_matches(self):
        tpl = _folder_template("t", case_types=["civil"], legal_statuses=["plaintiff", "defendant"], match_mode="any")
        assert self.svc._matches_case_folder_template(tpl, "civil", {"defendant"}) is True

    def test_any_mode_no_intersection_returns_false(self):
        tpl = _folder_template("t", case_types=["civil"], legal_statuses=["plaintiff"], match_mode="any")
        assert self.svc._matches_case_folder_template(tpl, "civil", {"defendant"}) is False

    def test_all_mode_subset_matches(self):
        tpl = _folder_template("t", case_types=["civil"], legal_statuses=["plaintiff"], match_mode="all")
        assert self.svc._matches_case_folder_template(tpl, "civil", {"plaintiff", "defendant"}) is True

    def test_all_mode_not_subset_returns_false(self):
        tpl = _folder_template("t", case_types=["civil"], legal_statuses=["plaintiff", "defendant"], match_mode="all")
        assert self.svc._matches_case_folder_template(tpl, "civil", {"plaintiff"}) is False

    def test_exact_mode_equal_matches(self):
        tpl = _folder_template("t", case_types=["civil"], legal_statuses=["plaintiff"], match_mode="exact")
        assert self.svc._matches_case_folder_template(tpl, "civil", {"plaintiff"}) is True

    def test_exact_mode_unequal_returns_false(self):
        tpl = _folder_template("t", case_types=["civil"], legal_statuses=["plaintiff"], match_mode="exact")
        assert self.svc._matches_case_folder_template(tpl, "civil", {"plaintiff", "defendant"}) is False

    def test_unknown_mode_returns_false(self):
        tpl = _folder_template("t", case_types=["civil"], legal_statuses=["plaintiff"], match_mode="weird")
        assert self.svc._matches_case_folder_template(tpl, "civil", {"plaintiff"}) is False


class TestCheckHasMatchingTemplates:
    def test_empty_case_type_raises(self):
        with pytest.raises(ValidationException):
            TemplateMatchingService().check_has_matching_templates("")

    @patch.object(TemplateMatchingService, "find_matching_folder_templates")
    @patch.object(TemplateMatchingService, "find_matching_contract_templates")
    def test_both_present(self, mock_docs, mock_folders):
        mock_folders.return_value = [{"id": 1, "name": "f"}]
        mock_docs.return_value = [{"id": 2, "name": "d"}]
        result = TemplateMatchingService().check_has_matching_templates("civil")
        assert result == {"has_folder": True, "has_document": True}

    @patch.object(TemplateMatchingService, "find_matching_folder_templates")
    @patch.object(TemplateMatchingService, "find_matching_contract_templates")
    def test_both_missing(self, mock_docs, mock_folders):
        mock_folders.return_value = []
        mock_docs.return_value = []
        result = TemplateMatchingService().check_has_matching_templates("civil")
        assert result == {"has_folder": False, "has_document": False}


class TestNormalizeInstitutions:
    def setup_method(self):
        self.svc = TemplateMatchingService()

    def test_none_returns_empty(self):
        assert self.svc._normalize_institutions(None) == []

    def test_empty_returns_empty(self):
        assert self.svc._normalize_institutions([]) == []

    def test_strips_and_dedupes(self):
        assert self.svc._normalize_institutions([" 广州中院 ", "广州中院", "北京高院"]) == ["广州中院", "北京高院"]

    def test_skips_blank_and_none(self):
        assert self.svc._normalize_institutions(["  ", None]) == []

    def test_non_string_coerced(self):
        assert self.svc._normalize_institutions(["广州市", "广州市"]) == ["广州市"]


class TestMatchesTemplateInstitutions:
    def setup_method(self):
        self.svc = TemplateMatchingService()

    def _template(self, name: str, applicable_institutions) -> MagicMock:
        tpl = MagicMock()
        tpl.name = name
        tpl.applicable_institutions = applicable_institutions
        return tpl

    def test_no_institutions_no_region_marker_matches(self):
        tpl = self._template("通用模板", [])
        assert self.svc._matches_template_institutions(tpl, []) is True

    def test_no_institutions_guangzhou_name_restricted(self):
        tpl = self._template("广州专用模板", [])
        # 无适用机构配置但名称带「广州」→ 按地域限制；空案件机构不匹配
        assert self.svc._matches_template_institutions(tpl, []) is False

    def test_guangzhou_region_marker_matches_guangzhou_case(self):
        tpl = self._template("广州专用模板", [])
        assert self.svc._matches_template_institutions(tpl, ["广州市中级人民法院"]) is True

    def test_no_template_institutions_empty_case_returns_false(self):
        tpl = self._template("模板", ["广州中院"])
        assert self.svc._matches_template_institutions(tpl, []) is False

    def test_exact_name_match(self):
        tpl = self._template("模板", ["广州中院"])
        assert self.svc._matches_template_institutions(tpl, ["广州中院"]) is True

    def test_template_name_contains_case_name(self):
        tpl = self._template("模板", ["广州"])
        assert self.svc._matches_template_institutions(tpl, ["广州市中级人民法院"]) is True

    def test_case_name_contains_template_name(self):
        tpl = self._template("模板", ["广州市中级人民法院"])
        assert self.svc._matches_template_institutions(tpl, ["广州"]) is True

    def test_no_overlap_returns_false(self):
        tpl = self._template("模板", ["上海高院"])
        assert self.svc._matches_template_institutions(tpl, ["北京高院"]) is False


class TestNormalizeCaseStageForDocument:
    def setup_method(self):
        self.svc = TemplateMatchingService()

    def test_empty_returns_empty(self):
        assert self.svc._normalize_case_stage_for_document("") == []

    @pytest.mark.parametrize(
        "stage",
        [
            "retrial_first",
            "retrial_second",
            "apply_retrial",
            "rehearing_first",
            "rehearing_second",
            "review",
            "petition",
            "apply_protest",
            "petition_protest",
        ],
    )
    def test_retrial_related_maps_to_retrial(self, stage):
        assert self.svc._normalize_case_stage_for_document(stage) == [DocumentCaseStage.RETRIAL]

    def test_normal_stage_passthrough(self):
        assert self.svc._normalize_case_stage_for_document("first_trial") == ["first_trial"]


class TestAsyncWrappers:
    def test_find_matching_case_document_template_names_async(self):
        svc = TemplateMatchingService()
        with patch.object(svc, "find_matching_case_document_template_names", return_value=["模板A"]) as mock_sync:
            result = asyncio.run(svc.find_matching_case_document_template_names_async("civil"))
        assert result == ["模板A"]
        mock_sync.assert_called_once_with("civil")

    def test_find_matching_contract_templates_async(self):
        svc = TemplateMatchingService()
        with patch.object(svc, "find_matching_contract_templates", return_value=[{"id": 1}]) as mock_sync:
            result = asyncio.run(svc.find_matching_contract_templates_async("civil"))
        assert result == [{"id": 1}]
        mock_sync.assert_called_once_with("civil")

    def test_find_matching_folder_templates_async(self):
        svc = TemplateMatchingService()
        with patch.object(svc, "find_matching_folder_templates", return_value=[{"id": 2}]) as mock_sync:
            result = asyncio.run(svc.find_matching_folder_templates_async("case", "civil"))
        assert result == [{"id": 2}]
        mock_sync.assert_called_once_with("case", "civil")

    def test_find_matching_case_file_templates_async(self):
        svc = TemplateMatchingService()
        with patch.object(svc, "find_matching_case_file_templates", return_value=[]) as mock_sync:
            result = asyncio.run(svc.find_matching_case_file_templates_async("civil", "first_trial", None))
        assert result == []
        mock_sync.assert_called_once_with("civil", "first_trial", None)
