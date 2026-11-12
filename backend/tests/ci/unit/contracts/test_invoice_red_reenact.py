"""红字发票（冲红重开）落库层 + 裁定层的行为锁定。

锁定的都是**会直接改账、改合同文件夹结构**的判定，所以每条都以“三年后律师能否
说清”为验收标准：

1. 红票文件名带「红字开具」，落 `已冲红/`；原票被**移动**进去（根目录不许留一份）。
2. `save_invoice(reject_duplicated_number=True)` 把重复票号从提示升级为 400。
3. 「冲红 + 重开」是一个原子动作：任一条守卫（G1–G6）不满足都整笔拒绝，
   不允许出现“红票落了、重开票没落”的半截账。
4. 整组撤销把三张票都还原（红票/新票移入 `_已删除/`，原票移回发票目录）。
5. 归档闸 2 / 闸 3：作废红票既不进扫描候选的勾选，也不进归档材料。

环境：必须 `DB_NAME=test_fachuan_dev`（禁止碰工作库）。文件操作全部在 `tmp_path` 与
临时 `MEDIA_ROOT` 里，不留残留。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from apps.contracts.models import (
    Contract,
    ContractFinanceLog,
    ContractFolderBinding,
    ContractPayment,
    Invoice,
    InvoiceIntake,
    InvoiceIntakeStatus,
    InvoiceStatus,
)
from apps.contracts.services.archive.checklist.material_mapping import map_contract_materials
from apps.contracts.services.archive.generation.download_handler import _download_uploaded_item, _looks_voided
from apps.contracts.services.contract.integrations._import_pipeline import ImportPipeline
from apps.contracts.services.payment.invoice_file_service import InvoiceFileService, invoice_voided_by, is_voided
from apps.contracts.services.payment.invoice_intake_service import (
    confirm_invoice_intake,
    confirm_red_only,
    confirm_red_reenact,
    reopen_invoice_intake,
)
from apps.core.exceptions import ValidationException
from apps.message_hub.models import InboxMessage, MessageSource
from apps.organization.models import AccountCredential, Lawyer
from apps.testing.factories import ContractFactory

INVOICE_DIR = "1-律师资料/3-发票"
BLUE_NUMBER = "11111111111111111111"
RED_NUMBER = "12345678901234567890"
REISSUE_NUMBER = "99999999999999999999"


# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def media_root(tmp_path: Path, settings: Any) -> Iterator[Path]:
    """把 MEDIA_ROOT 指到临时目录：发票 media 副本不许写进真实 media。"""
    root = tmp_path / "media"
    root.mkdir()
    settings.MEDIA_ROOT = root
    yield root


@pytest.fixture
def lawyer(db: Any) -> Lawyer:
    return Lawyer.objects.create(username="red_lawyer", real_name="测试律师", is_admin=True)


@pytest.fixture
def message(db: Any, lawyer: Lawyer) -> InboxMessage:
    from django.utils import timezone

    credential = AccountCredential.objects.create(
        lawyer=lawyer, site_name="测试邮箱", account="red@example.com", password="x"
    )
    source = MessageSource.objects.create(
        credential=credential,
        source_type="imap",
        display_name="测试邮箱",
        sync_since="2026-01-01T00:00:00Z",
    )
    return InboxMessage.objects.create(
        source=source,
        message_id="msg-red-1",
        subject="【发票】已开具",
        sender="finance@example.com",
        received_at=timezone.now(),
        body_text="发票已开具，请查收。",
    )


@pytest.fixture
def contract(db: Any) -> Contract:
    return ContractFactory(name="某某非诉专项")


@pytest.fixture
def folder(tmp_path: Path, contract: Contract) -> Path:
    """绑定文件夹：模板形态 `1-律师资料/3-发票`，`已冲红/` **不预建**。"""
    root = tmp_path / "binding"
    (root / INVOICE_DIR).mkdir(parents=True)
    ContractFolderBinding.objects.create(contract=contract, folder_path=str(root))
    return root


def _intake(
    message: InboxMessage,
    contract: Contract,
    *,
    number: str,
    amount: str | None,
    red_against: str = "",
    red_confirmation: str = "",
) -> InvoiceIntake:
    """建一条待认领发票，并把附件落到临时 MEDIA_ROOT（save_invoice 要读它）。"""
    from django.conf import settings

    from apps.contracts.services.payment.invoice_intake_scanner import _build_dedupe_key

    rel = f"message_hub/imap/1/{number}.pdf"
    target = Path(settings.MEDIA_ROOT) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"%PDF-1.4 red sample")
    return InvoiceIntake.objects.create(
        inbox_message=message,
        part_index=0,
        dedupe_key=_build_dedupe_key(message.pk, InvoiceIntake.objects.count(), number),
        attachment_path=rel,
        original_filename=f"dzfp_{number}.pdf",
        invoice_number=number,
        invoice_date=date(2026, 11, 11),
        total_amount=Decimal(amount) if amount is not None else None,
        buyer_name="某甲",
        red_against_number=red_against,
        red_confirmation_no=red_confirmation,
        status=InvoiceIntakeStatus.PENDING,
        suggested_contract=contract,
    )


def _confirmed_blue(
    message: InboxMessage,
    contract: Contract,
    *,
    payment: ContractPayment,
    number: str = BLUE_NUMBER,
    amount: str = "10000.00",
    folder_subpath: str = f"{INVOICE_DIR}/发票（某某非诉专项）_20261110开具.pdf",
) -> InvoiceIntake:
    """一张已入账的蓝票（原票）：直接落 Invoice + 已确认 intake，跳过 urealy 文件链路。"""
    invoice = Invoice.objects.create(
        payment=payment,
        file_path=f"contracts/invoices/{payment.pk}/{number}.pdf",
        original_filename=f"dzfp_{number}.pdf",
        invoice_number=number,
        invoice_date=date(2026, 11, 10),
        total_amount=Decimal(amount),
        seller_name="某某律师事务所",
        folder_subpath=folder_subpath,
    )
    media_file = Path(__import__("django.conf", fromlist=["settings"]).settings.MEDIA_ROOT) / invoice.file_path
    media_file.parent.mkdir(parents=True, exist_ok=True)
    media_file.write_bytes(b"%PDF-1.4 blue")
    return InvoiceIntake.objects.create(
        inbox_message=message,
        part_index=1,
        dedupe_key=f"blue-{number}",
        attachment_path=invoice.file_path,
        original_filename=f"dzfp_{number}.pdf",
        invoice_number=number,
        invoice_date=date(2026, 11, 10),
        total_amount=Decimal(amount),
        status=InvoiceIntakeStatus.CONFIRMED,
        suggested_contract=contract,
        confirmed_contract=contract,
        confirmed_payment=payment,
        invoice=invoice,
    )


@pytest.fixture
def payment(db: Any, contract: Contract) -> ContractPayment:
    return ContractPayment.objects.create(
        contract=contract,
        amount=Decimal("10000.00"),
        received_at=date(2026, 11, 10),
        invoiced_amount=Decimal("10000.00"),
        invoice_status=InvoiceStatus.INVOICED_FULL,
    )


# ── 落库层：命名与落点 ─────────────────────────────────────────────


class TestDisplayFilenameRed:
    def test_red_invoice_tail_marks_red(self) -> None:
        name = InvoiceFileService().display_filename(
            contract_name="某某非诉专项",
            inv_date=date(2026, 11, 11),
            ext=".pdf",
            is_red=True,
        )
        assert name == "发票（某某非诉专项）_20261111红字开具.pdf"

    def test_blue_invoice_unchanged(self) -> None:
        name = InvoiceFileService().display_filename(contract_name="某某案", inv_date=date(2026, 11, 11), ext=".pdf")
        assert name == "发票（某某案）_20261111开具.pdf"

    def test_red_and_blue_same_day_do_not_collide(self) -> None:
        """同一天的红票与重开蓝票必须不同名——这是改命名的第一重理由。"""
        service = InvoiceFileService()
        blue = service.display_filename(contract_name="某某案", inv_date=date(2026, 11, 11), ext=".pdf")
        red = service.display_filename(contract_name="某某案", inv_date=date(2026, 11, 11), ext=".pdf", is_red=True)
        assert blue != red


@pytest.mark.django_db
class TestSaveInvoiceDuplicatedNumber:
    def test_duplicated_number_rejected_when_requested(
        self, media_root: Path, lawyer: Lawyer, contract: Contract, payment: ContractPayment, message: InboxMessage
    ) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.contracts.models import Invoice as InvoiceModel
        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice

        InvoiceModel.objects.create(
            payment=payment,
            file_path="contracts/invoices/seed.pdf",
            original_filename="seed.pdf",
            invoice_number=BLUE_NUMBER,
            total_amount=Decimal("10000.00"),
        )
        with pytest.raises(ValidationException) as exc:
            InvoiceFileService().save_invoice(
                payment_id=payment.pk,
                uploaded_file=SimpleUploadedFile("dzfp_x.pdf", b"%PDF-1.4 dup", content_type="application/pdf"),
                parsed=ParsedInvoice(invoice_number=BLUE_NUMBER, total_amount=Decimal("10000.00")),
                user=lawyer,
                to_contract_folder=False,
                reject_duplicated_number=True,
            )
        assert exc.value.code == "INVOICE_NUMBER_DUPLICATED"

    def test_duplicated_number_is_only_a_hint_by_default(
        self, media_root: Path, lawyer: Lawyer, contract: Contract, payment: ContractPayment
    ) -> None:
        """人手拖文件上传：重复票号只提示（重传同一张票覆盖是真实场景）。"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice

        Invoice.objects.create(
            payment=payment,
            file_path="contracts/invoices/seed2.pdf",
            original_filename="seed2.pdf",
            invoice_number=BLUE_NUMBER,
            total_amount=Decimal("10000.00"),
        )
        saved = InvoiceFileService().save_invoice(
            payment_id=payment.pk,
            uploaded_file=SimpleUploadedFile("dzfp_y.pdf", b"%PDF-1.4 dup2", content_type="application/pdf"),
            parsed=ParsedInvoice(invoice_number=BLUE_NUMBER, total_amount=Decimal("10000.00")),
            user=lawyer,
            to_contract_folder=False,
        )
        assert saved.duplicated is True


