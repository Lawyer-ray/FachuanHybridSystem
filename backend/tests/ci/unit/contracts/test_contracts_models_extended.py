"""Comprehensive tests for contracts app - models, signals, services, templatetags."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.contracts.models import (
    ArchiveClassificationRule,
    ArchivePlaceholderOverride,
    ClientPaymentRecord,
    Contract,
    ContractAssignment,
    ContractFinanceLog,
    ContractFolderBinding,
    ContractFolderScanSession,
    ContractFolderScanStatus,
    ContractOASyncSession,
    ContractOASyncStatus,
    ContractParty,
    ContractPayment,
    ContractStatus,
    ContractTypeFolderRootPreset,
    FeeMode,
    FinalizedMaterial,
    Invoice,
    InvoiceStatus,
    LogLevel,
    MaterialCategory,
    PartyRole,
    RuleSource,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)
from apps.client.models import Client
from apps.organization.models import Lawyer


# ── Contract Model Extended ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestContractModelExtended:
    """Contract model extended tests."""

    def test_status_choices(self) -> None:
        assert ContractStatus.ACTIVE == "active"
        assert ContractStatus.ARCHIVED == "archived"
        assert ContractStatus.UNSIGNED == "unsigned"

    def test_fee_mode_choices(self) -> None:
        assert FeeMode.FIXED == "FIXED"
        assert FeeMode.SEMI_RISK == "SEMI_RISK"
        assert FeeMode.FULL_RISK == "FULL_RISK"
        assert FeeMode.CUSTOM == "CUSTOM"

    def test_default_fee_mode(self) -> None:
        contract = Contract.objects.create(name="默认收费合同", case_type="civil")
        assert contract.fee_mode == FeeMode.FIXED

    def test_default_status(self) -> None:
        contract = Contract.objects.create(name="默认状态合同", case_type="civil")
        assert contract.status == ContractStatus.ACTIVE

    def test_representation_stages_default(self) -> None:
        contract = Contract.objects.create(name="默认阶段合同", case_type="civil")
        assert contract.representation_stages == []

    def test_compact_archive_default(self) -> None:
        contract = Contract.objects.create(name="精简合同", case_type="civil")
        assert contract.compact_archive is False

    def test_clean_normalizes_stages(self) -> None:
        from apps.core.models.enums import CaseStage

        valid_stage = CaseStage.choices[0][0]
        contract = Contract(
            name="clean合同", case_type="civil", representation_stages=[valid_stage]
        )
        contract.clean()
        assert valid_stage in contract.representation_stages

    def test_clean_suppresses_validation_error(self) -> None:
        """clean() suppresses ValidationException from normalize."""
        contract = Contract(
            name="clean_err合同",
            case_type="civil",
            representation_stages=["invalid_stage_xyz"],
        )
        contract.clean()  # Should not raise


# ── ContractPayment Extended ────────────────────────────────────────────────


@pytest.mark.django_db
class TestContractPaymentExtended:
    """ContractPayment model tests."""

    def test_invoice_status_choices(self) -> None:
        assert InvoiceStatus.UNINVOICED == "UNINVOICED"
        assert InvoiceStatus.INVOICED_PARTIAL == "INVOICED_PARTIAL"
        assert InvoiceStatus.INVOICED_FULL == "INVOICED_FULL"

    def test_str_contains_amount(self) -> None:
        contract = Contract.objects.create(name="金额合同", case_type="civil")
        payment = ContractPayment.objects.create(
            contract=contract, amount=Decimal("50000.00"), received_at=date(2024, 1, 1)
        )
        result = str(payment)
        assert "50000" in result

    def test_str_contains_contract_id(self) -> None:
        contract = Contract.objects.create(name="id合同", case_type="civil")
        payment = ContractPayment.objects.create(
            contract=contract, amount=Decimal("100.00"), received_at=date(2024, 1, 1)
        )
        assert str(contract.id) in str(payment)


# ── ContractFinanceLog Model ───────────────────────────────────────────────


@pytest.mark.django_db
class TestContractFinanceLogModel:
    """ContractFinanceLog model tests."""

    def test_log_level_choices(self) -> None:
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARN == "WARN"
        assert LogLevel.ERROR == "ERROR"

    def test_str(self) -> None:
        contract = Contract.objects.create(name="finance合同", case_type="civil")
        lawyer = Lawyer.objects.create_user(username="finance_actor", real_name="财务律师")
        log = ContractFinanceLog.objects.create(
            contract=contract,
            action="payment_created",
            level=LogLevel.INFO,
            actor=lawyer,
        )
        result = str(log)
        assert str(contract.id) in result
        assert "payment_created" in result

    def test_default_level(self) -> None:
        contract = Contract.objects.create(name="default_level合同", case_type="civil")
        lawyer = Lawyer.objects.create_user(username="dl_actor", real_name="律师")
        log = ContractFinanceLog.objects.create(
            contract=contract, action="test", actor=lawyer
        )
        assert log.level == LogLevel.INFO


# ── SupplementaryAgreement Model Extended ───────────────────────────────────


@pytest.mark.django_db
class TestSupplementaryAgreementExtended:
    """SupplementaryAgreement extended tests."""

    def test_str_named(self) -> None:
        contract = Contract.objects.create(name="sa_name合同", case_type="civil")
        sa = SupplementaryAgreement.objects.create(contract=contract, name="补充1")
        assert "补充1" in str(sa)

    def test_str_unnamed(self) -> None:
        contract = Contract.objects.create(name="sa_unnamed合同", case_type="civil")
        sa = SupplementaryAgreement.objects.create(contract=contract)
        assert "未命名" in str(sa)


# ── FinalizedMaterial Model ────────────────────────────────────────────────


@pytest.mark.django_db
class TestFinalizedMaterialModel:
    """FinalizedMaterial model tests."""

    def test_str(self) -> None:
        contract = Contract.objects.create(name="fin合同", case_type="civil")
        mat = FinalizedMaterial.objects.create(
            contract=contract,
            file_path="/docs/test.pdf",
            original_filename="起诉状.pdf",
            category=MaterialCategory.ARCHIVE_DOCUMENT,
        )
        result = str(mat)
        assert "起诉状.pdf" in result
        assert "归档文书" in result

    def test_default_category(self) -> None:
        contract = Contract.objects.create(name="default_cat合同", case_type="civil")
        mat = FinalizedMaterial.objects.create(
            contract=contract,
            file_path="/docs/test2.pdf",
            original_filename="test.pdf",
        )
        assert mat.category == MaterialCategory.ARCHIVE_DOCUMENT

    def test_material_category_choices(self) -> None:
        assert MaterialCategory.CONTRACT_ORIGINAL == "contract_original"
        assert MaterialCategory.INVOICE == "invoice"
        assert MaterialCategory.CASE_MATERIAL == "case_material"


# ── Invoice Model ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestInvoiceModel:
    """Invoice model tests."""

    def test_str_with_filename(self) -> None:
        contract = Contract.objects.create(name="inv合同", case_type="civil")
        payment = ContractPayment.objects.create(
            contract=contract, amount=Decimal("1000.00"), received_at=date(2024, 1, 1)
        )
        inv = Invoice.objects.create(
            payment=payment,
            file_path="/invoices/test.pdf",
            original_filename="发票001.pdf",
        )
        assert str(inv) == "发票001.pdf"

    def test_str_fallback_to_id(self) -> None:
        contract = Contract.objects.create(name="inv_fallback合同", case_type="civil")
        payment = ContractPayment.objects.create(
            contract=contract, amount=Decimal("1000.00"), received_at=date(2024, 1, 1)
        )
        inv = Invoice.objects.create(
            payment=payment,
            file_path="/invoices/test.pdf",
            original_filename="",
        )
        result = str(inv)
        assert "发票" in result


# ── ClientPaymentRecord Model Extended ──────────────────────────────────────


@pytest.mark.django_db
class TestClientPaymentRecordExtended:
    """ClientPaymentRecord extended tests."""

    def test_str(self) -> None:
        contract = Contract.objects.create(name="cpr合同", case_type="civil")
        record = ClientPaymentRecord.objects.create(
            contract=contract, amount=Decimal("25000.00")
        )
        result = str(record)
        assert "25000" in result

    def test_optional_image_path(self) -> None:
        contract = Contract.objects.create(name="img合同", case_type="civil")
        record = ClientPaymentRecord.objects.create(
            contract=contract, amount=Decimal("100.00"), image_path="/img/test.jpg"
        )
        assert record.image_path == "/img/test.jpg"


# ── ContractFolderBinding Model ────────────────────────────────────────────


@pytest.mark.django_db
class TestContractFolderBindingModel:
    """ContractFolderBinding model tests."""

    def test_create(self) -> None:
        contract = Contract.objects.create(name="fb合同", case_type="civil")
        binding = ContractFolderBinding.objects.create(
            contract=contract, folder_path="/contracts/fb"
        )
        assert binding.folder_path == "/contracts/fb"


# ── ContractFolderScanSession Model ────────────────────────────────────────


@pytest.mark.django_db
class TestContractFolderScanSessionModel:
    """ContractFolderScanSession model tests."""

    def test_status_choices(self) -> None:
        assert ContractFolderScanStatus.PENDING == "pending"
        assert ContractFolderScanStatus.COMPLETED == "completed"

    def test_create_session(self) -> None:
        contract = Contract.objects.create(name="scan合同", case_type="civil")
        session = ContractFolderScanSession.objects.create(contract=contract)
        assert session.status == ContractFolderScanStatus.PENDING


# ── ContractOASyncSession Model ─────────────────────────────────────────────


@pytest.mark.django_db
class TestContractOASyncSessionModel:
    """ContractOASyncSession model tests."""

    def test_status_choices(self) -> None:
        assert ContractOASyncStatus.PENDING == "pending"

    def test_create_session(self) -> None:
        session = ContractOASyncSession.objects.create()
        assert session.status == ContractOASyncStatus.PENDING


# ── ContractTypeFolderRootPreset Model ──────────────────────────────────────


@pytest.mark.django_db
class TestContractTypeFolderRootPresetModel:
    """ContractTypeFolderRootPreset model tests."""

    def test_create(self) -> None:
        preset = ContractTypeFolderRootPreset.objects.create(
            case_type="civil", root_path="/contracts/civil"
        )
        assert preset.root_path == "/contracts/civil"


# ── ArchivePlaceholderOverride Model ────────────────────────────────────────


@pytest.mark.django_db
class TestArchivePlaceholderOverrideModel:
    """ArchivePlaceholderOverride model tests."""

    def test_create(self) -> None:
        contract = Contract.objects.create(name="override合同", case_type="civil")
        override = ArchivePlaceholderOverride.objects.create(
            contract=contract,
            template_subtype="case_cover",
            overrides={"key": "value"},
        )
        assert override.overrides == {"key": "value"}


# ── ContractAssignment Model ───────────────────────────────────────────────


@pytest.mark.django_db
class TestContractAssignmentModel:
    """ContractAssignment model tests."""

    def test_create(self) -> None:
        contract = Contract.objects.create(name="assign合同", case_type="civil")
        lawyer = Lawyer.objects.create_user(username="assign_lawyer", real_name="指派律师")
        assignment = ContractAssignment.objects.create(
            contract=contract, lawyer=lawyer
        )
        assert assignment.contract == contract
        assert assignment.lawyer == lawyer


# ── PartyRole Choices ───────────────────────────────────────────────────────


class TestPartyRoleChoices:
    """PartyRole enum tests."""

    def test_principal(self) -> None:
        assert PartyRole.PRINCIPAL == "PRINCIPAL"

    def test_opposing(self) -> None:
        assert PartyRole.OPPOSING == "OPPOSING"


# ── RuleSource Choices ──────────────────────────────────────────────────────


class TestRuleSourceChoices:
    """RuleSource enum tests."""

    def test_learned(self) -> None:
        assert RuleSource.LEARNED == "learned"

    def test_manual(self) -> None:
        assert RuleSource.MANUAL == "manual"
