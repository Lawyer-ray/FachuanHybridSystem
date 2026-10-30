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

SMS = "【建设银行】丙方不锈钢有限公司10月14日14时17分向贵公司4501账户律师费存入人民币30000元。"


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

    saved = authenticated_client.post(
        f"/api/v1/contracts/finance/payments/{payment.id}/invoices",
        {"files": _upload()},
    ).json()["saved"][0]
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


# ============================================================ 命名：发票（合同名称）_日期开具


def test_display_filename_follows_firm_convention() -> None:
    """沿用律所手工命名：`发票（{合同/案件名称}）_20260917开具.pdf`。"""
    from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

    svc = InvoiceFileService()
    case_name = "某铝业公司执行某建材公司、王某买卖合同纠纷一案"  # privacy-allow 虚构案名
    assert (
        svc.display_filename(contract_name=case_name, inv_date=date(2026, 10, 16), ext=".pdf")
        == f"发票（{case_name}）_20261016开具.pdf"
    )
    # 合同名缺失：退销售方；销售方也没有：日期兜底；日期也没有：只有「发票」
    assert svc.display_filename(contract_name="", seller="佛山市某酒店", inv_date=date(2026, 9, 17), ext=".pdf") == (
        "发票（佛山市某酒店）_20260917开具.pdf"
    )
    assert svc.display_filename(contract_name="", inv_date=date(2026, 9, 17), ext=".pdf") == "发票_20260917开具.pdf"
    assert svc.display_filename(contract_name="", seller="佛山市某酒店", inv_date=None, ext=".pdf") == "发票（佛山市某酒店）.pdf"
    assert svc.display_filename(contract_name="", inv_date=None, ext=".jpg") == "发票.jpg"
    # 文件名里的非法字符被清掉（名称带冒号/斜杠的极端脏数据）
    assert "：" not in svc.display_filename(contract_name="a:b*c?", inv_date=date(2026, 9, 17), ext=".pdf")
    # 超长合同名按 UTF-8 字节截断：整名不得超过 macOS 255 字节文件名上限
    long_name = "超长案名" * 40  # 160 字 = 480 字节
    out = svc.display_filename(contract_name=long_name, inv_date=date(2026, 10, 16), ext=".pdf")
    assert len(out.encode("utf-8")) <= 255
    assert out.startswith("发票（超长案名") and out.endswith("_20261016开具.pdf")


def test_invoice_dir_detection() -> None:
    """`发票` / `3-发票` 认；`发票领取台账` / 名字过长的不误认。"""
    from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

    assert InvoiceFileService._is_invoice_dir("发票")
    assert InvoiceFileService._is_invoice_dir("3-发票")
    assert InvoiceFileService._is_invoice_dir(" 1-律师资料发票 ")
    assert not InvoiceFileService._is_invoice_dir("发票领取台账")
    assert not InvoiceFileService._is_invoice_dir("发票领取台账2026年第一季度整理版汇总")


# ============================================================ 先开票后付款