# ── 记账层：净额 + 已冲红待重开 ────────────────────────────────────


@pytest.mark.django_db
class TestRecomputeInvoicedAmount:
    def _add_invoice(self, payment: ContractPayment, amount: str, **kwargs: Any) -> Invoice:
        # file_path 必须唯一（uniq_invoice_payment_file_path）：同额多张（红票+重开票）时靠序号区分
        return Invoice.objects.create(
            payment=payment,
            file_path=f"contracts/invoices/{payment.pk}/{Invoice.objects.filter(payment=payment).count()}.pdf",
            original_filename=f"{amount}.pdf",
            total_amount=Decimal(amount),
            **kwargs,
        )

    def test_negative_sum_is_not_capped_to_zero_status(self, payment: ContractPayment) -> None:
        """冲红未重开：净额 max(0) 但不许显示“未开票”，而是“已冲红待重开”。"""
        self._add_invoice(payment, "10000.00")
        self._add_invoice(payment, "-10000.00")
        InvoiceFileService().recompute_payment_invoicing(payment)
        payment.refresh_from_db()
        assert payment.invoiced_amount == Decimal("0.00")
        assert payment.invoice_status == InvoiceStatus.VOIDED_PENDING_REISSUE

    def test_positive_sum_still_capped_by_payment_amount(self, payment: ContractPayment) -> None:
        """正数分支仍受收款金额上限约束（不能因为负数放行就把上限也去掉）。"""
        self._add_invoice(payment, "30000.00")
        InvoiceFileService().recompute_payment_invoicing(payment)
        payment.refresh_from_db()
        # 收款只有 10000：开了 30000 也只能记到 10000（模型约束不许超）
        assert payment.invoiced_amount == Decimal("10000.00")
        assert payment.invoice_status == InvoiceStatus.INVOICED_FULL

    def test_overlap_net_amount(self, payment: ContractPayment) -> None:
        """红票 + 重开蓝票：净额回到 40000，状态回 INVOICED_FULL。"""
        self._add_invoice(payment, "10000.00")
        self._add_invoice(payment, "-10000.00")
        self._add_invoice(payment, "10000.00")
        InvoiceFileService().recompute_payment_invoicing(payment)
        payment.refresh_from_db()
        assert payment.invoiced_amount == Decimal("10000.00")
        assert payment.invoice_status == InvoiceStatus.INVOICED_FULL

    def test_no_invoice_stays_uninvoiced(self, payment: ContractPayment) -> None:
        Invoice.objects.filter(payment=payment).delete()
        InvoiceFileService().recompute_payment_invoicing(payment)
        payment.refresh_from_db()
        assert payment.invoice_status == InvoiceStatus.UNINVOICED


