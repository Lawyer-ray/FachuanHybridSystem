"""发票待认领扫描层的红票与入池判据（D2 / D8）。

## 锁定的行为

1. **入池判据收窄**：裸「请查收」不再算发票邮件（实测把「品质异常联络函 + 检验报告」
   判成了发票），但「1 张票 + 1 份报告」的邮件里票必须进来。
2. **红票事实落库**：`red_against_number` / `red_confirmation_no` 随解析写进 intake，
   原蓝票号命中本库 `Invoice` 时写 `offset_invoice`。
3. **配对幂等**：`_refresh_red_links` 把「重开蓝票 → 被替代的原票 intake」写进
   `supersedes_intake`，重复跑不产生变化（红票与蓝票谁先入池都要能配上）。
4. **回填重解析**：`scan_since` 对 `total_amount IS NULL` 的历史 pending 重跑解析，
   **只补空字段**，不覆盖人工已改的值。

## PDF 而不是假解析结果

`_deeper_parse` 走真实的 pdfplumber + `InvoiceParser`，所以这里用一份**单页的真实红票
文本**在 `tmp_path` 里现场生成 PDF（不落二进制 fixture、不依赖测试机上的媒体目录），
让「负号解析 + 红票事实」在扫描层也走一遍真链路。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from django.utils import timezone

from apps.contracts.models import Contract, ContractPayment, Invoice, InvoiceIntake, InvoiceIntakeStatus
from apps.contracts.services.payment import invoice_intake_scanner as scanner
from apps.message_hub.models import InboxMessage, MessageSource

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

#: 真实红票（单页版式，字段取自 pdfplumber 实读结果）
RED_INVOICE_TEXT = """电子发票（普通发票）
发票号码：12345678901234567890
开票日期：2026年11月11日
购 名称：某甲（个人） 销 名称：某某律师事务所
买 售
方 方
*生产生活服务*法律咨询 项 -1 9433.9622641509 -9433.96 6% -566.04
合 计 ¥-9433.96 ¥-566.04
价税合计（大写） （负数）肆万圆整 （小写）¥-10000.00
备
注
被红冲蓝字数电发票号码：11111111111111111111 红字发票信息确认单编号：22222222222222222222;
0000GZF0001-某甲非诉专项
开票人：张婧"""

ORIGINAL_NUMBER = "11111111111111111111"
RED_NUMBER = "12345678901234567890"
REISSUE_NUMBER = "99999999999999999999"
PROJECT_CODE = "0000GZF0001"


def _write_pdf(target: Path, text: str) -> Path:
    """把文本渲染成一份最小 PDF（真实 pdfplumber 可读）。

    中文字体（STSong-Light，报告自带 CID）是为了让 ``extract_text()`` 吐回原文：
    扫描层的判据全是中文关键词，用默认 Helvetica 只会写出乱码。
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(target))
    pdf.setFont("STSong-Light", 9)
    y = 820
    for line in text.splitlines():
        pdf.drawString(30, y, line)
        y -= 13
    pdf.save()
    return target


@pytest.fixture
def source(db) -> MessageSource:
    return MessageSource.objects.create(display_name="财务邮箱", sync_since=timezone.now())


def _message(source: MessageSource, **kwargs: Any) -> InboxMessage:
    base: dict[str, Any] = {
        "source": source,
        "message_id": f"msg-{InboxMessage.objects.count() + 1}",
        "subject": "发票已开具",
        "sender": "finance@example.com",
        "received_at": timezone.now(),
        "body_text": "发票已开具，详见附件。",
        "attachments_meta": [],
    }
    base.update(kwargs)
    return InboxMessage.objects.create(**base)


def _pdf_att(filename: str, path: Path, part_index: int = 0) -> dict[str, Any]:
    return {
        "filename": filename,
        "original_filename": filename,
        "content_type": "application/pdf",
        "local_path": str(path),
        "part_index": part_index,
    }


