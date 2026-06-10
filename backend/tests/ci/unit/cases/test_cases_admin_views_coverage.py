"""Cases Admin Views Mixin 测试 - 覆盖 CaseAdminViewsMixin"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.http import Http404

from apps.cases.admin.mixins.views import (
    CaseAdminViewsMixin,
    _get_contact_role_choices,
    _get_case_stage_choices,
    _has_court_filing_plugin,
    _log_inline_formset,
)

User = get_user_model()


def _make_request(method="GET", path="/admin/", data=None):
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path, data or {})
    else:
        request = factory.post(path, data or {})
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestCaseAdminViewsMixinHelperFunctions:
    """测试模块级辅助函数"""

    def test_get_contact_role_choices(self):
        choices = _get_contact_role_choices()
        assert isinstance(choices, list)
        for key, label in choices:
            assert isinstance(key, str)
            assert isinstance(label, str)

    def test_get_case_stage_choices(self):
        choices = _get_case_stage_choices()
        assert isinstance(choices, list)
        for key, label in choices:
            assert isinstance(key, str)
            assert isinstance(label, str)

    def test_has_court_filing_plugin(self):
        result = _has_court_filing_plugin()
        assert isinstance(result, bool)

    def test_log_inline_formset_no_formset(self):
        inline_formset = MagicMock()
        inline_formset.formset = None
        logger = MagicMock()
        _log_inline_formset(inline_formset, logger)
        logger.warning.assert_not_called()

    def test_log_inline_formset_with_errors(self):
        inline_formset = MagicMock()
        form = MagicMock()
        form.errors = {"field": ["error"]}
        inline_formset.formset.forms = [form]
        inline_formset.formset.non_form_errors.return_value = []
        inline_formset.formset.prefix = "test"
        logger = MagicMock()
        _log_inline_formset(inline_formset, logger)
        logger.warning.assert_called()

    def test_log_inline_formset_with_non_form_errors(self):
        inline_formset = MagicMock()
        inline_formset.formset.forms = []
        inline_formset.formset.non_form_errors.return_value = ["non form error"]
        inline_formset.formset.prefix = "test"
        logger = MagicMock()
        _log_inline_formset(inline_formset, logger)
        logger.warning.assert_called()


@pytest.mark.django_db
class TestCaseAdminViewsMixinDisplayMethods:
    """测试 display 方法"""

    def test_case_type_display(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.get_case_type_display.return_value = "民事"
        result = mixin.case_type_display(obj)
        assert result == "民事"

    def test_case_type_display_empty(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.get_case_type_display.return_value = ""
        result = mixin.case_type_display(obj)
        assert result == "-"

    def test_current_stage_display(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.get_current_stage_display.return_value = "一审"
        result = mixin.current_stage_display(obj)
        assert result == "一审"

    def test_current_stage_display_empty(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.get_current_stage_display.return_value = ""
        result = mixin.current_stage_display(obj)
        assert result == "-"

    def test_assigned_lawyers_empty(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.assignments.all.return_value = []
        result = mixin.assigned_lawyers(obj)
        assert result == "-"

    def test_assigned_lawyers_with_names(self):
        mixin = CaseAdminViewsMixin()
        assignment = MagicMock()
        assignment.lawyer.real_name = "张三"
        obj = MagicMock()
        obj.assignments.all.return_value = [assignment]
        result = mixin.assigned_lawyers(obj)
        assert "张三" in result

    def test_assigned_lawyers_no_real_name(self):
        mixin = CaseAdminViewsMixin()
        assignment = MagicMock()
        assignment.lawyer.real_name = ""
        assignment.lawyer.id = 42
        obj = MagicMock()
        obj.assignments.all.return_value = [assignment]
        result = mixin.assigned_lawyers(obj)
        assert "42" in result

    def test_contract_folder_path_display_no_contract(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.contract = None
        result = mixin.contract_folder_path_display(obj)
        assert "未关联合同" in result

    def test_contract_folder_path_display_no_binding(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.contract.folder_binding = None
        result = mixin.contract_folder_path_display(obj)
        assert "未绑定" in result

    def test_contract_folder_path_display_with_binding(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.contract.folder_binding.folder_path = "/some/path"
        result = mixin.contract_folder_path_display(obj)
        assert "/some/path" in result

    def test_filing_number_display_with_number(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.filing_number = "FC-2025-001"
        result = mixin.filing_number_display(obj)
        assert "FC-2025-001" in result

    def test_filing_number_display_empty(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.filing_number = None
        result = mixin.filing_number_display(obj)
        assert "未生成" in result

    def test_has_folder_binding_with_binding(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock()
        obj.folder_binding = MagicMock()
        result = mixin.has_folder_binding(obj)
        assert "已绑定" in result

    def test_has_folder_binding_without_binding(self):
        mixin = CaseAdminViewsMixin()
        obj = MagicMock(spec=[])  # no folder_binding attribute
        del obj.folder_binding  # Ensure no folder_binding
        result = mixin.has_folder_binding(obj)
        assert result == "未绑定"


@pytest.mark.django_db
class TestCaseAdminViewsMixinCoerceMethods:
    """测试类型强制转换方法"""

    def test_coerce_optional_date_none(self):
        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_date(None) is None

    def test_coerce_optional_date_empty(self):
        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_date("") is None

    def test_coerce_optional_date_valid(self):
        mixin = CaseAdminViewsMixin()
        result = mixin._coerce_optional_date("2025-06-01")
        assert result == date(2025, 6, 1)

    def test_coerce_optional_date_invalid(self):
        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_date("not-a-date") is None

    def test_coerce_optional_decimal_none(self):
        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_decimal(None) is None

    def test_coerce_optional_decimal_empty(self):
        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_decimal("") is None

    def test_coerce_optional_decimal_valid(self):
        mixin = CaseAdminViewsMixin()
        result = mixin._coerce_optional_decimal("123.45")
        assert result == Decimal("123.45")

    def test_coerce_optional_decimal_invalid(self):
        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_decimal("abc") is None

    def test_coerce_optional_bool_none(self):
        assert CaseAdminViewsMixin._coerce_optional_bool(None) is None

    def test_coerce_optional_bool_true_values(self):
        for val in ("1", "true", "yes", "on", True):
            assert CaseAdminViewsMixin._coerce_optional_bool(val) is True

    def test_coerce_optional_bool_false_values(self):
        for val in ("0", "false", "no", "off", False):
            assert CaseAdminViewsMixin._coerce_optional_bool(val) is False

    def test_coerce_optional_bool_empty(self):
        assert CaseAdminViewsMixin._coerce_optional_bool("") is None

    def test_coerce_optional_bool_invalid(self):
        assert CaseAdminViewsMixin._coerce_optional_bool("maybe") is None

    def test_coerce_optional_int_none(self):
        assert CaseAdminViewsMixin._coerce_optional_int(None) is None

    def test_coerce_optional_int_valid(self):
        assert CaseAdminViewsMixin._coerce_optional_int("42") == 42

    def test_coerce_optional_int_invalid(self):
        assert CaseAdminViewsMixin._coerce_optional_int("abc") is None

    def test_coerce_optional_int_empty(self):
        assert CaseAdminViewsMixin._coerce_optional_int("") is None

    def test_coerce_optional_str_none(self):
        assert CaseAdminViewsMixin._coerce_optional_str(None) is None

    def test_coerce_optional_str_valid(self):
        assert CaseAdminViewsMixin._coerce_optional_str("  hello  ") == "hello"

    def test_coerce_optional_str_empty(self):
        assert CaseAdminViewsMixin._coerce_optional_str("") is None


@pytest.mark.django_db
class TestCaseAdminViewsMixinFolderDisabled:
    """测试 _get_folder_disabled_reason_v2"""

    def test_no_match(self):
        mixin = CaseAdminViewsMixin()
        assert "无匹配" in mixin._get_folder_disabled_reason_v2("")

    def test_no_match_text(self):
        mixin = CaseAdminViewsMixin()
        assert "无匹配" in mixin._get_folder_disabled_reason_v2("无匹配的文件夹模板")

    def test_with_match(self):
        mixin = CaseAdminViewsMixin()
        assert mixin._get_folder_disabled_reason_v2("模板A, 模板B") == ""


@pytest.mark.django_db
class TestCaseAdminViewsMixinGroupTemplates:
    """测试 _group_templates_by_sub_type"""

    def test_group_templates_by_sub_type(self):
        mixin = CaseAdminViewsMixin()
        templates = [{"name": "模板1", "sub_type": "A"}]
        sub_type_choices = [("A", "类型A"), ("B", "类型B")]
        with patch("apps.cases.services.case.case_admin_service.CaseAdminService") as MockService:
            MockService.return_value.group_templates_by_sub_type.return_value = [("类型A", [{"name": "模板1"}])]
            result = CaseAdminViewsMixin._group_templates_by_sub_type(templates, sub_type_choices)
            assert isinstance(result, list)