# ── 裁定层：冲红重开的主路径 ────────────────────────────────────────


@pytest.mark.django_db
class TestConfirmRedReenact:
    def _setup(
        self, message: InboxMessage, contract: Contract, payment: ContractPayment, folder: Path
    ) -> tuple[InvoiceIntake, InvoiceIntake, InvoiceIntake]:
        blue = _confirmed_blue(message, contract, payment=payment)
        assert blue.invoice is not None
        original_path = folder / blue.invoice.folder_subpath
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_bytes(b"%PDF-1.4 original")

        red = _intake(
            message,
            contract,
            number=RED_NUMBER,
            amount="-10000.00",
            red_against=BLUE_NUMBER,
            red_confirmation="22222222222222222222",
        )
        red.offset_invoice = blue.invoice
        red.save(update_fields=["offset_invoice"])
        reissue = _intake(message, contract, number=REISSUE_NUMBER, amount="10000.00")
        reissue.invoice_number = REISSUE_NUMBER
        reissue.save(update_fields=["invoice_number"])
        return blue, red, reissue

    def test_renact_lands_red_and_blue_and_moves_original(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        folder: Path,
        lawyer: Lawyer,
    ) -> None:
        blue, red, reissue = self._setup(message, contract, payment, folder)

        result = confirm_red_reenact(red_intake_id=red.pk, new_intake_id=reissue.pk, user=lawyer)

        red.refresh_from_db()
        reissue.refresh_from_db()
        blue.refresh_from_db()
        assert red.status == InvoiceIntakeStatus.CONFIRMED
        assert reissue.status == InvoiceIntakeStatus.CONFIRMED
        # 组内配对落在 supersedes_intake（重开蓝票指回红票）——撤销整组靠这条反向关系
        assert reissue.supersedes_intake_id == red.pk
        assert result["red_invoice_id"] == red.invoice_id
        assert result["new_invoice_id"] == reissue.invoice_id

        red_invoice = Invoice.objects.get(pk=red.invoice_id)
        new_invoice = Invoice.objects.get(pk=reissue.invoice_id)
        assert red_invoice.total_amount == Decimal("-10000.00")
        assert new_invoice.total_amount == Decimal("10000.00")

        # 闸 1：原票被移动进已冲红/，根目录不许再有一份
        assert blue.invoice is not None
        assert blue.invoice.folder_subpath.startswith(f"{INVOICE_DIR}/已冲红/")
        assert (folder / blue.invoice.folder_subpath).is_file()
        assert not (folder / INVOICE_DIR / "发票（某某非诉专项）_20261110开具.pdf").exists()
        # 红票也落在已冲红/
        assert red_invoice.folder_subpath.startswith(f"{INVOICE_DIR}/已冲红/")
        assert "红字开具" in red_invoice.folder_subpath

        # 冲红 + 重开：净额回到 40000（-40000 与 +40000 相互抵消），状态仍是已开票
        payment.refresh_from_db()
        assert payment.invoiced_amount == Decimal("10000.00")
        assert payment.invoice_status == InvoiceStatus.INVOICED_FULL

        log = ContractFinanceLog.objects.filter(contract=contract, action="invoice_red_reenacted").first()
        assert log is not None
        assert log.payload["offset_invoice_number"] == BLUE_NUMBER

    def test_renact_without_new_invoice_leaves_voided_pending(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        folder: Path,
        lawyer: Lawyer,
    ) -> None:
        _blue, red, _reissue = self._setup(message, contract, payment, folder)
        confirm_red_reenact(red_intake_id=red.pk, new_intake_id=None, user=lawyer)
        payment.refresh_from_db()
        assert payment.invoice_status == InvoiceStatus.VOIDED_PENDING_REISSUE
        assert payment.invoiced_amount == Decimal("0.00")

    def test_full_cycle_with_reissue_returns_to_full(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        folder: Path,
        lawyer: Lawyer,
    ) -> None:
        _blue, red, reissue = self._setup(message, contract, payment, folder)
        confirm_red_reenact(red_intake_id=red.pk, new_intake_id=reissue.pk, user=lawyer)
        payment.refresh_from_db()
        assert payment.invoiced_amount == Decimal("10000.00")
        assert payment.invoice_status == InvoiceStatus.INVOICED_FULL