class TestInvoiceMailCriterion:
    """D8：入池判据的 4 态表 + 否决规则的「全部命中才生效」。"""

    def test_bare_qingchashou_is_not_an_invoice_mail(self, source: MessageSource) -> None:
        message = _message(
            source,
            subject="品质异常联络函",
            body_text="附件为检验结果，请查收。",
            attachments_meta=[{"filename": "70mm²红色硅胶线产品检验报告.pdf", "content_type": "application/pdf"}],
        )

        assert scanner.is_invoice_mail(message) is False

    def test_subject_hit_wins_even_without_attachments(self, source: MessageSource) -> None:
        assert scanner.is_invoice_mail(_message(source, subject="11月发票已开具", body_text="")) is True

    def test_dzfp_filename_counts(self, source: MessageSource) -> None:
        message = _message(
            source,
            subject="请查收",
            body_text="请查收",
            attachments_meta=[{"filename": f"dzfp_{RED_NUMBER}_某甲（个人）.pdf", "content_type": "application/pdf"}],
        )

        assert scanner.is_invoice_mail(message) is True

    def test_open_notice_in_body_requires_a_pdf_attachment(self, source: MessageSource) -> None:
        # 主题刻意不含「发票/开票」：否则走主题分支，测不到正文分支的 PDF 前置条件
        with_pdf = _message(
            source,
            subject="11月票据对接",
            body_text="发票请查收。",
            attachments_meta=[{"filename": "发票（某合同）_20261111开具.pdf", "content_type": "application/pdf"}],
        )
        without_pdf = _message(
            source,
            subject="11月票据对接",
            body_text="发票请查收。",
            attachments_meta=[{"filename": "说明.docx", "content_type": "application/msword"}],
        )

        assert scanner.is_invoice_mail(with_pdf) is True
        assert scanner.is_invoice_mail(without_pdf) is False

    def test_all_pdf_attachments_vetoed_blocks_the_mail(self, source: MessageSource) -> None:
        message = _message(
            source,
            subject="发票对账",
            attachments_meta=[
                {"filename": "产品检验报告.pdf", "content_type": "application/pdf"},
                {"filename": "燃烧测试报告.pdf", "content_type": "application/pdf"},
            ],
        )

        assert scanner.is_invoice_mail(message) is False

    def test_one_real_invoice_defeats_the_veto(self, source: MessageSource) -> None:
        # 一封带「1 张发票 + 1 份报告」的邮件里，票必须进来
        message = _message(
            source,
            subject="发票与检测报告",
            attachments_meta=[
                {"filename": "70mm²红色硅胶线产品检验报告.pdf", "content_type": "application/pdf"},
                {"filename": f"dzfp_{RED_NUMBER}_某甲（个人）.pdf", "content_type": "application/pdf"},
            ],
        )

        assert scanner.is_invoice_mail(message) is True


class TestRedFactsPersisted:
    """红票事实落库 + offset_invoice 命中。"""

    def test_scan_red_invoice_persists_facts_and_offset(self, source: MessageSource, tmp_path: Path) -> None:
        original = _create_invoice(ORIGINAL_NUMBER, Decimal("10000.00"))
        pdf_path = _write_pdf(tmp_path / "red.pdf", RED_INVOICE_TEXT)
        message = _message(
            source,
            attachments_meta=[_pdf_att(f"4_dzfp_{RED_NUMBER}_某甲（个人）_20261111172206-某丙-红票.pdf", pdf_path)],
        )

        created = scanner.scan_message(message)

        assert len(created) == 1
        intake = InvoiceIntake.objects.get(pk=created[0].pk)
        assert intake.total_amount == Decimal("-10000.00")
        assert intake.red_against_number == ORIGINAL_NUMBER
        assert intake.red_confirmation_no == "22222222222222222222"
        assert intake.offset_invoice_id == original.pk
        assert intake.is_red is True

    def test_missing_original_leaves_offset_empty(self, source: MessageSource, tmp_path: Path) -> None:
        pdf_path = _write_pdf(tmp_path / "red.pdf", RED_INVOICE_TEXT)
        message = _message(source, attachments_meta=[_pdf_att("红票.pdf", pdf_path)])

        created = scanner.scan_message(message)

        intake = InvoiceIntake.objects.get(pk=created[0].pk)
        assert intake.red_against_number == ORIGINAL_NUMBER
        assert intake.offset_invoice_id is None

    def test_red_invoice_never_preselects_a_payment(self, source: MessageSource, tmp_path: Path) -> None:
        contract = _create_contract(source)  # 项目号命中 → 才谈得上选收款
        ContractPayment.objects.create(contract=contract, amount=Decimal("10000.00"), received_at=date(2026, 11, 10))
        pdf_path = _write_pdf(tmp_path / "red.pdf", RED_INVOICE_TEXT)
        message = _message(source, attachments_meta=[_pdf_att("红票.pdf", pdf_path)])

        created = scanner.scan_message(message)

        intake = InvoiceIntake.objects.get(pk=created[0].pk)
        assert intake.suggested_payment_id is None
        assert intake.match_snapshot["payment_pick"]["confidence"] == "red_unmatched"


