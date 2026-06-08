"""Tests for cases.admin.mixins.views — increase coverage."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.cases.admin.mixins.views import (
    CaseAdminViewsMixin,
    _get_case_stage_choices,
    _get_contact_role_choices,
    _has_court_filing_plugin,
    _log_inline_formset,
)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestModuleHelpers:
    def test_get_contact_role_choices(self) -> None:
        choices = _get_contact_role_choices()
        assert isinstance(choices, list)
        # Should have at least some choices
        assert len(choices) > 0

    def test_get_case_stage_choices(self) -> None:
        choices = _get_case_stage_choices()
        assert isinstance(choices, list)
        assert len(choices) > 0

    def test_has_court_filing_plugin_import_error(self) -> None:
        """When plugins module doesn't exist, returns False."""
        with patch.dict("sys.modules", {"plugins": None}):
            result = _has_court_filing_plugin()
            assert isinstance(result, bool)

    def test_log_inline_formset_none_formset(self) -> None:
        inline = MagicMock()
        inline.formset = None
        _log_inline_formset(inline, MagicMock())

    def test_log_inline_formset_with_errors(self) -> None:
        logger = MagicMock()
        form1 = MagicMock()
        form1.errors = {"field": ["error"]}
        form2 = MagicMock()
        form2.errors = {}
        formset = MagicMock()
        formset.forms = [form1, form2]
        formset.non_form_errors.return_value = ["global error"]
        inline = MagicMock()
        inline.formset = formset
        inline.prefix = "test_prefix"
        _log_inline_formset(inline, logger)
        assert logger.warning.call_count >= 2  # form error + non_form error

    def test_log_inline_formset_no_errors(self) -> None:
        logger = MagicMock()
        form1 = MagicMock()
        form1.errors = {}
        formset = MagicMock()
        formset.forms = [form1]
        formset.non_form_errors.return_value = []
        inline = MagicMock()
        inline.formset = formset
        inline.prefix = "test"
        _log_inline_formset(inline, logger)
        logger.warning.assert_not_called()


# ---------------------------------------------------------------------------
# CaseAdminViewsMixin display methods
# ---------------------------------------------------------------------------