# ── 裁定层：G1–G6 守卫 ────────────────────────────────────────────


@pytest.mark.django_db
class TestRedGuards:
    def _red(
        self,
        message: InboxMessage,
        contract: Contract,
        *,
        amount: str | None = "-10000.00",
        offset: Invoice | None = None,
    ) -> InvoiceIntake:
        red = _intake(message, contract, number=RED_NUMBER, amount=amount, red_against=BLUE_NUMBER)
        if offset is not None:
            red.offset_invoice = offset
            red.save(update_fields=["offset_invoice"])
        return red

    def test_g1_offset_missing_rejected(
        self, media_root: Path, message: InboxMessage, contract: Contract, lawyer: Lawyer
    ) -> None:
        red = self._red(message, contract)
        with pytest.raises(ValidationException) as exc:
            confirm_red_reenact(red_intake_id=red.pk, new_intake_id=None, user=lawyer)
        assert exc.value.code == "INVOICE_RED_OFFSET_NOT_FOUND"

    def test_g2_contract_mismatch_rejected(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        lawyer: Lawyer,
    ) -> None:
        blue = _confirmed_blue(message, contract, payment=payment)
        other = ContractFactory(name="另一个项目")
        red = self._red(message, other, offset=blue.invoice)
        with pytest.raises(ValidationException) as exc:
            confirm_red_reenact(red_intake_id=red.pk, new_intake_id=None, user=lawyer)
        assert exc.value.code == "INVOICE_RED_CONTRACT_MISMATCH"

    def test_g3_reissue_must_be_positive(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        lawyer: Lawyer,
    ) -> None:
        blue = _confirmed_blue(message, contract, payment=payment)
        red = self._red(message, contract, offset=blue.invoice)
        reissue = _intake(message, contract, number=REISSUE_NUMBER, amount="0")
        with pytest.raises(ValidationException) as exc:
            confirm_red_reenact(red_intake_id=red.pk, new_intake_id=reissue.pk, user=lawyer)
        assert exc.value.code == "INVOICE_REENACT_NOT_POSITIVE"

    def test_g4_amount_mismatch_requires_override(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        lawyer: Lawyer,
    ) -> None:
        blue = _confirmed_blue(message, contract, payment=payment)
        red = self._red(message, contract, offset=blue.invoice)
        reissue = _intake(message, contract, number=REISSUE_NUMBER, amount="30000.00")
        with pytest.raises(ValidationException) as exc:
            confirm_red_reenact(red_intake_id=red.pk, new_intake_id=reissue.pk, user=lawyer)
        assert exc.value.code == "INVOICE_REENACT_AMOUNT_MISMATCH"

        confirm_red_reenact(
            red_intake_id=red.pk, new_intake_id=reissue.pk, user=lawyer, note="客户要求减额", amount_override=True
        )
        log = ContractFinanceLog.objects.filter(contract=contract, action="invoice_red_reenacted").first()
        assert log is not None
        assert log.payload["override"] is True
        assert log.payload["new_total_amount"] == "30000.00"

    def test_g5_duplicated_reissue_number_rejected(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        lawyer: Lawyer,
    ) -> None:
        blue = _confirmed_blue(message, contract, payment=payment)
        red = self._red(message, contract, offset=blue.invoice)
        reissue = _intake(message, contract, number=BLUE_NUMBER, amount="10000.00")
        with pytest.raises(ValidationException) as exc:
            confirm_red_reenact(red_intake_id=red.pk, new_intake_id=reissue.pk, user=lawyer)
        assert exc.value.code == "INVOICE_NUMBER_DUPLICATED"

    def test_g6_double_offset_rejected(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        lawyer: Lawyer,
    ) -> None:
        blue = _confirmed_blue(message, contract, payment=payment)
        first = self._red(message, contract, offset=blue.invoice)
        # 第一张红票先确认
        confirm_red_reenact(red_intake_id=first.pk, new_intake_id=None, user=lawyer)

        second = _intake(message, contract, number="66666666666666666666", amount="-10000.00", red_against=BLUE_NUMBER)
        second.offset_invoice = blue.invoice
        second.save(update_fields=["offset_invoice"])
        with pytest.raises(ValidationException) as exc:
            confirm_red_reenact(red_intake_id=second.pk, new_intake_id=None, user=lawyer)
        assert exc.value.code == "INVOICE_RED_ALREADY_APPLIED"

    def test_offset_amount_unknown_rejected(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        lawyer: Lawyer,
    ) -> None:
        blue = _confirmed_blue(message, contract, payment=payment)
        red = self._red(message, contract, amount=None, offset=blue.invoice)
        with pytest.raises(ValidationException) as exc:
            confirm_red_only(red_intake_id=red.pk, user=lawyer)
        assert exc.value.code == "INVOICE_RED_AMOUNT_UNKNOWN"