class TestRefreshRedLinks:
    """§3.3：配对只认红票证据，一对一，幂等。"""

    def test_reissue_is_linked_to_the_confirmed_original(self, db: object) -> None:
        original_intake = _create_intake(
            status=InvoiceIntakeStatus.CONFIRMED, invoice_number=ORIGINAL_NUMBER, total_amount=Decimal("10000.00")
        )
        _create_intake(invoice_number=RED_NUMBER, total_amount=Decimal("-10000.00"), red_against_number=ORIGINAL_NUMBER)
        reissue = _create_intake(invoice_number=REISSUE_NUMBER, total_amount=Decimal("10000.00"))

        changed = scanner._refresh_red_links(PROJECT_CODE)

        assert changed >= 1
        reissue.refresh_from_db()
        assert reissue.supersedes_intake_id == original_intake.pk

    def test_is_idempotent(self, db: object) -> None:
        _create_intake(
            status=InvoiceIntakeStatus.CONFIRMED, invoice_number=ORIGINAL_NUMBER, total_amount=Decimal("10000.00")
        )
        _create_intake(invoice_number=RED_NUMBER, total_amount=Decimal("-10000.00"), red_against_number=ORIGINAL_NUMBER)
        _create_intake(invoice_number=REISSUE_NUMBER, total_amount=Decimal("10000.00"))

        scanner._refresh_red_links(PROJECT_CODE)
        second = scanner._refresh_red_links(PROJECT_CODE)

        assert second == 0

    def test_amount_mismatch_does_not_link(self, db: object) -> None:
        # 重开改为部分金额是合法业务，不能自动判「替代」——猜测会误杀分期票
        _create_intake(
            status=InvoiceIntakeStatus.CONFIRMED, invoice_number=ORIGINAL_NUMBER, total_amount=Decimal("10000.00")
        )
        _create_intake(invoice_number=RED_NUMBER, total_amount=Decimal("-10000.00"), red_against_number=ORIGINAL_NUMBER)
        reissue = _create_intake(invoice_number=REISSUE_NUMBER, total_amount=Decimal("20000.00"))

        scanner._refresh_red_links(PROJECT_CODE)

        reissue.refresh_from_db()
        assert reissue.supersedes_intake_id is None

    def test_two_reissues_do_not_share_one_original(self, db: object) -> None:
        original = _create_intake(
            status=InvoiceIntakeStatus.CONFIRMED, invoice_number=ORIGINAL_NUMBER, total_amount=Decimal("10000.00")
        )
        _create_intake(invoice_number=RED_NUMBER, total_amount=Decimal("-10000.00"), red_against_number=ORIGINAL_NUMBER)
        first = _create_intake(invoice_number=REISSUE_NUMBER, total_amount=Decimal("10000.00"))
        second = _create_intake(invoice_number="88888888888888888888", total_amount=Decimal("10000.00"))

        scanner._refresh_red_links(PROJECT_CODE)

        first.refresh_from_db()
        second.refresh_from_db()
        # 一对一：同一条原票只能被一张重开票认领（按 id 先到先得，结果可重现）
        assert first.supersedes_intake_id == original.pk
        assert second.supersedes_intake_id is None

    def test_empty_project_code_is_a_noop(self, db: object) -> None:
        assert scanner._refresh_red_links("") == 0


