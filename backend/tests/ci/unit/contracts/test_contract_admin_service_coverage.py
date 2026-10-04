"""补充覆盖测试: contracts/services/contract/admin/contract_admin_service.py

覆盖: 六个服务的延迟加载 property（None → 构造、注入 → 原样返回）与
全部委托方法的参数透传 / 返回值传播；get_contract_detail_context 行为回归。
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.models import Contract
from apps.contracts.services.contract.admin.contract_admin_service import ContractAdminService


def _make_admin_service() -> tuple[ContractAdminService, dict[str, MagicMock]]:
    """注入全套 mock 子服务，返回 (服务, mock 字典)。"""
    services = {
        "display_service": MagicMock(name="display"),
        "filing_number_service": MagicMock(name="filing_number"),
        "document_service": MagicMock(name="document"),
        "query_service": MagicMock(name="query"),
        "mutation_service": MagicMock(name="mutation"),
        "progress_service": MagicMock(name="progress"),
    }
    return ContractAdminService(**services), services


# ── 延迟加载 property ─────────────────────────────────────────────


class TestLazyProperties:
    def test_display_service_lazy_created(self):
        svc = ContractAdminService()
        with patch("apps.contracts.services.contract.query.ContractDisplayService") as mock_cls:
            first = svc.display_service
            second = svc.display_service
        assert first is mock_cls.return_value
        assert second is first  # 只创建一次

    def test_filing_number_service_lazy_created(self):
        svc = ContractAdminService()
        with patch("apps.contracts.services.assignment.filing_number_service.FilingNumberService") as mock_cls:
            first = svc.filing_number_service
            second = svc.filing_number_service
        assert first is mock_cls.return_value
        assert second is first

    def test_document_service_lazy_created(self):
        svc = ContractAdminService()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_document_service.ContractAdminDocumentService"
        ) as mock_cls:
            assert svc.document_service is mock_cls.return_value

    def test_query_service_lazy_created(self):
        svc = ContractAdminService()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_query_service.ContractAdminQueryService"
        ) as mock_cls:
            assert svc.query_service is mock_cls.return_value

    def test_mutation_service_lazy_created_with_filing_number(self):
        svc = ContractAdminService()
        filing = MagicMock()
        svc._filing_number_service = filing
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.ContractAdminMutationService"
        ) as mock_cls:
            assert svc.mutation_service is mock_cls.return_value
        mock_cls.assert_called_once_with(filing_number_service=filing)

    def test_progress_service_lazy_created(self):
        svc = ContractAdminService()
        with patch("apps.contracts.services.contract.query.ContractProgressService") as mock_cls:
            assert svc.progress_service is mock_cls.return_value

    def test_injected_services_returned_as_is(self):
        svc, services = _make_admin_service()
        assert svc.display_service is services["display_service"]
        assert svc.filing_number_service is services["filing_number_service"]
        assert svc.document_service is services["document_service"]
        assert svc.query_service is services["query_service"]
        assert svc.mutation_service is services["mutation_service"]
        assert svc.progress_service is services["progress_service"]


# ── 委托方法 ──────────────────────────────────────────────────────


class TestDelegationMethods:
    def test_generate_contract_document(self):
        svc, services = _make_admin_service()
        services["document_service"].generate_contract_document.return_value = {"url": "/media/doc.pdf"}
        result = svc.generate_contract_document(9)
        services["document_service"].generate_contract_document.assert_called_once_with(9)
        assert result == {"url": "/media/doc.pdf"}

    def test_generate_supplementary_agreement(self):
        svc, services = _make_admin_service()
        services["document_service"].generate_supplementary_agreement.return_value = {"url": "/media/sup.pdf"}
        result = svc.generate_supplementary_agreement(3, 5)
        services["document_service"].generate_supplementary_agreement.assert_called_once_with(3, 5)
        assert result == {"url": "/media/sup.pdf"}

    def test_duplicate_contract(self):
        svc, services = _make_admin_service()
        duplicated = MagicMock(name="duplicated_contract")
        services["mutation_service"].duplicate_contract.return_value = duplicated
        assert svc.duplicate_contract(11) is duplicated
        services["mutation_service"].duplicate_contract.assert_called_once_with(11)

    def test_can_create_case(self):
        svc, services = _make_admin_service()
        services["query_service"].can_create_case.return_value = True
        assert svc.can_create_case(21) is True
        services["query_service"].can_create_case.assert_called_once_with(21)

    def test_create_case_from_contract_passes_kwargs(self):
        svc, services = _make_admin_service()
        user = MagicMock(name="user")
        org_access = {"law_firm_ids": [1]}
        case_dto = MagicMock(name="case_dto")
        services["mutation_service"].create_case_from_contract.return_value = case_dto
        result = svc.create_case_from_contract(
            contract_id=31,
            user=user,
            org_access=org_access,
            perm_open_access=True,
        )
        services["mutation_service"].create_case_from_contract.assert_called_once_with(
            contract_id=31, user=user, org_access=org_access, perm_open_access=True
        )
        assert result is case_dto

    def test_create_case_from_contract_defaults(self):
        svc, services = _make_admin_service()
        services["mutation_service"].create_case_from_contract.return_value = MagicMock()
        svc.create_case_from_contract(contract_id=32)
        call_kwargs = services["mutation_service"].create_case_from_contract.call_args.kwargs
        assert call_kwargs["user"] is None
        assert call_kwargs["org_access"] is None
        assert call_kwargs["perm_open_access"] is False

    def test_renew_advisor_contract(self):
        svc, services = _make_admin_service()
        renewed = MagicMock(name="renewed")
        services["mutation_service"].renew_advisor_contract.return_value = renewed
        assert svc.renew_advisor_contract(41) is renewed
        services["mutation_service"].renew_advisor_contract.assert_called_once_with(41)

    def test_generate_advisor_contract_name(self):
        svc, services = _make_admin_service()
        services["mutation_service"].generate_advisor_contract_name.return_value = "2026年度法律顾问合同"
        result = svc.generate_advisor_contract_name(["A公司"], date(2026, 1, 1), date(2026, 12, 31))
        services["mutation_service"].generate_advisor_contract_name.assert_called_once_with(
            ["A公司"], date(2026, 1, 1), date(2026, 12, 31)
        )
        assert result == "2026年度法律顾问合同"

    def test_get_related_cases(self):
        svc, services = _make_admin_service()
        related = [{"id": 1, "name": "案件A"}]
        services["query_service"].get_related_cases.return_value = related
        assert svc.get_related_cases(51) is related
        services["query_service"].get_related_cases.assert_called_once_with(51)

    def test_handle_contract_filing_change(self):
        svc, services = _make_admin_service()
        services["mutation_service"].handle_contract_filing_change.return_value = "FLT-2026-001"
        assert svc.handle_contract_filing_change(61, True) == "FLT-2026-001"
        services["mutation_service"].handle_contract_filing_change.assert_called_once_with(61, True)


# ── get_contract_detail_context 行为回归 ─────────────────────────
# 该方法在源码标记 pragma: no cover，不计覆盖率，但行为仍需保护。


def _make_contract_stub(db_contract: Contract, case_type: str, stages: list[str]) -> MagicMock:
    stub = MagicMock(spec=Contract)
    stub.pk = db_contract.id
    stub.case_type = case_type
    stub.representation_stages = stages
    payments_qs = MagicMock(name="payments_qs")
    payments_qs.aggregate.return_value = {"total": 0}
    stub.payments.all.return_value = payments_qs
    supplementary_qs = MagicMock(name="supplementary_qs")
    supplementary_qs.exists.return_value = False
    stub.supplementary_agreements.all.return_value.order_by.return_value = supplementary_qs
    stub.finalized_materials.exclude.return_value = []
    return stub


@pytest.mark.django_db
class TestGetContractDetailContext:
    def test_civil_contract_full_context(self):
        db_contract = Contract.objects.create(name="上下文合同", case_type="civil")
        contract_obj = _make_contract_stub(db_contract, "civil", ["first_trial", "second_trial"])
        svc, services = _make_admin_service()
        services["query_service"].get_contract_detail.return_value = contract_obj
        services["query_service"].get_related_cases.return_value = []
        services["display_service"].get_matched_document_template.return_value = "委托合同模板"
        services["display_service"].get_matched_document_templates_list.return_value = ["模板A"]
        services["display_service"].get_matched_folder_templates.return_value = "文件夹模板"
        services["display_service"].get_matched_folder_templates_list.return_value = ["文件夹A"]
        services["progress_service"].get_payment_progress.return_value = {"paid": 0}
        services["progress_service"].get_invoice_summary.return_value = {"invoiced": 0}

        with (
            patch("apps.contracts.services.contract.integrations.InvoiceUploadService") as invoice_cls,
            patch("apps.contracts.services.client_payment.ClientPaymentRecordService") as payment_cls,
            patch("apps.contracts.services.archive.wiring.build_archive_checklist_service") as build_checklist,
        ):
            invoice_cls.return_value.list_invoices_by_contract.return_value = {"p1": []}
            payment_cls.return_value.get_contract_payment_records.return_value = []
            payment_cls.return_value.calculate_total_amount.return_value = 0
            build_checklist.return_value.get_checklist_with_status.return_value = {
                "items": [{"code": "lt_1", "template": "case_cover"}, {"code": "lt_4", "template": None}]
            }
            context = svc.get_contract_detail_context(db_contract.id)

        assert context["contract"] is contract_obj
        assert context["total_payment_amount"] == 0
        assert context["has_supplementary_agreements"] is False
        assert context["show_representation_stages"] is True
        assert context["representation_stages_display"] == ["一审", "二审"]
        assert context["has_contract_template"] is True
        assert context["contract_template_display"] == "委托合同模板"
        assert context["contract_templates_list"] == ["模板A"]
        assert context["has_folder_template"] is True
        assert context["folder_templates_list"] == ["文件夹A"]
        assert context["payment_progress"] == {"paid": 0}
        assert context["invoice_summary"] == {"invoiced": 0}
        assert context["invoices_by_payment"] == {"p1": []}
        assert context["client_payments"] == []
        assert context["total_client_payment"] == 0
        assert context["finalized_materials_grouped"] == {}
        assert context["archive_code_to_template"] == {"lt_1": "case_cover"}
        assert "today" in context and "soon_due_date" in context

    @pytest.mark.django_db
    def test_display_service_failure_falls_back(self):
        db_contract = Contract.objects.create(name="异常合同", case_type="non_litigation")
        contract_obj = _make_contract_stub(db_contract, "non_litigation", [])
        svc, services = _make_admin_service()
        services["query_service"].get_contract_detail.return_value = contract_obj
        services["query_service"].get_related_cases.return_value = []
        services["display_service"].get_matched_document_template.side_effect = RuntimeError("boom")
        services["display_service"].get_matched_folder_templates.side_effect = RuntimeError("boom")
        services["progress_service"].get_payment_progress.return_value = {}
        services["progress_service"].get_invoice_summary.return_value = {}

        with (
            patch("apps.contracts.services.contract.integrations.InvoiceUploadService") as invoice_cls,
            patch("apps.contracts.services.client_payment.ClientPaymentRecordService") as payment_cls,
            patch("apps.contracts.services.archive.wiring.build_archive_checklist_service") as build_checklist,
        ):
            invoice_cls.return_value.list_invoices_by_contract.return_value = {}
            payment_cls.return_value.get_contract_payment_records.return_value = []
            payment_cls.return_value.calculate_total_amount.return_value = 0
            build_checklist.return_value.get_checklist_with_status.return_value = {"items": []}
            context = svc.get_contract_detail_context(db_contract.id)

        assert context["contract"] is contract_obj
        # 显示服务异常时回退到"查询失败"且不判定为有模板
        assert context["has_contract_template"] is False
        assert context["contract_template_display"] == "查询失败"
        assert context["contract_templates_list"] == []
        assert context["has_folder_template"] is False
        assert context["folder_template_display"] == "查询失败"
        assert context["folder_templates_list"] == []
        assert context["show_representation_stages"] is False
        assert context["representation_stages_display"] == []
