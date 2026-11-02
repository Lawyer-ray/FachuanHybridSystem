"""粘贴图片记收款：`POST /finance/payments/parse-image` 集成测试。

跑在测试库（``DB_NAME=test_fachuan_dev``）。这个端点是「律师粘贴网银电子回单
截图 → 自动填好金额/日期/付款人」的唯一入口，所以测的重心是**识别链路与
草稿字段口径**，而不是图片本身：

1. 回单版式：分栏付款人/收款人不能取反（自家律所绝不能当付款人）、大写金额
   参与校验、日期带到时分；**只解析不落库**；
2. 短信版式文本：回单判定失败时自动降级到短信解析；
3. 引擎认不出文字：200 + 空草稿（不报错、不落库），前端据此提示手填；
4. 非图片 / 空文件：400。

识别引擎全部 mock（`PaymentImageReader` 顶层 patch），避免测试依赖
VLM 网关与本地 OCR 引擎是否装好。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.contracts.models import Contract, ContractPayment

URL = "/api/v1/contracts/finance/payments/parse-image"

# 真实网银电子回单版式（结构照抄，主体名脱敏）
RECEIPT_TEXT = (
    "南海农商银行网上银行交易电子凭证"
    "交易时间:2026-11-02 14:17:07 交易状态:交易成功 网银流水:88880001 "
    "付款人 户名:佛山市某某铝业有限公司 转出账号:6222XXXXXXXXXXXX "
    "收款人 户名:北京某某(广州)律师事务所 转入账号:6228XXXXXXXXXXXX "
    "金额: 25,000.00 大写:贰万伍仟元正整 币种:人民币 用途:往来款"
)

SMS_TEXT = "【建设银行】丙方不锈钢有限公司10月14日14时17分向贵公司4501账户律师费存入人民币30000元。"


def _png() -> SimpleUploadedFile:
    # 扩展名/MIME 是后端唯一在意的（内容交给被 mock 的识别引擎）
    return SimpleUploadedFile("回单.png", b"\x89PNG\r\n\x1a\n fake", content_type="image/png")


def _reader_out(text: str, method: str = "vlm") -> Any:
    from apps.contracts.services.payment.payment_image_reader import PastedImageText

    return PastedImageText(text=text, method=method, chars=len(text))


@pytest.fixture()
def contract(db: None) -> Contract:
    return Contract.objects.create(name="回单识别测试合同", case_type="civil", fixed_amount=Decimal("100000"))


@pytest.mark.django_db
@patch("apps.contracts.services.payment.payment_image_reader.PaymentImageReader.read")
def test_receipt_image_yields_draft_without_persisting(
    mock_read: Any, authenticated_client, contract: Contract
) -> None:
    mock_read.return_value = _reader_out(RECEIPT_TEXT)

    resp = authenticated_client.post(URL, {"file": _png()})
    assert resp.status_code == 200, resp.content
    body = resp.json()

    assert body["is_receipt"] is True
    assert body["amount"] == "25000.00"
    assert body["received_at"] == "2026-11-02"
    assert body["amount_mismatch"] is False
    assert body["extraction_method"] == "vlm"
    # 付款人绝不能是自家律所（两栏都叫「户名」，取反就是记账事故）
    assert body["payer"] == "佛山市某某铝业有限公司"
    assert "律师事务所" in body["payee"]
    assert "往来款" in body["note"]
    assert any("视觉模型" in h for h in body["hints"])

    # 只解析不落库
    assert ContractPayment.objects.count() == 0


@pytest.mark.django_db
@patch("apps.contracts.services.payment.payment_image_reader.PaymentImageReader.read")
def test_amount_mismatch_is_surfaced(mock_read: Any, authenticated_client, contract: Contract) -> None:
    """小写 25,000 与大写 贰万陆仟 对不上时必须显式置位，让前端醒目提示核对。"""
    mock_read.return_value = _reader_out(
        "电子回单 金额: 25,000.00 大写:贰万陆仟元整 交易时间:2026-11-02 14:17:07 "
        "付款人 户名:佛山市某某铝业有限公司 收款人 户名:北京某某律师事务所"
    )
    body = authenticated_client.post(URL, {"file": _png()}).json()

    assert body["amount"] == "25000.00"
    assert body["amount_mismatch"] is True
    assert any("大写与小写" in h for h in body["hints"])


@pytest.mark.django_db
@patch("apps.contracts.services.payment.payment_image_reader.PaymentImageReader.read")
def test_sms_screenshot_falls_back_to_sms_parser(mock_read: Any, authenticated_client, contract: Contract) -> None:
    """截图里的文本是短信版式（不是回单）时，自动降级到短信解析，字段照样填。"""
    mock_read.return_value = _reader_out(SMS_TEXT, method="ocr")

    body = authenticated_client.post(URL, {"file": _png()}).json()

    assert body["is_receipt"] is False
    assert body["amount"] == "30000.00"
    assert body["received_at"] == "2026-10-14"
    assert body["payer"] == "丙方不锈钢有限公司"
    assert body["extraction_method"] == "ocr"


@pytest.mark.django_db
@patch("apps.contracts.services.payment.payment_image_reader.PaymentImageReader.read")
def test_unreadable_image_returns_empty_draft(mock_read: Any, authenticated_client, contract: Contract) -> None:
    """引擎一个字都没认出来：200 + 空字段（绝不填默认值），前端提示手填。"""
    mock_read.return_value = _reader_out("", method="empty")

    resp = authenticated_client.post(URL, {"file": _png()})
    assert resp.status_code == 200, resp.content
    body = resp.json()

    assert body["amount"] is None
    assert body["received_at"] is None
    assert body["payer"] == ""
    assert body["note"] == ""
    assert ContractPayment.objects.count() == 0


@pytest.mark.django_db
def test_unsupported_file_type_is_rejected(authenticated_client, contract: Contract) -> None:
    """非图片/PDF（如误贴的 docx）要 400 拒绝，而不是悄悄当成图片去 OCR。"""
    bad = SimpleUploadedFile(
        "说明.docx",
        b"PK\x03\x04",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    resp = authenticated_client.post(URL, {"file": bad})
    assert resp.status_code == 400, resp.content

    # 不只看状态码：拒收必须带可读原因，且绝不能落库
    body = resp.json()
    assert "图片" in str(body), f"400 响应应说明支持的类型，实际: {body}"
    assert ContractPayment.objects.count() == 0
