"""CaseAdminForm 空阶段回归：normalize_stages 返回 None 不得直写模型（列 NOT NULL）。

E2E test_case_edit_submit_and_delete 首次提交即暴露：admin 编辑案件不选
「当前阶段」时 500（NotNullViolation: cases_case.current_stage）。
"""

from __future__ import annotations

import pytest

from apps.cases.admin.case_forms_admin import CaseAdminForm
from apps.cases.models import Case
from apps.testing.factories import ContractFactory


@pytest.mark.django_db
class TestBlankCurrentStageCleaned:
    def test_blank_stage_cleaned_to_empty_string(self) -> None:
        contract = ContractFactory(name="空阶段合同", case_type="civil")
        form = CaseAdminForm(
            data={
                "name": "空阶段案件",
                "contract": contract.pk,
                "current_stage": "",
                "status": "active",
                "start_date": "2026-01-01",
            }
        )
        assert form.is_valid(), form.errors
        # 关键契约：空阶段清洗为 ""（模型默认），而非 normalize_stages 的 None
        assert form.cleaned_data["current_stage"] == ""

    def test_selected_stage_preserved(self) -> None:
        contract = ContractFactory(name="有阶段合同", case_type="civil")
        stage = Case._meta.get_field("current_stage").default
        assert stage == ""
        form = CaseAdminForm(
            data={
                "name": "有阶段案件",
                "contract": contract.pk,
                "current_stage": "first_trial",
                "status": "active",
                "start_date": "2026-01-01",
            }
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["current_stage"] == "first_trial"