@pytest.mark.django_db
class TestConfirmInvoiceIntakeRedGuard:
    def test_plain_confirm_rejects_red(
        self, media_root: Path, message: InboxMessage, contract: Contract, lawyer: Lawyer
    ) -> None:
        """红票不得从老端点进（Service 层是唯一门，API 之外也要拦住）。"""
        red = _intake(message, contract, number=RED_NUMBER, amount="-10000.00", red_against=BLUE_NUMBER)
        with pytest.raises(ValidationException) as exc:
            confirm_invoice_intake(intake_id=red.pk, contract_id=contract.pk, payment_id=None, user=lawyer)
        assert exc.value.code == "INVOICE_RED_USE_DEDICATED_ENDPOINT"

    def test_plain_confirm_rejects_duplicated_number(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        lawyer: Lawyer,
    ) -> None:
        _confirmed_blue(message, contract, payment=payment)
        dup = _intake(message, contract, number=BLUE_NUMBER, amount="10000.00")
        with pytest.raises(ValidationException) as exc:
            confirm_invoice_intake(intake_id=dup.pk, contract_id=contract.pk, payment_id=payment.pk, user=lawyer)
        assert exc.value.code == "INVOICE_NUMBER_DUPLICATED"


# ── 裁定层：confirm_red_only ──────────────────────────────────────


