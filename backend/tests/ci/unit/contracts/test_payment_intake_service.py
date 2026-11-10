"""到账待认领业务服务（数据库侧）测试。

锁定的核心行为：

1. **可见性收敛**：收件人 / 主办律师 / 管理员能看，无关律师看不到。
2. **确认生成收款记录**，并写财务审计日志。
3. **撤销确认必须同时删除收款记录**（否则留下无主的钱）。
4. **重复确认/重复撤销被拒**（幂等保护）。
5. **候选下拉与自动匹配共用资格规则**：已收满/已归档的项目不能出现在下拉里
   （用户明确要求：收完款项 / 结案 / 归档后就不应再匹配到）。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.contracts.models import Contract, ContractAssignment, ContractPayment, IntakeStatus, PaymentIntake
from apps.contracts.services.payment.intake_service import (
    can_decide,
    confirm_intake,
    ignore_intake,
    open_count,
    reject_intake,
    reopen_intake,
    selectable_contracts,
    visible_intakes_qs,
)
from apps.message_hub.models import InboxMessage, MessageSource
from apps.organization.models import AccountCredential, Lawyer


@pytest.fixture
def lawyer(db) -> Lawyer:
    return Lawyer.objects.create(username="intake_lawyer", real_name="测试律师")  # privacy-allow


@pytest.fixture
def other_lawyer(db) -> Lawyer:
    return Lawyer.objects.create(username="intake_other", real_name="别的律师")  # privacy-allow


@pytest.fixture
def admin_lawyer(db) -> Lawyer:
    return Lawyer.objects.create(username="intake_admin", real_name="管理员", is_admin=True)  # privacy-allow


@pytest.fixture
def source(db, lawyer: Lawyer) -> MessageSource:
    """收件人=lawyer 的 IMAP 来源（归属经 credential 传递）。"""
    credential = AccountCredential.objects.create(
        lawyer=lawyer, site_name="测试邮箱", account="intake@example.com", password="x"
    )
    return MessageSource.objects.create(
        credential=credential,
        source_type="imap",
        display_name="测试邮箱",
        sync_since="2026-01-01T00:00:00Z",
    )


@pytest.fixture
def message(db, source: MessageSource) -> InboxMessage:
    from django.utils import timezone

    return InboxMessage.objects.create(
        source=source,
        message_id="msg-1",
        subject="【到账通知】测试",
        sender="bank@example.com",
        received_at=timezone.now(),
        body_text="【测试银行】某人10月1日存入人民币2400元。",  # privacy-allow
    )


def _intake(message: InboxMessage, **kwargs) -> PaymentIntake:
    base = {
        "inbox_message": message,
        "dedupe_key": f"k-{PaymentIntake.objects.count() + 1}",
        "amount": Decimal("2400"),
        "received_at": date(2026, 10, 1),
        "payer_name": "某人",  # privacy-allow
        "bank_remark": "银行备注原文",  # privacy-allow
        "status": IntakeStatus.PENDING,
    }
    base.update(kwargs)
    return PaymentIntake.objects.create(**base)


def _contract(*, name="测试项目", fixed="10000", paid="0", status="active") -> Contract:
    contract = Contract.objects.create(name=name, case_type="civil", status=status)
    contract.fixed_amount = Decimal(fixed) if fixed else None
    contract.fee_mode = "FIXED"
    contract.save(update_fields=["fixed_amount", "fee_mode"])
    if paid and Decimal(paid) > 0:
        ContractPayment.objects.create(contract=contract, amount=Decimal(paid), received_at=date(2026, 1, 1))
    return contract


@pytest.mark.django_db
class TestVisibility:
    def test_recipient_sees_own_mail_intake(self, lawyer, message):
        intake = _intake(message)
        assert visible_intakes_qs(lawyer).filter(pk=intake.pk).exists()

    def test_unrelated_lawyer_cannot_see(self, other_lawyer, lawyer, message):
        _intake(message)
        assert not visible_intakes_qs(other_lawyer).exists()

    def test_primary_lawyer_sees_suggested_contract_intake(self, other_lawyer, message):
        """建议项目的主办律师也要看到——业务主办不能因邮件不归他而漏掉到账。"""
        contract = _contract()
        ContractAssignment.objects.create(contract=contract, lawyer=other_lawyer, is_primary=True)
        intake = _intake(message, suggested_contract=contract)
        assert visible_intakes_qs(other_lawyer).filter(pk=intake.pk).exists()

    def test_non_primary_assignee_does_not_see(self, other_lawyer, message):
        """非主办律师（协办）不算"与我相关"，避免无关人员看到财务数据。"""
        contract = _contract()
        ContractAssignment.objects.create(contract=contract, lawyer=other_lawyer, is_primary=False)
        _intake(message, suggested_contract=contract)
        assert not visible_intakes_qs(other_lawyer).exists()

    def test_admin_sees_all(self, admin_lawyer, message):
        _intake(message)
        assert visible_intakes_qs(admin_lawyer).count() == 1

    def test_can_decide_matrix(self, lawyer, other_lawyer, admin_lawyer, message):
        intake = _intake(message)
        assert can_decide(lawyer, intake) is True
        assert can_decide(admin_lawyer, intake) is True
        assert can_decide(other_lawyer, intake) is False

    def test_open_count_only_pending(self, lawyer, message):
        _intake(message, dedupe_key="a")
        _intake(message, dedupe_key="b", status=IntakeStatus.IGNORED, decision_note="往来款")  # privacy-allow
        assert open_count(lawyer) == 1


@pytest.mark.django_db
class TestConfirm:
    def test_confirm_creates_payment(self, lawyer, message):
        contract = _contract()
        intake = _intake(message, suggested_contract=contract)
        confirm_intake(intake_id=intake.pk, contract_id=None, user=lawyer)

        intake.refresh_from_db()
        assert intake.status == IntakeStatus.CONFIRMED
        assert intake.payment_id is not None
        assert intake.confirmed_by_id == lawyer.pk
        payment = ContractPayment.objects.get(pk=intake.payment_id)
        assert payment.contract_id == contract.pk
        assert payment.amount == Decimal("2400")
        assert "到账认领" in payment.note

    def test_confirm_can_switch_contract(self, lawyer, message):
        """允许改判：确认到与建议不同的项目。"""
        suggested = _contract(name="建议项目")  # privacy-allow
        chosen = _contract(name="实际项目")  # privacy-allow
        intake = _intake(message, suggested_contract=suggested)
        confirm_intake(intake_id=intake.pk, contract_id=chosen.pk, user=lawyer)
        intake.refresh_from_db()
        assert intake.confirmed_contract_id == chosen.pk

    def test_confirm_without_any_contract_rejected(self, lawyer, message):
        from apps.core.exceptions import ValidationException

        intake = _intake(message)
        with pytest.raises(ValidationException):
            confirm_intake(intake_id=intake.pk, contract_id=None, user=lawyer)

    def test_double_confirm_rejected(self, lawyer, message):
        from apps.core.exceptions import ValidationException

        contract = _contract()
        intake = _intake(message, suggested_contract=contract)
        confirm_intake(intake_id=intake.pk, contract_id=None, user=lawyer)
        with pytest.raises(ValidationException):
            confirm_intake(intake_id=intake.pk, contract_id=None, user=lawyer)

    def test_unrelated_lawyer_cannot_confirm(self, other_lawyer, message):
        from apps.core.exceptions import NotFoundError

        contract = _contract()
        intake = _intake(message, suggested_contract=contract)
        with pytest.raises(NotFoundError):
            confirm_intake(intake_id=intake.pk, contract_id=None, user=other_lawyer)

    def test_confirm_writes_finance_log(self, lawyer, message):
        from apps.contracts.models import ContractFinanceLog

        contract = _contract()
        intake = _intake(message, suggested_contract=contract)
        confirm_intake(intake_id=intake.pk, contract_id=None, user=lawyer)
        assert ContractFinanceLog.objects.filter(contract=contract, action="payment_intake_confirmed").exists()

    def test_over_paid_logs_warning_but_succeeds(self, lawyer, message):
        """并发/硬选导致超付：不阻断（钱确实收了），但升 WARN 留痕。"""
        from apps.contracts.models import ContractFinanceLog, LogLevel

        contract = _contract(fixed="2000", paid="2000")  # 已收满
        intake = _intake(message, suggested_contract=contract)
        confirm_intake(intake_id=intake.pk, contract_id=contract.pk, user=lawyer)
        assert ContractFinanceLog.objects.filter(
            contract=contract, action="payment_intake_over_paid", level=LogLevel.WARN
        ).exists()


@pytest.mark.django_db
class TestReopenAndClose:
    def test_reopen_deletes_payment(self, lawyer, message):
        contract = _contract()
        intake = _intake(message, suggested_contract=contract)
        confirm_intake(intake_id=intake.pk, contract_id=None, user=lawyer)
        payment_id = PaymentIntake.objects.get(pk=intake.pk).payment_id
        assert payment_id is not None

        reopen_intake(intake_id=intake.pk, user=lawyer)

        intake.refresh_from_db()
        assert intake.status == IntakeStatus.PENDING
        assert intake.payment_id is None
        assert intake.confirmed_contract_id is None
        assert not ContractPayment.objects.filter(pk=payment_id).exists()

    def test_reopen_writes_revert_log(self, lawyer, message):
        from apps.contracts.models import ContractFinanceLog

        contract = _contract()
        intake = _intake(message, suggested_contract=contract)
        confirm_intake(intake_id=intake.pk, contract_id=None, user=lawyer)
        reopen_intake(intake_id=intake.pk, user=lawyer)
        assert ContractFinanceLog.objects.filter(contract=contract, action="payment_intake_reverted").exists()

    def test_reopen_pending_rejected(self, lawyer, message):
        from apps.core.exceptions import ValidationException

        intake = _intake(message)
        with pytest.raises(ValidationException):
            reopen_intake(intake_id=intake.pk, user=lawyer)

    def test_reject_and_ignore(self, lawyer, message):
        i1 = _intake(message, dedupe_key="r1")
        reject_intake(intake_id=i1.pk, user=lawyer, reason="营销邮件误判")  # privacy-allow
        i1.refresh_from_db()
        assert i1.status == IntakeStatus.REJECTED
        assert i1.decision_note == "营销邮件误判"  # privacy-allow

        i2 = _intake(message, dedupe_key="r2")
        ignore_intake(intake_id=i2.pk, user=lawyer, reason="往来款")  # privacy-allow
        i2.refresh_from_db()
        assert i2.status == IntakeStatus.IGNORED

    def test_closed_can_be_reopened(self, lawyer, message):
        intake = _intake(message)
        reject_intake(intake_id=intake.pk, user=lawyer, reason="x")  # privacy-allow
        reopen_intake(intake_id=intake.pk, user=lawyer)
        intake.refresh_from_db()
        assert intake.status == IntakeStatus.PENDING


@pytest.mark.django_db
class TestSelectableContracts:
    """下拉与自动匹配共用资格规则——收满/归档/结案的项目不能出现在下拉里。"""

    def test_fully_paid_excluded(self, db):
        _contract(name="收满项目", fixed="10000", paid="10000")  # privacy-allow
        assert not selectable_contracts().filter(name="收满项目").exists()  # privacy-allow

    def test_partially_paid_included(self, db):
        _contract(name="部分收款项目", fixed="10000", paid="3000")  # privacy-allow
        assert selectable_contracts().filter(name="部分收款项目").exists()  # privacy-allow

    def test_archived_excluded(self, db):
        _contract(name="归档项目", fixed="10000", paid="0", status="archived")  # privacy-allow
        assert not selectable_contracts().filter(name="归档项目").exists()  # privacy-allow

    def test_unsigned_excluded(self, db):
        _contract(name="未签项目", fixed="10000", paid="0", status="unsigned")  # privacy-allow
        assert not selectable_contracts().filter(name="未签项目").exists()  # privacy-allow

    def test_search_filters_by_name(self, db):
        _contract(name="甲公司合同", fixed="10000", paid="0")  # privacy-allow
        _contract(name="乙公司合同", fixed="10000", paid="0")  # privacy-allow
        assert selectable_contracts(search="甲").filter(name="甲公司合同").exists()  # privacy-allow
        assert not selectable_contracts(search="甲").filter(name="乙公司合同").exists()  # privacy-allow

    def test_paid_total_annotated(self, db):
        _contract(name="注解项目", fixed="10000", paid="4000")  # privacy-allow
        row = selectable_contracts().get(name="注解项目")  # privacy-allow
        assert row.paid_total == Decimal("4000")
