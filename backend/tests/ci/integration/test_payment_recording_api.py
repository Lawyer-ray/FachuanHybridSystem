"""记收款链路集成测试：到账短信识别 + 发票拖拽落库。

跑在测试库（``DB_NAME=test_fachuan_dev``），覆盖：

1. `POST /finance/payments/parse-text` —— 真实短信原样进、草稿出，**不落库**；
2. `POST /finance/payments/{id}/invoices` —— 识别字段落库、开票金额回填、
   文件进 media；重复发票号只提示不重复计额；坏文件单独失败；OCR 挂了仍存票；
3. `DELETE /finance/invoices/{id}` —— 删除后开票金额回落。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.contracts.models import Contract, ContractPayment, Invoice, InvoiceStatus

SMS = (
    "【建设银行】丙方不锈钢有限公司10月14日14时17分"
    "向贵公司4501账户律师费存入人民币30000元。"
)


@pytest.fixture()
def contract(db: None) -> Contract:
    return Contract.objects.create(name="记收款测试合同", case_type="civil", fixed_amount=Decimal("100000"))


@pytest.fixture()
def payment(contract: Contract) -> ContractPayment:
    return ContractPayment.objects.create(contract=contract, amount=Decimal("30000"), received_at=date(2026, 10, 14))


def _parsed(*, number: str = "24442000000123456789", total: str = "30000.00") -> Any:
    data = MagicMock()
    data.invoice_code = ""
    data.invoice_number = number
    data.invoice_date = date(2026, 10, 14)
    data.amount = Decimal("28301.89")
    data.tax_amount = Decimal("1698.11")
    data.total_amount = Decimal(total)
    data.buyer_name = "广东某律师事务所"
    data.seller_name = "佛山市某酒店"
    data.project_name = "餐饮服务"
    data.category = "vat_electronic"
    return data


def _upload(name: str = "invoice.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"%PDF-1.4 fake", content_type="application/pdf")


def _mock_recognizer(parsed: Any = None, *, error: Exception | None = None) -> Any:
    result = MagicMock(success=True, data=parsed, error=None)
    svc = MagicMock()
    if error is not None:
        svc.recognize_files.side_effect = error
    else:
        svc.recognize_files.return_value = [result]
    return svc


# ============================================================ 短信识别


@pytest.mark.django_db
def test_parse_text_returns_draft_without_persisting(authenticated_client, payment: ContractPayment) -> None:
    resp = authenticated_client.post(
        "/api/v1/contracts/finance/payments/parse-text",
        data={"text": SMS},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["amount"] == "30000.00"
    assert body["received_at"] == "2026-10-14"
    assert body["payer"] == "丙方不锈钢有限公司"
    assert body["note"] == "律师费"
    assert body["hints"]
    # 只解析不落库
    assert ContractPayment.objects.count() == 1


@pytest.mark.django_db
def test_parse_text_unrecognized_amount_is_null(authenticated_client) -> None:
    resp = authenticated_client.post(
        "/api/v1/contracts/finance/payments/parse-text",
        data={"text": "银行通知：请核对您的账户"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["amount"] is None
    assert body["received_at"] is None


# ============================================================ 发票上传


@pytest.mark.django_db
@patch("apps.invoice_recognition.services.wiring.get_quick_recognition_service")
def test_upload_invoice_fills_fields_and_invoiced_amount(
    mock_svc_factory: Any, authenticated_client, payment: ContractPayment
) -> None:
    mock_svc_factory.return_value = _mock_recognizer(_parsed())

    resp = authenticated_client.post(
        f"/api/v1/contracts/finance/payments/{payment.id}/invoices",
        {"files": _upload()},
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()

    assert len(body["saved"]) == 1
    assert not body["failed"]
    saved = body["saved"][0]
    assert saved["total_amount"] == "30000.00"
    assert saved["invoice_number"] == "24442000000123456789"
    assert saved["invoice_date"] == "2026-10-14"

    invoice = Invoice.objects.get(pk=saved["id"])
    assert invoice.payment_id == payment.id
    assert invoice.file_path.startswith("contracts/invoices/")
    assert invoice.total_amount == Decimal("30000.00")

    payment.refresh_from_db()
    assert payment.invoiced_amount == Decimal("30000")
    assert payment.invoice_status == InvoiceStatus.INVOICED_FULL
    assert body["invoice_status"] == InvoiceStatus.INVOICED_FULL


@pytest.mark.django_db
@patch("apps.invoice_recognition.services.wiring.get_quick_recognition_service")
def test_duplicate_invoice_number_does_not_double_count(
    mock_svc_factory: Any, authenticated_client, payment: ContractPayment
) -> None:
    mock_svc_factory.return_value = _mock_recognizer(_parsed())

    url = f"/api/v1/contracts/finance/payments/{payment.id}/invoices"
    first = authenticated_client.post(url, {"files": _upload("a.pdf")}).json()
    second = authenticated_client.post(url, {"files": _upload("b.pdf")}).json()

    assert first["duplicated_count"] == 0
    assert second["duplicated_count"] == 1
    # 两张票都存下来（律师要能看到原件），但开票金额只算一次
    assert Invoice.objects.filter(payment=payment).count() == 2
    payment.refresh_from_db()
    assert payment.invoiced_amount == Decimal("30000")


@pytest.mark.django_db
@patch("apps.invoice_recognition.services.wiring.get_quick_recognition_service")
def test_bad_file_fails_alone(mock_svc_factory: Any, authenticated_client, payment: ContractPayment) -> None:
    mock_svc_factory.return_value = _mock_recognizer(_parsed())

    resp = authenticated_client.post(
        f"/api/v1/contracts/finance/payments/{payment.id}/invoices",
        {"files": [_upload(), SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")]},
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert len(body["saved"]) == 1
    assert len(body["failed"]) == 1
    assert "virus.exe" in body["failed"][0]["filename"]


@pytest.mark.django_db
@patch("apps.invoice_recognition.services.wiring.get_quick_recognition_service")
def test_recognition_failure_still_stores_file(
    mock_svc_factory: Any, authenticated_client, payment: ContractPayment
) -> None:
    """OCR 认不出来也要把发票存下来——能否入账取决于有没有票，不取决于 OCR。"""
    mock_svc_factory.return_value = _mock_recognizer(error=RuntimeError("ocr down"))

    resp = authenticated_client.post(
        f"/api/v1/contracts/finance/payments/{payment.id}/invoices",
        {"files": _upload()},
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert len(body["saved"]) == 1
    assert body["saved"][0]["total_amount"] is None
    assert Invoice.objects.filter(payment=payment).count() == 1


@pytest.mark.django_db
@patch("apps.invoice_recognition.services.wiring.get_quick_recognition_service")
def test_invoiced_amount_capped_at_payment_amount(
    mock_svc_factory: Any, authenticated_client, payment: ContractPayment
) -> None:
    """发票合计超过收款金额时按收款金额封顶（模型约束不允许开票额大于收款额）。"""
    mock_svc_factory.return_value = _mock_recognizer(_parsed(number="11111111111111111111", total="40000.00"))

    authenticated_client.post(
        f"/api/v1/contracts/finance/payments/{payment.id}/invoices",
        {"files": _upload()},
    )
    payment.refresh_from_db()
    assert payment.invoiced_amount == Decimal("30000")
    assert payment.invoice_status == InvoiceStatus.INVOICED_FULL


@pytest.mark.django_db
@patch("apps.invoice_recognition.services.wiring.get_quick_recognition_service")
def test_delete_invoice_recomputes_amount(
    mock_svc_factory: Any, authenticated_client, payment: ContractPayment
) -> None:
    mock_svc_factory.return_value = _mock_recognizer(_parsed())

    saved = (
        authenticated_client.post(
            f"/api/v1/contracts/finance/payments/{payment.id}/invoices",
            {"files": _upload()},
        )
        .json()["saved"][0]
    )
    resp = authenticated_client.delete(f"/api/v1/contracts/finance/invoices/{saved['id']}")
    assert resp.status_code == 200, resp.content
    assert not Invoice.objects.filter(pk=saved["id"]).exists()
    payment.refresh_from_db()
    assert payment.invoiced_amount == Decimal("0")
    assert payment.invoice_status == InvoiceStatus.UNINVOICED


@pytest.mark.django_db
def test_list_payment_invoices(authenticated_client, contract: Contract, payment: ContractPayment) -> None:
    Invoice.objects.create(payment=payment, file_path="contracts/invoices/1/a.pdf", original_filename="a.pdf")
    resp = authenticated_client.get(
        f"/api/v1/contracts/finance/payments/{payment.id}/invoices",
        {"contract_id": contract.id},
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert len(body) == 1
    assert body[0]["original_filename"] == "a.pdf"