@pytest.mark.django_db
class TestConfirmRedOnly:
    def test_red_only_moves_original_and_voids_pending(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        folder: Path,
        lawyer: Lawyer,
    ) -> None:
        blue = _confirmed_blue(message, contract, payment=payment)
        assert blue.invoice is not None
        original = folder / blue.invoice.folder_subpath
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(b"%PDF-1.4 original")

        red = _intake(message, contract, number=RED_NUMBER, amount="-10000.00", red_against=BLUE_NUMBER)
        red.offset_invoice = blue.invoice
        red.save(update_fields=["offset_invoice"])

        result = confirm_red_only(red_intake_id=red.pk, user=lawyer, note="客户不要这张票")

        red.refresh_from_db()
        blue.refresh_from_db()
        assert red.status == InvoiceIntakeStatus.CONFIRMED
        assert red.decision_note == "客户不要这张票"
        assert result["new_invoice_id"] is None
        assert blue.invoice is not None
        # folder_subpath 是 query-set update 写的，必须 reload 才看得到
        blue.invoice.refresh_from_db()
        assert blue.invoice.folder_subpath.startswith(f"{INVOICE_DIR}/已冲红/")
        payment.refresh_from_db()
        assert payment.invoice_status == InvoiceStatus.VOIDED_PENDING_REISSUE


# ── 裁定层：整组撤销 ──────────────────────────────────────────────


