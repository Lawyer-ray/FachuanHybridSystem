"""Coverage tests for cases admin views and services."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestCaseAdminViewsMixin:
    def test_import(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        assert CaseAdminViewsMixin is not None

    def test_coerce_optional_date_none(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_date(None) is None
        assert mixin._coerce_optional_date("") is None

    def test_coerce_optional_date_valid(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_date("2025-06-30") == date(2025, 6, 30)

    def test_coerce_optional_date_invalid(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_date("not-a-date") is None

    def test_coerce_optional_decimal_none(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_decimal(None) is None

    def test_coerce_optional_decimal_valid(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_decimal("1234.56") == Decimal("1234.56")

    def test_coerce_optional_decimal_invalid(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        assert mixin._coerce_optional_decimal("abc") is None

    def test_coerce_optional_bool_none(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        assert CaseAdminViewsMixin._coerce_optional_bool(None) is None

    def test_coerce_optional_bool_true(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        assert CaseAdminViewsMixin._coerce_optional_bool(True) is True
        assert CaseAdminViewsMixin._coerce_optional_bool("true") is True
        assert CaseAdminViewsMixin._coerce_optional_bool("1") is True
        assert CaseAdminViewsMixin._coerce_optional_bool("yes") is True

    def test_coerce_optional_bool_false(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        assert CaseAdminViewsMixin._coerce_optional_bool(False) is False
        assert CaseAdminViewsMixin._coerce_optional_bool("false") is False
        assert CaseAdminViewsMixin._coerce_optional_bool("0") is False

    def test_coerce_optional_int_none(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        assert CaseAdminViewsMixin._coerce_optional_int(None) is None

    def test_coerce_optional_int_valid(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        assert CaseAdminViewsMixin._coerce_optional_int("42") == 42

    def test_coerce_optional_int_invalid(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        assert CaseAdminViewsMixin._coerce_optional_int("abc") is None

    def test_coerce_optional_str_none(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        assert CaseAdminViewsMixin._coerce_optional_str(None) is None

    def test_coerce_optional_str_valid(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        assert CaseAdminViewsMixin._coerce_optional_str("  hello  ") == "hello"

    def test_get_folder_disabled_reason_v2_no_match(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        assert mixin._get_folder_disabled_reason_v2("") == "无匹配的文件夹模板"
        assert mixin._get_folder_disabled_reason_v2("无匹配xxx") == "无匹配的文件夹模板"

    def test_get_folder_disabled_reason_v2_has_match(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        assert mixin._get_folder_disabled_reason_v2("模板A") == ""

    def test_check_folder_binding(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        with patch("apps.cases.admin.mixins.views.Case") as MockCase:
            MockCase.objects.filter.return_value.filter.return_value.exists.return_value = True
            result = CaseAdminViewsMixin._check_folder_binding(1)
            assert result is True

    def test_contract_folder_path_display_no_obj(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        assert mixin.contract_folder_path_display(None) == "未关联合同"

    def test_contract_folder_path_display_no_contract(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        obj = SimpleNamespace(contract=None)
        assert mixin.contract_folder_path_display(obj) == "未关联合同"

    def test_filing_number_display(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        obj_with = SimpleNamespace(filing_number="2025-001")
        assert mixin.filing_number_display(obj_with) == "2025-001"
        obj_without = SimpleNamespace(filing_number=None)
        assert mixin.filing_number_display(obj_without) == "未生成"

    def test_has_folder_binding_yes(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        obj = SimpleNamespace(folder_binding=MagicMock())
        assert "已绑定" in mixin.has_folder_binding(obj)

    def test_has_folder_binding_no(self):
        from apps.cases.admin.mixins.views import CaseAdminViewsMixin

        mixin = CaseAdminViewsMixin()
        obj = SimpleNamespace(folder_binding=None)
        assert mixin.has_folder_binding(obj) == "未绑定"


# --- cases services ---

class TestCasesServices:
    def test_folder_scan_service_import(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService

        assert CaseFolderScanService is not None

    def test_case_material_service_import(self):
        from apps.cases.services.material.case_material_service import CaseMaterialService

        assert CaseMaterialService is not None

    def test_email_folder_scan_service_import(self):
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService

        assert EmailFolderScanService is not None

    def test_case_import_service_import(self):
        from apps.cases.services.case_import_service import CaseImportService

        assert CaseImportService is not None

    def test_case_admin_service_import(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        assert CaseAdminService is not None

    def test_cause_court_data_service_import(self):
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataService

        assert CauseCourtDataService is not None
