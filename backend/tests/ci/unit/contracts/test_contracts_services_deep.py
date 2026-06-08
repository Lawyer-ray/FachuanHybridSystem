"""Comprehensive tests for contracts services — mutation, query, workflow, access policy, validator, assemblers, payment, finance."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.models import (
    Contract,
    ContractAssignment,
    ContractFinanceLog,
    ContractPayment,
    ContractParty,
    ContractStatus,
    FeeMode,
    InvoiceStatus,
    PartyRole,
)
from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy
from apps.contracts.services.contract.domain.validator import ContractValidator
from apps.contracts.services.contract.mutation.service import ContractMutationService
from apps.contracts.services.contract.query.service import ContractQueryService
from apps.contracts.services.contract.domain.workflow_service import ContractWorkflowService
from apps.contracts.services.contract.assemblers.contract_details_assembler import ContractDetailsAssembler
from apps.contracts.services.payment.contract_payment_service import ContractPaymentService
from apps.contracts.services.payment.contract_finance_service import ContractFinanceService
from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.testing.factories import CaseFactory, ClientFactory, ContractFactory, LawyerFactory


# ── Fixtures ──


@pytest.fixture
def validator():
    return ContractValidator()


@pytest.fixture
def access_policy():
    return ContractAccessPolicy()


@pytest.fixture
def mock_validator():
    v = MagicMock(spec=ContractValidator)
    v.validate_fee_mode.return_value = None
    v.validate_stages.return_value = ["一审"]
    return v


@pytest.fixture
def mock_lawyer_assignment_service():
    svc = MagicMock()
    svc.set_contract_lawyers.return_value = []
    svc.get_all_lawyers.return_value = []
    return svc


@pytest.fixture
def mock_case_service():
    svc = MagicMock()
    svc.close_cases_by_contract_internal.return_value = 0
    svc.count_cases_by_contract.return_value = 0
    return svc


@pytest.fixture
def mutation_service(mock_validator, mock_lawyer_assignment_service, mock_case_service):
    return ContractMutationService(
        validator=mock_validator,
        lawyer_assignment_service=mock_lawyer_assignment_service,
        case_service=mock_case_service,
    )


@pytest.fixture
def payment_service():
    return ContractPaymentService()


@pytest.fixture
def finance_service():
    return ContractFinanceService()


@pytest.fixture
def admin_user(db, law_firm):
    from apps.organization.models import Lawyer

    return Lawyer.objects.create_user(
        username="admin_test_svc",
        password="testpass123",
        is_admin=True,
        law_firm=law_firm,
    )


# ── ContractValidator tests ──


@pytest.mark.django_db
class TestContractValidator:
    def test_validate_fee_mode_fixed_ok(self, validator):
        validator.validate_fee_mode({"fee_mode": FeeMode.FIXED, "fixed_amount": 10000})

    def test_validate_fee_mode_fixed_missing_amount(self, validator):
        with pytest.raises(ValidationException):
            validator.validate_fee_mode({"fee_mode": FeeMode.FIXED})

    def test_validate_fee_mode_fixed_zero_amount(self, validator):
        with pytest.raises(ValidationException):
            validator.validate_fee_mode({"fee_mode": FeeMode.FIXED, "fixed_amount": 0})

    def test_validate_fee_mode_semi_risk_ok(self, validator):
        validator.validate_fee_mode({"fee_mode": FeeMode.SEMI_RISK, "fixed_amount": 5000, "risk_rate": 10})

    def test_validate_fee_mode_semi_risk_missing_rate(self, validator):
        with pytest.raises(ValidationException):
            validator.validate_fee_mode({"fee_mode": FeeMode.SEMI_RISK, "fixed_amount": 5000})

    def test_validate_fee_mode_semi_risk_missing_amount(self, validator):
        with pytest.raises(ValidationException):
            validator.validate_fee_mode({"fee_mode": FeeMode.SEMI_RISK, "risk_rate": 10})

    def test_validate_fee_mode_full_risk_ok(self, validator):
        validator.validate_fee_mode({"fee_mode": FeeMode.FULL_RISK, "risk_rate": 15})

    def test_validate_fee_mode_full_risk_missing_rate(self, validator):
        with pytest.raises(ValidationException):
            validator.validate_fee_mode({"fee_mode": FeeMode.FULL_RISK})

    def test_validate_fee_mode_full_risk_zero_rate(self, validator):
        with pytest.raises(ValidationException):
            validator.validate_fee_mode({"fee_mode": FeeMode.FULL_RISK, "risk_rate": 0})

    def test_validate_fee_mode_custom_ok(self, validator):
        validator.validate_fee_mode({"fee_mode": FeeMode.CUSTOM, "custom_terms": "自定义条款"})

    def test_validate_fee_mode_custom_empty(self, validator):
        with pytest.raises(ValidationException):
            validator.validate_fee_mode({"fee_mode": FeeMode.CUSTOM, "custom_terms": ""})

    def test_validate_fee_mode_custom_whitespace(self, validator):
        with pytest.raises(ValidationException):
            validator.validate_fee_mode({"fee_mode": FeeMode.CUSTOM, "custom_terms": "   "})

    def test_validate_fee_mode_none(self, validator):
        validator.validate_fee_mode({})

    def test_validate_stages_empty(self, validator):
        assert validator.validate_stages([], "civil") == []

    def test_validate_stages_valid(self, validator):
        from apps.core.config.business_config import business_config

        stages = [v for v, _ in business_config.get_stages_for_case_type("civil")]
        if stages:
            assert validator.validate_stages([stages[0]], "civil") == [stages[0]]

    def test_validate_stages_invalid(self, validator):
        with pytest.raises(ValidationException):
            validator.validate_stages(["不存在的阶段"], "civil")


# ── ContractAccessPolicy tests ──


@pytest.mark.django_db
class TestContractAccessPolicy:
    def test_has_access_perm_open(self, access_policy):
        assert access_policy.has_access(1, None, None, perm_open_access=True)

    def test_has_access_no_user(self, access_policy):
        assert not access_policy.has_access(1, None, None)

    def test_has_access_admin_user(self, access_policy, admin_user):
        c = ContractFactory()
        assert access_policy.has_access(c.id, admin_user, None)

    def test_can_create_contract_authenticated(self, access_policy, lawyer):
        assert access_policy.can_create_contract(lawyer)

    def test_can_create_contract_anonymous(self, access_policy):
        assert not access_policy.can_create_contract(None)

    def test_filter_queryset_perm_open(self, access_policy, db):
        qs = Contract.objects.all()
        result = access_policy.filter_queryset(qs, None, None, perm_open_access=True)
        assert result is qs

    def test_filter_queryset_no_user(self, access_policy, db):
        ContractFactory()
        qs = Contract.objects.all()
        result = access_policy.filter_queryset(qs, None, None)
        assert result.count() == 0

    def test_filter_queryset_admin(self, access_policy, admin_user, db):
        ContractFactory()
        qs = Contract.objects.all()
        result = access_policy.filter_queryset(qs, admin_user, None)
        assert result.count() >= 1

    def test_ensure_access_raises(self, access_policy):
        with pytest.raises(PermissionDenied):
            access_policy.ensure_access(contract_id=1, user=None, org_access=None)

    def test_ensure_access_passes(self, access_policy, admin_user):
        c = ContractFactory()
        access_policy.ensure_access(contract_id=c.id, user=admin_user, org_access=None)

    def test_has_access_with_contract_obj_admin(self, access_policy, admin_user):
        c = ContractFactory()
        assert access_policy.has_access(c.id, admin_user, None, contract=c)

    def test_has_access_with_contract_obj_no_user(self, access_policy):
        c = ContractFactory()
        assert not access_policy.has_access(c.id, None, None, contract=c)

    def test_ensure_access_ctx(self, access_policy, admin_user):
        from apps.core.security.access_context import AccessContext

        c = ContractFactory()
        ctx = AccessContext(user=admin_user, org_access=None, perm_open_access=False)
        access_policy.ensure_access_ctx(contract_id=c.id, ctx=ctx)


# ── ContractMutationService tests ──


@pytest.mark.django_db
class TestContractMutationService:
    def test_create_contract(self, mutation_service, mock_validator):
        data = {"name": "Test Contract", "case_type": "civil", "fee_mode": "FIXED"}
        contract = mutation_service.create_contract(data)
        assert contract.pk is not None
        assert contract.name == "Test Contract"

    def test_create_contract_with_lawyers(self, mutation_service, mock_validator, mock_lawyer_assignment_service):
        data = {"name": "Test", "case_type": "civil", "lawyer_ids": [1, 2]}
        mutation_service.create_contract(data)
        mock_lawyer_assignment_service.set_contract_lawyers.assert_called_once()

    def test_create_contract_with_parties(self, mutation_service, mock_validator):
        client = ClientFactory()
        data = {
            "name": "Test",
            "case_type": "civil",
            "parties": [{"client_id": client.id, "role": "PRINCIPAL"}],
        }
        mutation_service.create_contract(data)
        assert ContractParty.objects.filter(client=client).exists()

    def test_create_contract_strips_non_model_fields(self, mutation_service, mock_validator):
        data = {
            "name": "Test",
            "case_type": "civil",
            "cases": [{"name": "c1"}],
            "payments": [],
            "reminders": [],
            "assignments": [],
            "supplementary_agreements": [],
        }
        contract = mutation_service.create_contract(data)
        assert contract.pk is not None

    def test_update_contract(self, mutation_service, mock_validator):
        c = ContractFactory()
        updated = mutation_service.update_contract(c.pk, {"name": "Updated"})
        assert updated.name == "Updated"

    def test_update_contract_not_found(self, mutation_service):
        with pytest.raises(NotFoundError):
            mutation_service.update_contract(99999, {"name": "X"})

    def test_update_contract_fee_mode_validation(self, mutation_service, mock_validator):
        c = ContractFactory()
        mutation_service.update_contract(c.pk, {"fee_mode": "FIXED"})
        mock_validator.validate_fee_mode.assert_called()

    def test_update_contract_stages_validation(self, mutation_service, mock_validator):
        c = ContractFactory()
        mutation_service.update_contract(c.pk, {"representation_stages": ["一审"]})
        mock_validator.validate_stages.assert_called()

    def test_update_contract_archived_closes_cases(self, mutation_service, mock_validator, mock_case_service):
        c = ContractFactory(status=ContractStatus.ACTIVE)
        mock_case_service.close_cases_by_contract_internal.return_value = 2
        mutation_service.update_contract(c.pk, {"status": ContractStatus.ARCHIVED})
        mock_case_service.close_cases_by_contract_internal.assert_called_once_with(c.pk)

    def test_delete_contract(self, mutation_service, mock_case_service):
        c = ContractFactory()
        mutation_service.delete_contract(c.pk)
        assert not Contract.objects.filter(pk=c.pk).exists()

    def test_delete_contract_not_found(self, mutation_service):
        with pytest.raises(NotFoundError):
            mutation_service.delete_contract(99999)

    def test_update_contract_lawyers(self, mutation_service, mock_lawyer_assignment_service):
        c = ContractFactory()
        mutation_service.update_contract_lawyers(c.pk, [1, 2])
        mock_lawyer_assignment_service.set_contract_lawyers.assert_called_with(c.pk, [1, 2])


# ── ContractQueryService tests ──


@pytest.mark.django_db
class TestContractQueryService:
    def test_list_contracts(self, db):
        svc = ContractQueryService()
        ContractFactory()
        ContractFactory()
        qs = svc.list_contracts(perm_open_access=True)
        assert qs.count() >= 2

    def test_list_contracts_filter_case_type(self, db):
        svc = ContractQueryService()
        ContractFactory(case_type="civil")
        ContractFactory(case_type="criminal")
        qs = svc.list_contracts(case_type="civil", perm_open_access=True)
        for c in qs:
            assert c.case_type == "civil"

    def test_list_contracts_filter_status(self, db):
        svc = ContractQueryService()
        ContractFactory(status=ContractStatus.ACTIVE)
        ContractFactory(status=ContractStatus.ARCHIVED)
        qs = svc.list_contracts(status="active", perm_open_access=True)
        for c in qs:
            assert c.status == "active"

    def test_list_contracts_filter_search(self, db):
        svc = ContractQueryService()
        ContractFactory(name="Alpha合同")
        ContractFactory(name="Beta合同")
        qs = svc.list_contracts(search="Alpha", perm_open_access=True)
        assert qs.count() >= 1

    def test_list_contracts_filter_fee_mode(self, db):
        svc = ContractQueryService()
        ContractFactory(fee_mode=FeeMode.FIXED)
        qs = svc.list_contracts(fee_mode="FIXED", perm_open_access=True)
        for c in qs:
            assert c.fee_mode == "FIXED"

    def test_list_contracts_filter_is_filed(self, db):
        svc = ContractQueryService()
        ContractFactory(is_filed=True)
        ContractFactory(is_filed=False)
        qs = svc.list_contracts(is_filed=True, perm_open_access=True)
        for c in qs:
            assert c.is_filed is True

    def test_get_contract_internal(self, db):
        svc = ContractQueryService()
        c = ContractFactory()
        result = svc.get_contract_internal(c.pk)
        assert result.pk == c.pk

    def test_get_contract_internal_not_found(self, db):
        svc = ContractQueryService()
        with pytest.raises(NotFoundError):
            svc.get_contract_internal(99999)

    def test_get_contract_with_details_model_internal(self, db):
        svc = ContractQueryService()
        c = ContractFactory()
        result = svc.get_contract_with_details_model_internal(c.pk)
        assert result.pk == c.pk

    def test_get_contract_with_details_model_internal_not_found(self, db):
        svc = ContractQueryService()
        result = svc.get_contract_with_details_model_internal(99999)
        assert result is None


# ── ContractWorkflowService tests ──


@pytest.mark.django_db
class TestContractWorkflowService:
    def _make_workflow(self):
        mutation_svc = MagicMock()
        mutation_svc.create_contract.return_value = MagicMock(pk=1)
        supplementary_svc = MagicMock()
        finance_mutation_svc = MagicMock()
        lawyer_assignment_svc = MagicMock()
        lawyer_assignment_svc.get_all_lawyers.return_value = []
        case_svc = MagicMock()
        case_svc.create_case.return_value = MagicMock(id=10)
        return ContractWorkflowService(
            mutation_service=mutation_svc,
            supplementary_agreement_service=supplementary_svc,
            finance_mutation_service=finance_mutation_svc,
            lawyer_assignment_service=lawyer_assignment_svc,
            case_service=case_svc,
        )

    def test_create_contract_basic(self):
        wf = self._make_workflow()
        wf.create_contract_with_cases({"name": "test", "case_type": "civil"})
        wf.mutation_service.create_contract.assert_called_once()

    def test_create_contract_with_cases_data(self):
        wf = self._make_workflow()
        wf.create_contract_with_cases(
            {"name": "test", "case_type": "civil"},
            cases_data=[{"name": "case1", "case_type": "civil", "parties": []}],
        )
        wf.case_service.create_case.assert_called_once()

    def test_create_contract_with_supplementary(self):
        wf = self._make_workflow()
        wf.create_contract_with_cases(
            {"name": "test", "case_type": "civil", "supplementary_agreements": [{"name": "SA1"}]},
        )
        wf.supplementary_agreement_service.create_supplementary_agreement.assert_called_once()

    def test_create_contract_with_payments_confirms(self):
        wf = self._make_workflow()
        wf.create_contract_with_cases(
            {"name": "test", "case_type": "civil"},
            payments_data=[{"amount": 1000}],
            confirm_finance=True,
        )
        wf.finance_mutation_service.add_payments.assert_called_once()

    def test_create_contract_with_payments_no_confirm_raises(self):
        wf = self._make_workflow()
        with pytest.raises(ValidationException):
            wf.create_contract_with_cases(
                {"name": "test", "case_type": "civil"},
                payments_data=[{"amount": 1000}],
                confirm_finance=False,
            )

    def test_create_contract_with_lawyers_and_parties(self):
        wf = self._make_workflow()
        lawyer = MagicMock(id=1)
        wf.lawyer_assignment_service.get_all_lawyers.return_value = [lawyer]
        wf.create_contract_with_cases(
            {"name": "test", "case_type": "civil"},
            cases_data=[{
                "name": "case1",
                "case_type": "civil",
                "parties": [{"client_id": 1, "legal_status": "原告"}],
            }],
            assigned_lawyer_ids=[1],
        )
        wf.case_service.create_case_assignment.assert_called()
        wf.case_service.create_case_party.assert_called()


# ── ContractDetailsAssembler tests ──


@pytest.mark.django_db
class TestContractDetailsAssembler:
    def test_assemble_basic(self):
        assembler = ContractDetailsAssembler()
        c = ContractFactory()
        result = assembler.to_dict(c)
        assert result["id"] == c.pk
        assert result["name"] == c.name
        assert result["contract_parties"] == []
        assert result["assignments"] == []
        assert result["cases"] == []

    def test_assemble_with_parties(self):
        assembler = ContractDetailsAssembler()
        c = ContractFactory()
        client = ClientFactory()
        ContractParty.objects.create(contract=c, client=client, role=PartyRole.PRINCIPAL)
        result = assembler.to_dict(c)
        assert len(result["contract_parties"]) == 1
        assert result["contract_parties"][0]["client_id"] == client.id

    def test_assemble_with_assignments(self, law_firm):
        assembler = ContractDetailsAssembler()
        c = ContractFactory()
        lawyer = LawyerFactory(law_firm=law_firm)
        ContractAssignment.objects.create(contract=c, lawyer=lawyer, is_primary=True, order=1)
        result = assembler.to_dict(c)
        assert len(result["assignments"]) == 1
        assert result["assignments"][0]["lawyer_id"] == lawyer.id

    def test_assemble_with_cases(self):
        assembler = ContractDetailsAssembler()
        c = ContractFactory()
        CaseFactory(contract=c)
        result = assembler.to_dict(c)
        assert len(result["cases"]) == 1


# ── ContractPaymentService tests ──


@pytest.mark.django_db
class TestContractPaymentService:
    def test_list_payments_empty(self, db):
        svc = ContractPaymentService()
        qs = svc.list_payments()
        assert qs.count() == 0

    def test_list_payments_with_contract_filter(self, db):
        svc = ContractPaymentService()
        c = ContractFactory()
        ContractPayment.objects.create(contract=c, amount=Decimal("1000"), received_at=date.today())
        c2 = ContractFactory()
        ContractPayment.objects.create(contract=c2, amount=Decimal("2000"), received_at=date.today())
        qs = svc.list_payments(contract_id=c.pk)
        assert qs.count() == 1

    def test_list_payments_with_invoice_status_filter(self, db):
        svc = ContractPaymentService()
        c = ContractFactory()
        ContractPayment.objects.create(contract=c, amount=Decimal("1000"), invoice_status=InvoiceStatus.UNINVOICED)
        ContractPayment.objects.create(contract=c, amount=Decimal("2000"), invoice_status=InvoiceStatus.INVOICED_FULL)
        qs = svc.list_payments(invoice_status=InvoiceStatus.UNINVOICED)
        assert qs.count() == 1

    def test_list_payments_with_date_range(self, db):
        svc = ContractPaymentService()
        c = ContractFactory()
        ContractPayment.objects.create(contract=c, amount=Decimal("1000"), received_at=date(2025, 1, 15))
        ContractPayment.objects.create(contract=c, amount=Decimal("2000"), received_at=date(2025, 6, 15))
        qs = svc.list_payments(start_date=date(2025, 3, 1), end_date=date(2025, 12, 31))
        assert qs.count() == 1

    def test_get_payment(self, db):
        svc = ContractPaymentService()
        c = ContractFactory()
        p = ContractPayment.objects.create(contract=c, amount=Decimal("1000"))
        result = svc.get_payment(p.pk)
        assert result.pk == p.pk

    def test_get_payment_not_found(self, db):
        svc = ContractPaymentService()
        with pytest.raises(NotFoundError):
            svc.get_payment(99999)

    def test_create_payment_success(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory(fixed_amount=Decimal("50000"))
        p = svc.create_payment(
            contract_id=c.pk,
            amount=Decimal("10000"),
            user=admin_user,
            confirm=True,
        )
        assert p.pk is not None
        assert p.amount == Decimal("10000")

    def test_create_payment_no_confirm_raises(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory()
        with pytest.raises(ValidationException, match="二次确认"):
            svc.create_payment(contract_id=c.pk, amount=Decimal("1000"), user=admin_user, confirm=False)

    def test_create_payment_zero_amount_raises(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory()
        with pytest.raises(ValidationException, match="大于0"):
            svc.create_payment(contract_id=c.pk, amount=Decimal("0"), user=admin_user, confirm=True)

    def test_create_payment_negative_amount_raises(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory()
        with pytest.raises(ValidationException, match="大于0"):
            svc.create_payment(contract_id=c.pk, amount=Decimal("-100"), user=admin_user, confirm=True)

    def test_create_payment_over_fixed_amount_raises(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory(fixed_amount=Decimal("1000"))
        with pytest.raises(ValidationException, match="累计收款"):
            svc.create_payment(contract_id=c.pk, amount=Decimal("2000"), user=admin_user, confirm=True)

    def test_create_payment_invoiced_over_amount_raises(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory()
        with pytest.raises(ValidationException, match="开票金额"):
            svc.create_payment(
                contract_id=c.pk,
                amount=Decimal("1000"),
                invoiced_amount=Decimal("2000"),
                user=admin_user,
                confirm=True,
            )

    def test_update_payment_success(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory(fixed_amount=Decimal("50000"))
        p = ContractPayment.objects.create(contract=c, amount=Decimal("1000"))
        updated = svc.update_payment(
            payment_id=p.pk,
            data={"note": "updated note"},
            user=admin_user,
            confirm=True,
        )
        assert updated.note == "updated note"

    def test_update_payment_no_confirm_raises(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory()
        p = ContractPayment.objects.create(contract=c, amount=Decimal("1000"))
        with pytest.raises(ValidationException, match="二次确认"):
            svc.update_payment(payment_id=p.pk, data={"note": "x"}, user=admin_user, confirm=False)

    def test_update_payment_amount(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory(fixed_amount=Decimal("50000"))
        p = ContractPayment.objects.create(contract=c, amount=Decimal("1000"))
        updated = svc.update_payment(
            payment_id=p.pk,
            data={"amount": Decimal("2000")},
            user=admin_user,
            confirm=True,
        )
        assert updated.amount == Decimal("2000")

    def test_update_payment_zero_amount_raises(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory(fixed_amount=Decimal("50000"))
        p = ContractPayment.objects.create(contract=c, amount=Decimal("1000"))
        with pytest.raises(ValidationException, match="大于0"):
            svc.update_payment(
                payment_id=p.pk,
                data={"amount": Decimal("0")},
                user=admin_user,
                confirm=True,
            )

    def test_update_payment_invoiced_amount(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory(fixed_amount=Decimal("50000"))
        p = ContractPayment.objects.create(contract=c, amount=Decimal("1000"))
        updated = svc.update_payment(
            payment_id=p.pk,
            data={"invoiced_amount": Decimal("500")},
            user=admin_user,
            confirm=True,
        )
        assert updated.invoiced_amount == Decimal("500")
        assert updated.invoice_status == InvoiceStatus.INVOICED_PARTIAL

    def test_delete_payment_success(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory()
        p = ContractPayment.objects.create(contract=c, amount=Decimal("1000"))
        result = svc.delete_payment(payment_id=p.pk, user=admin_user, confirm=True)
        assert result["success"] is True
        assert not ContractPayment.objects.filter(pk=p.pk).exists()

    def test_delete_payment_no_confirm_raises(self, db, admin_user):
        svc = ContractPaymentService()
        c = ContractFactory()
        p = ContractPayment.objects.create(contract=c, amount=Decimal("1000"))
        with pytest.raises(ValidationException, match="二次确认"):
            svc.delete_payment(payment_id=p.pk, user=admin_user, confirm=False)

    def test_calculate_invoice_status_uninvoiced(self, db):
        svc = ContractPaymentService()
        assert svc._calculate_invoice_status(Decimal("0"), Decimal("1000")) == InvoiceStatus.UNINVOICED

    def test_calculate_invoice_status_partial(self, db):
        svc = ContractPaymentService()
        assert svc._calculate_invoice_status(Decimal("500"), Decimal("1000")) == InvoiceStatus.INVOICED_PARTIAL

    def test_calculate_invoice_status_full(self, db):
        svc = ContractPaymentService()
        assert svc._calculate_invoice_status(Decimal("1000"), Decimal("1000")) == InvoiceStatus.INVOICED_FULL

    def test_get_total_received(self, db):
        svc = ContractPaymentService()
        c = ContractFactory()
        ContractPayment.objects.create(contract=c, amount=Decimal("1000"))
        ContractPayment.objects.create(contract=c, amount=Decimal("2000"))
        assert svc._get_total_received(c.pk) == Decimal("3000")

    def test_get_total_received_exclude(self, db):
        svc = ContractPaymentService()
        c = ContractFactory()
        p1 = ContractPayment.objects.create(contract=c, amount=Decimal("1000"))
        ContractPayment.objects.create(contract=c, amount=Decimal("2000"))
        assert svc._get_total_received(c.pk, exclude_id=p1.pk) == Decimal("2000")

    def test_log_finance_no_actor(self, db):
        svc = ContractPaymentService()
        c = ContractFactory()
        svc._log_finance(c.pk, None, "test_action")
        assert ContractFinanceLog.objects.count() == 0


# ── ContractFinanceService tests ──


@pytest.mark.django_db
class TestContractFinanceService:
    def test_get_finance_stats_empty(self, db):
        svc = ContractFinanceService()
        result = svc.get_finance_stats()
        assert result["total_received_all"] == 0
        assert result["total_invoiced_all"] == 0

    def test_get_finance_stats_with_data(self, db):
        svc = ContractFinanceService()
        c = ContractFactory()
        ContractPayment.objects.create(
            contract=c, amount=Decimal("1000"), invoiced_amount=Decimal("500"),
            invoice_status=InvoiceStatus.INVOICED_PARTIAL
        )
        result = svc.get_finance_stats(contract_id=c.pk)
        assert len(result["items"]) == 1

    def test_get_finance_stats_with_date_range(self, db):
        svc = ContractFinanceService()
        c = ContractFactory()
        ContractPayment.objects.create(contract=c, amount=Decimal("1000"), received_at=date(2025, 6, 1))
        ContractPayment.objects.create(contract=c, amount=Decimal("2000"), received_at=date(2025, 1, 1))
        result = svc.get_finance_stats(start_date=date(2025, 3, 1), end_date=date(2025, 12, 31))
        assert len(result["items"]) == 1
