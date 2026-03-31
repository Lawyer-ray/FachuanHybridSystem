"""Unit tests for ContractCloneWorkflow."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, call, patch

import pytest

from apps.contracts.services.contract.admin_workflows.clone_workflow import ContractCloneWorkflow


def _make_workflow() -> tuple[ContractCloneWorkflow, MagicMock]:
    reminder_service = MagicMock()
    reminder_service.export_contract_reminders_internal.return_value = []
    workflow = ContractCloneWorkflow(reminder_service=reminder_service)
    return workflow, reminder_service


def _make_contract(*, parties: list[MagicMock], assignments: list[MagicMock], agreements: list[MagicMock]) -> MagicMock:
    contract = MagicMock()
    contract.id = 1
    contract.contract_parties.all.return_value = parties
    contract.assignments.all.return_value = assignments
    contract.supplementary_agreements.all.return_value = agreements
    return contract


def _make_target_contract() -> MagicMock:
    contract = MagicMock()
    contract.id = 2
    return contract


# ── 完整流程 ──────────────────────────────────────────────────────────────────

def test_clone_related_data_full_flow() -> None:
    party = MagicMock()
    party.client = MagicMock()
    party.role = "plaintiff"

    assignment = MagicMock()
    assignment.lawyer = MagicMock()
    assignment.is_primary = True
    assignment.order = 0

    agreement = MagicMock()
    agreement.name = "补充协议1"
    agreement_party = MagicMock()
    agreement_party.client = MagicMock()
    agreement_party.role = "party"
    agreement.parties.all.return_value = [agreement_party]

    source = _make_contract(parties=[party], assignments=[assignment], agreements=[agreement])
    target = _make_target_contract()

    workflow, reminder_service = _make_workflow()

    with (
        patch("apps.contracts.services.contract.admin_workflows.clone_workflow.ContractParty") as MockParty,
        patch("apps.contracts.services.contract.admin_workflows.clone_workflow.ContractAssignment") as MockAssignment,
        patch("apps.contracts.services.contract.admin_workflows.clone_workflow.SupplementaryAgreement") as MockAgreement,
        patch("apps.contracts.services.contract.admin_workflows.clone_workflow.SupplementaryAgreementParty") as MockAgreementParty,
    ):
        MockAgreement.objects.bulk_create.return_value = [MagicMock()]
        workflow.clone_related_data(source_contract=source, target_contract=target)

    MockParty.objects.bulk_create.assert_called_once()
    MockAssignment.objects.bulk_create.assert_called_once()
    MockAgreement.objects.bulk_create.assert_called_once()
    MockAgreementParty.objects.bulk_create.assert_called_once()


# ── 无补充协议（提前 return）────────────────────────────────────────────────

def test_clone_related_data_no_agreements_skips_agreement_bulk_create() -> None:
    source = _make_contract(parties=[], assignments=[], agreements=[])
    target = _make_target_contract()

    workflow, _ = _make_workflow()

    with (
        patch("apps.contracts.services.contract.admin_workflows.clone_workflow.ContractParty"),
        patch("apps.contracts.services.contract.admin_workflows.clone_workflow.ContractAssignment"),
        patch("apps.contracts.services.contract.admin_workflows.clone_workflow.SupplementaryAgreement") as MockAgreement,
        patch("apps.contracts.services.contract.admin_workflows.clone_workflow.SupplementaryAgreementParty") as MockAgreementParty,
    ):
        workflow.clone_related_data(source_contract=source, target_contract=target)

    MockAgreement.objects.bulk_create.assert_not_called()
    MockAgreementParty.objects.bulk_create.assert_not_called()


# ── due_at_transform 参数 ────────────────────────────────────────────────────

def test_clone_related_data_applies_due_at_transform() -> None:
    reminder = {"due_at": datetime.date(2025, 1, 1), "title": "提醒"}
    source = _make_contract(parties=[], assignments=[], agreements=[])
    target = _make_target_contract()

    workflow, reminder_service = _make_workflow()
    reminder_service.export_contract_reminders_internal.return_value = [reminder]

    transform = MagicMock(return_value=datetime.date(2026, 1, 1))

    with (
        patch("apps.contracts.services.contract.admin_workflows.clone_workflow.ContractParty"),
        patch("apps.contracts.services.contract.admin_workflows.clone_workflow.ContractAssignment"),
    ):
        workflow.clone_related_data(source_contract=source, target_contract=target, due_at_transform=transform)

    transform.assert_called_once_with(datetime.date(2025, 1, 1))
    reminder_service.create_contract_reminders_internal.assert_called_once()


# ── plus_one_year_due_at ─────────────────────────────────────────────────────

def test_plus_one_year_due_at_adds_one_year() -> None:
    d = datetime.date(2024, 3, 15)
    result = ContractCloneWorkflow.plus_one_year_due_at(d)
    assert result == datetime.date(2025, 3, 15)


def test_plus_one_year_due_at_none_returns_none() -> None:
    assert ContractCloneWorkflow.plus_one_year_due_at(None) is None


def test_plus_one_year_due_at_falsy_returns_none() -> None:
    assert ContractCloneWorkflow.plus_one_year_due_at("") is None