@pytest.mark.django_db
class TestReopenRedGroup:
    def test_reopen_from_red_rolls_back_whole_group(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        folder: Path,
        lawyer: Lawyer,
    ) -> None:
        blue = _confirmed_blue(message, contract, payment=payment)
        assert blue.invoice is not None
        original = folder / blue.invoice.folder_subpath
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(b"%PDF-1.4 original")
        red = _intake(message, contract, number=RED_NUMBER, amount="-10000.00", red_against=BLUE_NUMBER)
        red.offset_invoice = blue.invoice
        red.save(update_fields=["offset_invoice"])
        reissue = _intake(message, contract, number=REISSUE_NUMBER, amount="10000.00")
        confirm_red_reenact(red_intake_id=red.pk, new_intake_id=reissue.pk, user=lawyer)

        blue.refresh_from_db()
        voided_subpath = blue.invoice.folder_subpath
        assert voided_subpath.startswith(f"{INVOICE_DIR}/已冲红/")

        reopen_invoice_intake(intake_id=red.pk, user=lawyer)

        red.refresh_from_db()
        reissue.refresh_from_db()
        blue.refresh_from_db()
        assert red.status == InvoiceIntakeStatus.PENDING
        assert red.invoice_id is None
        assert reissue.status == InvoiceIntakeStatus.PENDING
        assert reissue.invoice_id is None
        assert reissue.supersedes_intake_id is None

        # 红票/重开票的 Invoice 记录已删，原票记录还在
        assert not Invoice.objects.filter(invoice_number__in=[RED_NUMBER, REISSUE_NUMBER]).exists()
        assert blue.invoice is not None
        # 原票从已冲红/ 移回发票目录，folder_subpath 同步更新
        assert blue.invoice.folder_subpath == f"{INVOICE_DIR}/发票（某某非诉专项）_20261110开具.pdf"
        assert (folder / blue.invoice.folder_subpath).is_file()
        assert not (folder / voided_subpath).exists()

        payment.refresh_from_db()
        assert payment.invoiced_amount == Decimal("10000.00")
        assert payment.invoice_status == InvoiceStatus.INVOICED_FULL

    def test_reopen_from_reissue_rolls_back_same_group(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        folder: Path,
        lawyer: Lawyer,
    ) -> None:
        blue = _confirmed_blue(message, contract, payment=payment)
        assert blue.invoice is not None
        original = folder / blue.invoice.folder_subpath
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(b"%PDF-1.4 original")
        red = _intake(message, contract, number=RED_NUMBER, amount="-10000.00", red_against=BLUE_NUMBER)
        red.offset_invoice = blue.invoice
        red.save(update_fields=["offset_invoice"])
        reissue = _intake(message, contract, number=REISSUE_NUMBER, amount="10000.00")
        confirm_red_reenact(red_intake_id=red.pk, new_intake_id=reissue.pk, user=lawyer)

        # 从重开蓝票点撤销 → 走同一组，结果必须与从红票撤销一致（红票那端也要回到 pending）
        reopened = reopen_invoice_intake(intake_id=reissue.pk, user=lawyer)
        assert reopened.pk == red.pk
        red.refresh_from_db()
        reissue.refresh_from_db()
        assert red.status == InvoiceIntakeStatus.PENDING
        assert reissue.status == InvoiceIntakeStatus.PENDING
        assert not Invoice.objects.filter(invoice_number__in=[RED_NUMBER, REISSUE_NUMBER]).exists()


# ── 归档闸 3：两个消费者都要挡 ────────────────────────────────────


