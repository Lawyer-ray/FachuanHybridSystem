"""红票的收款预选行为（D4）：永不预选收款，置信度分两档。

## 为什么红票要单独一档

修复前红票的 `total_amount` 是 `None` → `_amounts_match(None)` 恒 False → 界面报
「金额与收款不符」。方向错了：真实情况是「这是红票，它冲掉的是 ……368336」。
更危险的是红票一旦预选了一笔收款，人就容易顺手确认，帐上多出一笔支出。

所以：`choose_payment(..., is_red=True)` 的 `suggested_payment_id` **恒为 None**，
`confidence` 只取 `red_offset` / `red_unmatched`。

## 测法

`choose_payment` 的分支判定用假收款行集跑（只把取收款列表的查询入口换掉），
避免把逻辑重写一份去测副本；真实库那条端到端验证「红票在真实收款表上也不预选」。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any
from unittest import mock

import pytest

from apps.contracts.models import Contract, ContractPayment
from apps.contracts.services.payment.invoice_match import (
    CONFIDENCE_EXACT,
    CONFIDENCE_RED_OFFSET,
    CONFIDENCE_RED_UNMATCHED,
    NOTE_RED_OFFSET,
    NOTE_RED_UNMATCHED,
    choose_payment,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

ORIGINAL_NUMBER = "11111111111111111111"
RED_TOTAL = Decimal("-10000.00")

_ROW: dict[str, Any] = {
    "id": 1,
    "amount": Decimal("10000.00"),
    "received_at": date(2026, 11, 10),
    "note": "",
}


@contextmanager
def _with_payments(rows: list[dict[str, Any]]) -> Iterator[Any]:
    """把取收款列表的查询入口换成假行集（被测逻辑原样运行）。"""

    class _FakeQuerySet(list):
        def order_by(self, *args: Any, **kwargs: Any) -> _FakeQuerySet:
            return self

        def values(self, *args: Any, **kwargs: Any) -> _FakeQuerySet:
            return self

    with mock.patch(
        "apps.contracts.models.ContractPayment.objects.filter",
        return_value=_FakeQuerySet(rows),
    ) as patched:
        yield patched





class TestRedNeverPreselectsPayment:
    def test_red_with_single_matching_payment_still_picks_nothing(self) -> None:
        with _with_payments([_ROW]):
            result = choose_payment(contract_id=393, total_amount=RED_TOTAL, invoice_date=None, is_red=True)

        assert result["suggested_payment_id"] is None
        # 收款选项仍然给出来：人可以自己看，只是系统不替人做这个动作
        assert result["payment_options"]

    def test_blue_invoice_still_picks_the_only_payment(self) -> None:
        """同一笔收款下，蓝票行为不变（回归护栏：加法不能改掉既有规则）。"""
        with _with_payments([_ROW]):
            result = choose_payment(contract_id=393, total_amount=Decimal("10000.00"), invoice_date=None)

        assert result["suggested_payment_id"] == 1
        assert result["confidence"] == CONFIDENCE_EXACT


class TestRedConfidence:
    """红票两档置信度。

    ⚠️ 这两个事实（票面印的被冲票号、该票号是否命中本库 Invoice）**由扫描层查询
    后显式传入**。``choose_payment`` 只拿到合同，拿不到票号，所以它自己不可能
    推导出「原票在库」——历史实现曾试图用「该收款已挂的发票号」兜底，结果恒为空，
    所有红票都退化成 ``red_unmatched``（见下面 test_never_derives_offset_from_contract）。
    """

    def test_original_in_library_gives_red_offset(self) -> None:
        with _with_payments([_ROW]):
            result = choose_payment(
                contract_id=393,
                total_amount=RED_TOTAL,
                invoice_date=None,
                is_red=True,
                red_against_number=ORIGINAL_NUMBER,
                red_offset_found=True,
            )

        assert result["confidence"] == CONFIDENCE_RED_OFFSET
        assert result["note"] == NOTE_RED_OFFSET.format(number=ORIGINAL_NUMBER)

    def test_missing_original_gives_red_unmatched(self) -> None:
        with _with_payments([_ROW]):
            result = choose_payment(
                contract_id=393,
                total_amount=RED_TOTAL,
                invoice_date=None,
                is_red=True,
                red_against_number=ORIGINAL_NUMBER,
                red_offset_found=False,
            )

        assert result["confidence"] == CONFIDENCE_RED_UNMATCHED
        # 票号仍要带给用户，否则他无从知道该去补录哪张票
        assert ORIGINAL_NUMBER in result["note"]

    def test_never_derives_offset_from_contract_when_not_told(self) -> None:
        """回归锚点：不传事实时**不得**自己猜出 red_offset。

        这条锁死的是一个真实缺陷：旧实现从「合同唯一那笔收款已挂的发票号」推导
        被冲票号，从而把「原票不在库」误报成「可一键冲红」。票号必须由调用方给。
        """
        with _with_payments([_ROW]):
            result = choose_payment(contract_id=393, total_amount=RED_TOTAL, invoice_date=None, is_red=True)

        assert result["confidence"] == CONFIDENCE_RED_UNMATCHED
        assert result["suggested_payment_id"] is None

    def test_number_without_hit_is_still_unmatched(self) -> None:
        """票面写了票号 ≠ 原票在库。前者是识别结果，后者要查库才算。"""
        with _with_payments([_ROW]):
            result = choose_payment(
                contract_id=393,
                total_amount=RED_TOTAL,
                invoice_date=None,
                is_red=True,
                red_against_number=ORIGINAL_NUMBER,
                red_offset_found=None,
            )

        assert result["confidence"] == CONFIDENCE_RED_UNMATCHED

    def test_red_never_reports_amount_mismatch(self) -> None:
        """D4：红票金额未识别时不能说「金额与收款不符」——它压根没被识别出来。"""
        with _with_payments([_ROW]):
            result = choose_payment(contract_id=393, total_amount=None, invoice_date=None, is_red=True)

        assert result["confidence"] in {CONFIDENCE_RED_OFFSET, CONFIDENCE_RED_UNMATCHED}
        assert result["confidence"] != "amount_mismatch"

    def test_red_without_any_payment(self) -> None:
        with _with_payments([]):
            result = choose_payment(contract_id=393, total_amount=RED_TOTAL, invoice_date=None, is_red=True)

        assert result["suggested_payment_id"] is None
        assert result["confidence"] == CONFIDENCE_RED_UNMATCHED

    def test_red_against_multiple_payments_is_unmatched_not_ambiguous(self) -> None:
        rows = [_ROW, {**_ROW, "id": 2, "amount": Decimal("10000.00")}]
        with _with_payments(rows):
            result = choose_payment(contract_id=393, total_amount=RED_TOTAL, invoice_date=None, is_red=True)

        assert result["confidence"] == CONFIDENCE_RED_UNMATCHED
        assert len(result["payment_options"]) == 2


class TestRedAgainstRealPaymentTable:
    def test_red_on_real_payment_does_not_preselect(self, db: object) -> None:
        contract = Contract.objects.create(name="红票真实收款回归", status="active")
        payment = ContractPayment.objects.create(
            contract=contract, amount=Decimal("10000.00"), received_at=date(2026, 11, 10)
        )

        result = choose_payment(contract_id=contract.pk, total_amount=RED_TOTAL, invoice_date=None, is_red=True)

        assert result["suggested_payment_id"] is None
        assert result["confidence"] == CONFIDENCE_RED_UNMATCHED
        assert int(result["payment_options"][0]["id"]) == payment.pk