@pytest.mark.django_db
@patch("apps.invoice_recognition.services.wiring.get_quick_recognition_service")
def test_upload_invoice_before_payment_lands_on_contract(
    mock_svc_factory: Any, authenticated_client, contract: Contract
) -> None:
    """先开票：票挂合同名下，不动开票金额（还没有收款可动）。"""
    mock_svc_factory.return_value = _mock_recognizer(_parsed())

    resp = authenticated_client.post(
        f"/api/v1/contracts/finance/contracts/{contract.id}/invoices", {"files": _upload()}
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert len(body["saved"]) == 1
    assert body["saved"][0]["payment_id"] is None
    assert body["saved"][0]["display_filename"] == "发票（记收款测试合同）_20261014开具.pdf"
    assert body["invoice_status"] == ""  # 没关联收款，无开票状态可回

    invoice = Invoice.objects.get(pk=body["saved"][0]["id"])
    assert invoice.payment_id is None
    assert invoice.contract_id == contract.id
    assert invoice.seller_name == "佛山市某酒店"
    assert invoice.file_path.startswith(f"contracts/invoices/c{contract.id}/")


@pytest.mark.django_db
@patch("apps.invoice_recognition.services.wiring.get_quick_recognition_service")
def test_attach_invoice_to_payment_recomputes_amount(
    mock_svc_factory: Any, authenticated_client, contract: Contract, payment: ContractPayment
) -> None:
    """钱到账后把合同挂靠发票归属到收款：开票金额回填、payment_id 有值、contract 清空。"""
    mock_svc_factory.return_value = _mock_recognizer(_parsed())
    uploaded = authenticated_client.post(
        f"/api/v1/contracts/finance/contracts/{contract.id}/invoices", {"files": _upload()}
    ).json()["saved"][0]

    resp = authenticated_client.post(
        f"/api/v1/contracts/finance/invoices/{uploaded['id']}/attach",
        data={"payment_id": payment.id},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["invoice"]["payment_id"] == payment.id
    assert body["invoice_status"] == InvoiceStatus.INVOICED_FULL
    assert body["invoiced_amount"] == "30000.00"

    invoice = Invoice.objects.get(pk=uploaded["id"])
    assert invoice.payment_id == payment.id
    assert invoice.contract_id is None
    payment.refresh_from_db()
    assert payment.invoiced_amount == Decimal("30000")


@pytest.mark.django_db
@patch("apps.invoice_recognition.services.wiring.get_quick_recognition_service")
def test_attach_rejects_cross_contract_and_double_attach(
    mock_svc_factory: Any, authenticated_client, contract: Contract, payment: ContractPayment
) -> None:
    """跨合同 / 已关联别的收款都拒绝——财务数据宁可重传不可错挂。"""
    other = Contract.objects.create(name="另一份合同", case_type="civil", fixed_amount=Decimal("10000"))
    mock_svc_factory.return_value = _mock_recognizer(_parsed())
    uploaded = authenticated_client.post(
        f"/api/v1/contracts/finance/contracts/{contract.id}/invoices", {"files": _upload()}
    ).json()["saved"][0]

    # 已直接挂收款的发票不能改挂
    linked = Invoice.objects.create(payment=payment, file_path="contracts/invoices/x/b.pdf", original_filename="b.pdf")
    resp = authenticated_client.post(
        f"/api/v1/contracts/finance/invoices/{linked.id}/attach",
        data={"payment_id": payment.id},
        content_type="application/json",
    )
    assert resp.status_code == 400, resp.content

    # 跨合同：发票挂 A 合同、收款在 B 合同
    other_payment = ContractPayment.objects.create(
        contract=other, amount=Decimal("5000"), received_at=date(2026, 10, 20)
    )
    resp = authenticated_client.post(
        f"/api/v1/contracts/finance/invoices/{uploaded['id']}/attach",
        data={"payment_id": other_payment.id},
        content_type="application/json",
    )
    assert resp.status_code == 400, resp.content
    uploaded_row = Invoice.objects.get(pk=uploaded["id"])
    assert uploaded_row.contract_id == contract.id  # 挂靠未被动过


@pytest.mark.django_db
def test_list_contract_invoices_includes_unlinked(
    authenticated_client, contract: Contract, payment: ContractPayment
) -> None:
    Invoice.objects.create(payment=payment, file_path="contracts/invoices/1/a.pdf", original_filename="a.pdf")
    Invoice.objects.create(
        contract=contract, file_path=f"contracts/invoices/c{contract.id}/b.pdf", original_filename="b.pdf"
    )

    resp = authenticated_client.get(f"/api/v1/contracts/finance/contracts/{contract.id}/invoices")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert {row["original_filename"] for row in body} == {"a.pdf", "b.pdf"}

    resp = authenticated_client.get(f"/api/v1/contracts/finance/contracts/{contract.id}/invoices", {"unlinked": "true"})
    body = resp.json()
    assert [row["original_filename"] for row in body] == ["b.pdf"]
    assert body[0]["payment_id"] is None


@pytest.mark.django_db
def test_delete_unlinked_invoice_needs_no_payment(authenticated_client, contract: Contract) -> None:
    invoice = Invoice.objects.create(
        contract=contract, file_path=f"contracts/invoices/c{contract.id}/c.pdf", original_filename="c.pdf"
    )
    resp = authenticated_client.delete(f"/api/v1/contracts/finance/invoices/{invoice.id}")
    assert resp.status_code == 200, resp.content
    assert not Invoice.objects.filter(pk=invoice.id).exists()


# ============================================================ 复制发票文件到系统剪贴板


@pytest.mark.django_db
def test_copy_invoice_to_clipboard_uses_renamed_file(
    authenticated_client, contract: Contract, payment: ContractPayment
) -> None:
    """复制的是**重命名后**的文件（发票（合同名称）_日期开具），不是 media 里的 UUID 原名。"""
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    stored = default_storage.save("contracts/invoices/1/copy-test.pdf", ContentFile(b"%PDF-1.4 fake"))
    try:
        Invoice.objects.create(
            payment=payment,
            file_path=stored,
            original_filename="copy-test.pdf",
            invoice_date=date(2026, 10, 14),
            seller_name="佛山市某酒店",
        )
        captured: dict[str, Any] = {}

        def _capture(paths: Any) -> int:
            captured["paths"] = paths
            return sum(1 for p in paths if p.is_file())

        with patch("apps.core.services.mac_clipboard_service.MacClipboardFileService") as clipboard_cls:
            clipboard_cls.return_value.is_available.return_value = True
            clipboard_cls.return_value.copy_file_paths.side_effect = _capture

            resp = authenticated_client.post("/api/v1/contracts/finance/invoices/-1/copy-to-clipboard")
            assert resp.status_code == 404, resp.content  # 不存在的发票

            invoice = Invoice.objects.get(file_path=stored)
            resp = authenticated_client.post(f"/api/v1/contracts/finance/invoices/{invoice.id}/copy-to-clipboard")

        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body == {"success": True, "copied": 1, "reason": None}
        # 落板文件名 = 律师命名习惯，且文件内容真实存在（粘贴时才有本体）
        (path,) = captured["paths"]
        assert path.name == "发票（记收款测试合同）_20261014开具.pdf"
        assert path.read_bytes() == b"%PDF-1.4 fake"
    finally:
        default_storage.delete(stored)


@pytest.mark.django_db
def test_copy_invoice_to_clipboard_unsupported_off_mac(authenticated_client, contract: Contract) -> None:
    """后端非 macOS / 无 pyobjc：返回 unsupported，前端据此降级复制文件名。"""
    invoice = Invoice.objects.create(
        contract=contract, file_path=f"contracts/invoices/c{contract.id}/d.pdf", original_filename="d.pdf"
    )
    with patch("apps.core.services.mac_clipboard_service.MacClipboardFileService") as clipboard_cls:
        clipboard_cls.return_value.is_available.return_value = False
        resp = authenticated_client.post(f"/api/v1/contracts/finance/invoices/{invoice.id}/copy-to-clipboard")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["success"] is False and body["reason"] == "unsupported"


@pytest.mark.django_db
def test_copy_invoice_to_clipboard_missing_file_reports_failure(authenticated_client, contract: Contract) -> None:
    """media 原件丢失：如实返回落板失败（success=false + reason），不能再抛 500。

    真实事故：票记录还在、media 文件被清掉，复制按钮点下去返回「系统错误」，
    前端 catch 分支又把 busy 卡死，表现成按钮无限转圈。
    """
    invoice = Invoice.objects.create(
        contract=contract, file_path=f"contracts/invoices/c{contract.id}/gone.pdf", original_filename="gone.pdf"
    )
    with patch("apps.core.services.mac_clipboard_service.MacClipboardFileService") as clipboard_cls:
        clipboard_cls.return_value.is_available.return_value = True
        resp = authenticated_client.post(f"/api/v1/contracts/finance/invoices/{invoice.id}/copy-to-clipboard")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["success"] is False and body["copied"] == 0
    assert body["reason"], "缺失文件必须给出可读原因，供前端降级复制文件名"


@pytest.mark.django_db
@patch("apps.invoice_recognition.services.wiring.get_quick_recognition_service")
def test_detach_invoice_returns_to_contract_and_recomputes(
    mock_svc_factory: Any, authenticated_client, contract: Contract, payment: ContractPayment
) -> None:
    """挂错能调整：解除关联 → 票回合同名下、原收款开票金额归零；可再挂到正确收款。"""
    mock_svc_factory.return_value = _mock_recognizer(_parsed())
    uploaded = authenticated_client.post(
        f"/api/v1/contracts/finance/contracts/{contract.id}/invoices", {"files": _upload()}
    ).json()["saved"][0]
    authenticated_client.post(
        f"/api/v1/contracts/finance/invoices/{uploaded['id']}/attach",
        data={"payment_id": payment.id},
        content_type="application/json",
    )
    payment.refresh_from_db()
    assert payment.invoiced_amount == Decimal("30000")

    resp = authenticated_client.post(f"/api/v1/contracts/finance/invoices/{uploaded['id']}/detach")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["invoice"]["payment_id"] is None
    assert Decimal(body["invoiced_amount"]) == Decimal("0")
    assert body["invoice_status"] == InvoiceStatus.UNINVOICED

    invoice = Invoice.objects.get(pk=uploaded["id"])
    assert invoice.payment_id is None
    assert invoice.contract_id == contract.id  # 退回合同名下，不是变成孤儿
    payment.refresh_from_db()
    assert payment.invoiced_amount == Decimal("0")
    assert payment.invoice_status == InvoiceStatus.UNINVOICED

    # 再挂回正确收款：解除不是单向门
    resp = authenticated_client.post(
        f"/api/v1/contracts/finance/invoices/{uploaded['id']}/attach",
        data={"payment_id": payment.id},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    payment.refresh_from_db()
    assert payment.invoiced_amount == Decimal("30000")


@pytest.mark.django_db
def test_detach_unlinked_invoice_is_rejected(authenticated_client, contract: Contract) -> None:
    """本来就没挂的票再解绑要报错，而不是静默成功（前端无法区分就无从提示）。"""
    invoice = Invoice.objects.create(
        contract=contract, file_path=f"contracts/invoices/c{contract.id}/e.pdf", original_filename="e.pdf"
    )
    resp = authenticated_client.post(f"/api/v1/contracts/finance/invoices/{invoice.id}/detach")
    assert resp.status_code == 400, resp.content