class TestCaseAdminViewsMixinDisplays:
    def _make_mixin(self):
        mixin = CaseAdminViewsMixin()
        mixin.admin_site = MagicMock()
        mixin.model = MagicMock()
        mixin.model._meta = MagicMock()
        return mixin

    def test_id_link(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.pk = 42
        with patch("apps.cases.admin.mixins.views.reverse", return_value="/admin/cases/case/42/change/"):
            result = mixin.id_link(obj)
            assert "42" in str(result)

    def test_name_link(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.pk = 10
        obj.name = "测试案件"
        with patch("apps.cases.admin.mixins.views.reverse", return_value="/admin/cases/case/10/detail/"):
            result = mixin.name_link(obj)
            assert "测试案件" in str(result)

    def test_case_type_display(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.get_case_type_display.return_value = "民事"
        assert mixin.case_type_display(obj) == "民事"

    def test_case_type_display_empty(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.get_case_type_display.return_value = ""
        assert mixin.case_type_display(obj) == "-"

    def test_current_stage_display(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.get_current_stage_display.return_value = "一审"
        assert mixin.current_stage_display(obj) == "一审"

    def test_current_stage_display_empty(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.get_current_stage_display.return_value = ""
        assert mixin.current_stage_display(obj) == "-"

    def test_assigned_lawyers_empty(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.assignments.all.return_value = []
        assert mixin.assigned_lawyers(obj) == "-"

    def test_assigned_lawyers_with_names(self) -> None:
        mixin = self._make_mixin()
        assignment1 = MagicMock()
        assignment1.lawyer.real_name = "张三"
        assignment2 = MagicMock()
        assignment2.lawyer.real_name = "李四"
        obj = MagicMock()
        obj.assignments.all.return_value = [assignment1, assignment2]
        result = mixin.assigned_lawyers(obj)
        assert "张三" in result
        assert "李四" in result

    def test_assigned_lawyers_with_id_fallback(self) -> None:
        mixin = self._make_mixin()
        assignment = MagicMock()
        assignment.lawyer.real_name = ""
        assignment.lawyer.id = 7
        obj = MagicMock()
        obj.assignments.all.return_value = [assignment]
        result = mixin.assigned_lawyers(obj)
        assert "7" in result

    def test_contract_folder_path_display_no_obj(self) -> None:
        mixin = self._make_mixin()
        assert mixin.contract_folder_path_display(None) == "未关联合同"

    def test_contract_folder_path_display_no_contract(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.contract = None
        assert mixin.contract_folder_path_display(obj) == "未关联合同"

    def test_contract_folder_path_display_no_binding(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.contract.folder_binding = None
        assert mixin.contract_folder_path_display(obj) == "未绑定文件夹"

    def test_contract_folder_path_display_with_binding(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.contract.folder_binding.folder_path = "/some/path"
        assert mixin.contract_folder_path_display(obj) == "/some/path"

    def test_filing_number_display(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.filing_number = "FC-2025-001"
        assert mixin.filing_number_display(obj) == "FC-2025-001"

    def test_filing_number_display_empty(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.filing_number = None
        assert mixin.filing_number_display(obj) == "未生成"

    def test_has_folder_binding_with_binding(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock()
        obj.folder_binding = MagicMock()
        result = mixin.has_folder_binding(obj)
        assert "已绑定" in result

    def test_has_folder_binding_no_binding(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock(spec=[])  # no folder_binding attr
        result = mixin.has_folder_binding(obj)
        assert "未绑定" in result

    def test_get_folder_disabled_reason_v2_empty(self) -> None:
        mixin = self._make_mixin()
        result = mixin._get_folder_disabled_reason_v2("")
        assert "无匹配" in result

    def test_get_folder_disabled_reason_v2_with_no_match(self) -> None:
        mixin = self._make_mixin()
        result = mixin._get_folder_disabled_reason_v2("无匹配的文件夹模板")
        assert "无匹配" in result

    def test_get_folder_disabled_reason_v2_with_match(self) -> None:
        mixin = self._make_mixin()
        result = mixin._get_folder_disabled_reason_v2("民事诉讼模板")
        assert result == ""

    def test_get_matched_folder_templates_display_no_case_type(self) -> None:
        mixin = self._make_mixin()
        obj = MagicMock(spec=[])
        obj.case_type = None
        result = mixin.get_matched_folder_templates_display(obj)
        assert "未设置" in result


# ---------------------------------------------------------------------------
# CaseAdminViewsMixin coerce helpers
# ---------------------------------------------------------------------------


class TestCoerceHelpers:
    def _make_mixin(self):
        return CaseAdminViewsMixin()

    def test_coerce_date_none(self) -> None:
        mixin = self._make_mixin()
        assert mixin._coerce_optional_date(None) is None

    def test_coerce_date_empty(self) -> None:
        mixin = self._make_mixin()
        assert mixin._coerce_optional_date("") is None

    def test_coerce_date_valid(self) -> None:
        mixin = self._make_mixin()
        result = mixin._coerce_optional_date("2025-06-01")
        assert result == date(2025, 6, 1)

    def test_coerce_date_invalid(self) -> None:
        mixin = self._make_mixin()
        assert mixin._coerce_optional_date("not-a-date") is None

    def test_coerce_decimal_none(self) -> None:
        mixin = self._make_mixin()
        assert mixin._coerce_optional_decimal(None) is None

    def test_coerce_decimal_empty(self) -> None:
        mixin = self._make_mixin()
        assert mixin._coerce_optional_decimal("") is None

    def test_coerce_decimal_valid(self) -> None:
        mixin = self._make_mixin()
        result = mixin._coerce_optional_decimal("123.45")
        assert result == Decimal("123.45")

    def test_coerce_decimal_invalid(self) -> None:
        mixin = self._make_mixin()
        assert mixin._coerce_optional_decimal("not-a-number") is None

    def test_coerce_bool_none(self) -> None:
        assert CaseAdminViewsMixin._coerce_optional_bool(None) is None

    def test_coerce_bool_true_values(self) -> None:
        for val in ["1", "true", "True", "yes", "on", True]:
            result = CaseAdminViewsMixin._coerce_optional_bool(val)
            assert result is True, f"Expected True for {val!r}"

    def test_coerce_bool_false_values(self) -> None:
        for val in ["0", "false", "False", "no", "off", False]:
            result = CaseAdminViewsMixin._coerce_optional_bool(val)
            assert result is False, f"Expected False for {val!r}"

    def test_coerce_bool_empty(self) -> None:
        assert CaseAdminViewsMixin._coerce_optional_bool("") is None

    def test_coerce_bool_garbage(self) -> None:
        assert CaseAdminViewsMixin._coerce_optional_bool("maybe") is None

    def test_coerce_int_none(self) -> None:
        assert CaseAdminViewsMixin._coerce_optional_int(None) is None

    def test_coerce_int_valid(self) -> None:
        assert CaseAdminViewsMixin._coerce_optional_int("42") == 42

    def test_coerce_int_invalid(self) -> None:
        assert CaseAdminViewsMixin._coerce_optional_int("abc") is None

    def test_coerce_int_empty(self) -> None:
        assert CaseAdminViewsMixin._coerce_optional_int("") is None

    def test_coerce_str_none(self) -> None:
        assert CaseAdminViewsMixin._coerce_optional_str(None) is None

    def test_coerce_str_valid(self) -> None:
        assert CaseAdminViewsMixin._coerce_optional_str(" hello ") == "hello"

    def test_coerce_str_empty(self) -> None:
        assert CaseAdminViewsMixin._coerce_optional_str("") is None


# ---------------------------------------------------------------------------
# CaseAdminViewsMixin helper methods
# ---------------------------------------------------------------------------


class TestCaseAdminViewsMixinHelpers:
    def _make_mixin(self):
        mixin = CaseAdminViewsMixin()
        mixin.admin_site = MagicMock()
        mixin.model = MagicMock()
        mixin.model._meta = MagicMock()
        return mixin

    def test_check_folder_binding(self, db) -> None:
        """_check_folder_binding returns a boolean."""
        result = CaseAdminViewsMixin._check_folder_binding(999999)
        assert isinstance(result, bool)

    def test_log_post_response_no_context(self) -> None:
        logger = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.context_data = None
        CaseAdminViewsMixin._log_post_response(response, logger)
        logger.info.assert_called_once()

    def test_log_post_response_with_form_errors(self) -> None:
        logger = MagicMock()
        response = MagicMock()
        response.status_code = 200
        form = MagicMock()
        form.errors = {"field": ["error"]}
        adminform = MagicMock()
        adminform.form = form
        response.context_data = {
            "adminform": adminform,
            "inline_admin_formsets": [],
        }
        CaseAdminViewsMixin._log_post_response(response, logger)
        assert logger.info.call_count >= 2

    def test_group_templates_by_sub_type(self) -> None:
        with patch("apps.cases.services.case.case_admin_service.CaseAdminService") as mock_svc_cls:
            mock_svc_cls.return_value.group_templates_by_sub_type.return_value = [("sub1", [])]
            result = CaseAdminViewsMixin._group_templates_by_sub_type([], [])
            assert result == [("sub1", [])]
