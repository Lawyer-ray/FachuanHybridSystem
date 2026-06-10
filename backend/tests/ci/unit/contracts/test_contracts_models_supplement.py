"""contracts app 补充 Model 单元测试

覆盖 ContractFolderBinding, ContractFolderScanSession, ContractOASyncSession,
Invoice, ContractFinanceLog, Contract 的 __str__、property、choices。
"""

import pytest
from django.utils import timezone

from apps.contracts.models.contract import Contract, ContractStatus, FeeMode
from apps.contracts.models.contract_oa_sync_session import ContractOASyncSession, ContractOASyncStatus
from apps.contracts.models.finance import ContractFinanceLog, LogLevel
from apps.contracts.models.folder_binding import ContractFolderBinding
from apps.contracts.models.folder_scan_session import ContractFolderScanSession, ContractFolderScanStatus
from apps.contracts.models.invoice import Invoice
from apps.contracts.models.payment import ContractPayment, InvoiceStatus
from apps.testing.factories import ContractFactory, LawyerFactory


# ============================================================
# Contract
# ============================================================


@pytest.mark.django_db
class TestContract:
    def test_str(self):
        contract = Contract.objects.create(name="借款合同", case_type="civil")
        assert str(contract) == "借款合同"

    def test_status_choices(self):
        assert ContractStatus.UNSIGNED.value == "unsigned"
        assert ContractStatus.ACTIVE.value == "active"
        assert ContractStatus.ARCHIVED.value == "archived"

    def test_fee_mode_choices(self):
        assert FeeMode.FIXED.value == "FIXED"
        assert FeeMode.SEMI_RISK.value == "SEMI_RISK"
        assert FeeMode.FULL_RISK.value == "FULL_RISK"
        assert FeeMode.CUSTOM.value == "CUSTOM"

    def test_default_status(self):
        contract = Contract.objects.create(name="默认合同", case_type="civil")
        assert contract.status == ContractStatus.ACTIVE


# ============================================================
# ContractFolderBinding
# ============================================================


@pytest.mark.django_db
class TestContractFolderBinding:
    def test_str(self):
        contract = Contract.objects.create(name="测试合同", case_type="civil")
        binding = ContractFolderBinding.objects.create(
            contract=contract,
            folder_path="/contracts/test/2026",
        )
        result = str(binding)
        assert "测试合同" in result
        assert "/contracts/test/2026" in result

    def test_default_storage_type(self):
        contract = Contract.objects.create(name="存储测试", case_type="civil")
        binding = ContractFolderBinding.objects.create(
            contract=contract,
            folder_path="/tmp",
        )
        assert binding.storage_type == "local"


# ============================================================
# ContractFolderScanSession
# ============================================================


@pytest.mark.django_db
class TestContractFolderScanSession:
    def test_str(self):
        contract = Contract.objects.create(name="扫描合同", case_type="civil")
        session = ContractFolderScanSession.objects.create(
            contract=contract,
            status=ContractFolderScanStatus.PENDING,
        )
        result = str(session)
        assert f"contract:{contract.id}" in result
        assert "pending" in result

    def test_status_choices(self):
        assert ContractFolderScanStatus.PENDING.value == "pending"
        assert ContractFolderScanStatus.RUNNING.value == "running"
        assert ContractFolderScanStatus.COMPLETED.value == "completed"
        assert ContractFolderScanStatus.FAILED.value == "failed"
        assert ContractFolderScanStatus.IMPORTED.value == "imported"

    def test_default_progress(self):
        contract = Contract.objects.create(name="进度测试", case_type="civil")
        session = ContractFolderScanSession.objects.create(contract=contract)
        assert session.progress == 0


# ============================================================
# ContractOASyncSession
# ============================================================


@pytest.mark.django_db
class TestContractOASyncSession:
    def test_str(self):
        session = ContractOASyncSession.objects.create(
            status=ContractOASyncStatus.PENDING,
        )
        result = str(session)
        assert "contract_oa_sync" in result
        assert "pending" in result

    def test_status_choices(self):
        assert ContractOASyncStatus.PENDING.value == "pending"
        assert ContractOASyncStatus.RUNNING.value == "running"
        assert ContractOASyncStatus.COMPLETED.value == "completed"
        assert ContractOASyncStatus.FAILED.value == "failed"
        assert ContractOASyncStatus.CANCELLED.value == "cancelled"

    def test_default_counts(self):
        session = ContractOASyncSession.objects.create()
        assert session.total_count == 0
        assert session.processed_count == 0
        assert session.matched_count == 0
        assert session.multiple_count == 0
        assert session.not_found_count == 0
        assert session.error_count == 0


# ============================================================
# ContractPayment
# ============================================================


@pytest.mark.django_db
class TestContractPayment:
    def test_str(self):
        contract = Contract.objects.create(name="付款合同", case_type="civil")
        payment = ContractPayment.objects.create(
            contract=contract,
            amount=5000.00,
        )
        result = str(payment)
        assert str(contract.id) in result
        assert "5000" in result

    def test_invoice_status_choices(self):
        assert InvoiceStatus.UNINVOICED.value == "UNINVOICED"
        assert InvoiceStatus.INVOICED_PARTIAL.value == "INVOICED_PARTIAL"
        assert InvoiceStatus.INVOICED_FULL.value == "INVOICED_FULL"

    def test_default_invoice_status(self):
        contract = Contract.objects.create(name="默认状态合同", case_type="civil")
        payment = ContractPayment.objects.create(contract=contract, amount=1000)
        assert payment.invoice_status == InvoiceStatus.UNINVOICED


# ============================================================
# Invoice
# ============================================================


@pytest.mark.django_db
class TestInvoice:
    def test_str_with_filename(self):
        contract = Contract.objects.create(name="发票合同", case_type="civil")
        payment = ContractPayment.objects.create(contract=contract, amount=2000)
        invoice = Invoice.objects.create(
            payment=payment,
            file_path="/tmp/invoice.pdf",
            original_filename="增值税发票001.pdf",
        )
        assert str(invoice) == "增值税发票001.pdf"

    def test_str_without_filename(self):
        contract = Contract.objects.create(name="发票合同2", case_type="civil")
        payment = ContractPayment.objects.create(contract=contract, amount=3000)
        invoice = Invoice.objects.create(
            payment=payment,
            file_path="/tmp/inv.pdf",
            original_filename="",
        )
        result = str(invoice)
        assert "发票" in result


# ============================================================
# ContractFinanceLog
# ============================================================


@pytest.mark.django_db
class TestContractFinanceLog:
    def test_str(self):
        contract = Contract.objects.create(name="财务合同", case_type="civil")
        lawyer = LawyerFactory()
        log = ContractFinanceLog.objects.create(
            contract=contract,
            action="create_payment",
            level=LogLevel.INFO,
            actor=lawyer,
        )
        result = str(log)
        assert str(contract.id) in result
        assert "create_payment" in result
        assert "INFO" in result

    def test_log_level_choices(self):
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARN.value == "WARN"
        assert LogLevel.ERROR.value == "ERROR"

    def test_default_level(self):
        contract = Contract.objects.create(name="日志合同", case_type="civil")
        lawyer = LawyerFactory()
        log = ContractFinanceLog.objects.create(
            contract=contract,
            action="test",
            actor=lawyer,
        )
        assert log.level == LogLevel.INFO