class TestBackfillReparse:
    """回填：只补空字段，不覆盖非空。"""

    def test_blank_amount_is_filled_from_pdf(self, tmp_path: Path, db: object) -> None:
        pdf_path = _write_pdf(tmp_path / "red.pdf", RED_INVOICE_TEXT)
        intake = _create_intake(
            invoice_number=RED_NUMBER,
            total_amount=None,
            attachment_path=str(pdf_path),
            original_filename="红票.pdf",
        )

        scanner._backfill_missing_amounts()

        intake.refresh_from_db()
        assert intake.total_amount == Decimal("-10000.00")
        assert intake.red_against_number == ORIGINAL_NUMBER

    def test_non_empty_fields_are_not_overwritten(self, tmp_path: Path, db: object) -> None:
        pdf_path = _write_pdf(tmp_path / "red.pdf", RED_INVOICE_TEXT)
        intake = _create_intake(
            invoice_number=RED_NUMBER,
            total_amount=None,
            attachment_path=str(pdf_path),
            original_filename="红票.pdf",
            red_confirmation_no="人工录入的确认单号",
        )

        scanner._backfill_missing_amounts()

        intake.refresh_from_db()
        assert intake.red_confirmation_no == "人工录入的确认单号"

    def test_confirmed_intakes_are_not_backfilled(self, tmp_path: Path, db: object) -> None:
        pdf_path = _write_pdf(tmp_path / "red.pdf", RED_INVOICE_TEXT)
        intake = _create_intake(
            invoice_number=REISSUE_NUMBER,
            total_amount=None,
            attachment_path=str(pdf_path),
            original_filename="红票.pdf",
            status=InvoiceIntakeStatus.CONFIRMED,
        )

        scanner._backfill_missing_amounts()

        intake.refresh_from_db()
        assert intake.total_amount is None

    def test_scan_since_returns_touched_projects_of_backfill(self, tmp_path: Path, source: MessageSource) -> None:
        # 回填不新增返回键（ScanOut / 前端已按 scanned|created|days 消费），
        # 只把「被回填的项目」交给配对重算
        pdf_path = _write_pdf(tmp_path / "red.pdf", RED_INVOICE_TEXT)
        _create_intake(
            source=source,
            invoice_number=RED_NUMBER,
            total_amount=None,
            attachment_path=str(pdf_path),
            original_filename="红票.pdf",
        )

        touched = scanner._backfill_missing_amounts()
        result = scanner.scan_since(days=1)

        assert touched == {PROJECT_CODE}
        assert set(result) == {"scanned", "created", "days"}


# ── fixtures 工厂 ─────────────────────────────────────────


def _create_contract(source: MessageSource) -> Contract:
    return Contract.objects.create(
        name="某甲非诉专项",
        law_firm_oa_case_number=PROJECT_CODE,
        status="active",
    )


def _create_invoice(invoice_number: str, total_amount: Decimal) -> Invoice:
    contract = Contract.objects.create(
        name="某甲非诉专项",
        law_firm_oa_case_number=PROJECT_CODE,
        status="active",
    )
    return Invoice.objects.create(
        contract=contract,
        file_path=f"invoices/{invoice_number}.pdf",
        original_filename=f"{invoice_number}.pdf",
        invoice_number=invoice_number,
        total_amount=total_amount,
    )


def _create_intake(
    *,
    source: MessageSource | None = None,
    inbox_message: InboxMessage | None = None,
    invoice_number: str,
    total_amount: Decimal | None,
    status: str = InvoiceIntakeStatus.PENDING,
    red_against_number: str = "",
    red_confirmation_no: str = "",
    attachment_path: str = "",
    original_filename: str = "票.pdf",
) -> InvoiceIntake:
    if inbox_message is None:
        inbox_message = _message(source or MessageSource.objects.first() or _create_source())
    return InvoiceIntake.objects.create(
        inbox_message=inbox_message,
        part_index=InvoiceIntake.objects.count(),
        dedupe_key=f"k-{InvoiceIntake.objects.count() + 1}",
        invoice_number=invoice_number,
        total_amount=total_amount,
        status=status,
        project_code=PROJECT_CODE,
        red_against_number=red_against_number,
        red_confirmation_no=red_confirmation_no,
        attachment_path=attachment_path,
        original_filename=original_filename,
    )


def _create_source() -> MessageSource:
    return MessageSource.objects.create(display_name="财务邮箱", sync_since=timezone.now())