@pytest.mark.django_db
class TestArchiveVoidedFilters:
    def test_download_handler_filters_voided_invoice(
        self, contract: Contract, payment: ContractPayment, message: InboxMessage, media_root: Path
    ) -> None:
        from apps.contracts.models import FinalizedMaterial, MaterialCategory
        from apps.contracts.services.archive.category_mapping import get_archive_category

        (media_root / "contracts/materials").mkdir(parents=True)
        (media_root / "contracts/materials/keep.pdf").write_bytes(b"%PDF keep")
        (media_root / "contracts/materials/red.pdf").write_bytes(b"%PDF red")
        code = self._invoice_item_code(contract)
        keep = FinalizedMaterial.objects.create(
            contract=contract,
            category=MaterialCategory.INVOICE,
            file_path="contracts/materials/keep.pdf",
            original_filename="发票（某某案）_20261111开具.pdf",
        )
        FinalizedMaterial.objects.create(
            contract=contract,
            category=MaterialCategory.INVOICE,
            file_path="contracts/materials/red.pdf",
            original_filename="发票（某某案）_20261111红字开具.pdf",
            archive_item_code=code,
        )
        assert get_archive_category(contract.case_type)
        result = _download_uploaded_item(contract, code)
        # 单张有效票 → 直接返回该文件；红票没被合并进卷宗
        assert result.get("filename") == keep.original_filename

    def test_material_mapping_skips_voided_invoice(self, contract: Contract, db: Any) -> None:
        from apps.contracts.models import FinalizedMaterial, MaterialCategory

        valid = FinalizedMaterial.objects.create(
            contract=contract,
            category=MaterialCategory.INVOICE,
            file_path="contracts/materials/a.pdf",
            original_filename="发票（某某案）_20261111开具.pdf",
        )
        FinalizedMaterial.objects.create(
            contract=contract,
            category=MaterialCategory.INVOICE,
            file_path="contracts/materials/b.pdf",
            original_filename="发票（某某案）_20261111红字开具.pdf",
        )
        from apps.contracts.services.archive.category_mapping import get_archive_category

        category = get_archive_category(contract.case_type)
        materials = list(FinalizedMaterial.objects.filter(contract=contract))
        result = map_contract_materials(category, materials)
        all_ids = [mid for ids in result.values() for mid in ids]
        assert valid.id in all_ids
        assert len(all_ids) == 1

    def test_looks_voided_predicate(self) -> None:
        class _M:
            original_filename = "发票（某某案）_20261111红字开具.pdf"

        assert _looks_voided(_M()) is True  # type: ignore[arg-type]

    @staticmethod
    def _invoice_item_code(contract: Contract) -> str:
        from apps.contracts.services.archive.category_mapping import get_archive_category
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_name

        code = find_code_by_name(get_archive_category(contract.case_type), "收费凭证")
        assert code
        return code


# ── 归档闸 2：导入流水线不导入作废票 ──────────────────────────────


@pytest.mark.django_db
class TestImportPipelineVoided:
    def test_voided_candidate_not_imported(self, tmp_path: Path, contract: Contract) -> None:
        from unittest.mock import MagicMock

        from apps.contracts.models.folder_scan_session import ContractFolderScanStatus

        red_file = tmp_path / "发票（某某案）_20261111红字开具.pdf"
        red_file.write_bytes(b"%PDF red")

        session = MagicMock()
        session.id = 1
        session.status = ContractFolderScanStatus.COMPLETED
        session.result_payload = {"candidates": [{"source_path": str(red_file)}]}
        session.started_by_id = None

        pipeline = ImportPipeline()
        from unittest.mock import patch

        module = "apps.contracts.services.contract.integrations._import_pipeline"
        with (
            patch(f"{module}.FinalizedMaterial") as material_model,
            patch(f"{module}.ContractFolderScanSession"),
            patch(f"{module}.compute_file_hash_from_bytes", return_value="a" * 64),
        ):
            result = pipeline.confirm_import(
                contract_id=contract.pk,
                session=session,
                items=[{"source_path": str(red_file), "selected": True, "category": "invoice"}],
            )
        assert result["skipped_voided"] == 1
        assert result["imported_count"] == 0
        material_model.objects.create.assert_not_called()


# ── 作废派生（不落字段）───────────────────────────────────────────


@pytest.mark.django_db
class TestInvoiceVoidedBy:
    def test_voided_by_returns_confirmed_red_invoice(
        self,
        media_root: Path,
        message: InboxMessage,
        contract: Contract,
        payment: ContractPayment,
        lawyer: Lawyer,
    ) -> None:
        blue = _confirmed_blue(message, contract, payment=payment)
        assert blue.invoice is not None
        assert invoice_voided_by(blue.invoice) is None
        assert is_voided(blue.invoice) is False

        red = _intake(message, contract, number=RED_NUMBER, amount="-10000.00", red_against=BLUE_NUMBER)
        red.offset_invoice = blue.invoice
        red.save(update_fields=["offset_invoice"])
        confirm_red_only(red_intake_id=red.pk, user=lawyer)

        red.refresh_from_db()
        assert red.invoice_id is not None
        voided_by = invoice_voided_by(Invoice.objects.get(pk=blue.invoice_id))
        assert voided_by is not None
        assert voided_by.pk == red.invoice_id
