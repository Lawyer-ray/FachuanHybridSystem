"""
发票上传功能测试 — 属性测试 + 单元测试

Feature: contract-invoice-upload
"""

from __future__ import annotations

import datetime
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from apps.contracts.models import ContractPayment, Invoice
from apps.contracts.services.contract.invoice_upload_service import InvoiceUploadService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(**kwargs: Any) -> Any:
    from apps.contracts.models import Contract

    defaults: dict[str, Any] = {"name": "测试合同", "case_type": "civil"}
    defaults.update(kwargs)
    return Contract.objects.create(**defaults)


def _make_payment(contract: Any, **kwargs: Any) -> ContractPayment:
    defaults: dict[str, Any] = {"amount": "1000.00"}
    defaults.update(kwargs)
    return ContractPayment.objects.create(contract=contract, **defaults)


def _make_invoice(payment: ContractPayment, **kwargs: Any) -> Invoice:
    defaults: dict[str, Any] = {
        "file_path": f"contracts/invoices/{payment.pk}/test.pdf",
        "original_filename": "test.pdf",
        "remark": "",
    }
    defaults.update(kwargs)
    return Invoice.objects.create(payment=payment, **defaults)


# ---------------------------------------------------------------------------
# Property 1: Invoice 字段 Round-Trip
# Feature: contract-invoice-upload, Property 1: Invoice 字段 Round-Trip
# ---------------------------------------------------------------------------


class TestProperty1FieldRoundTrip(HypothesisTestCase):
    """Property 1: 字段 round-trip — Validates: Requirements 1.2"""

    @given(
        file_path=st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != ""),
        original_filename=st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != ""),
        remark=st.text(max_size=200),
    )
    @settings(max_examples=100)
    def test_fields_roundtrip(self, file_path: str, original_filename: str, remark: str) -> None:
        # Feature: contract-invoice-upload, Property 1: Invoice 字段 Round-Trip
        contract = _make_contract()
        payment = _make_payment(contract)
        inv = Invoice.objects.create(
            payment=payment,
            file_path=file_path,
            original_filename=original_filename,
            remark=remark,
        )
        fetched = Invoice.objects.get(pk=inv.pk)
        assert fetched.file_path == file_path
        assert fetched.original_filename == original_filename
        assert fetched.remark == remark
        assert fetched.payment_id == payment.pk


# ---------------------------------------------------------------------------
# Property 2: 级联删除
# Feature: contract-invoice-upload, Property 2: 级联删除
# ---------------------------------------------------------------------------


class TestProperty2CascadeDelete(HypothesisTestCase):
    """Property 2: 级联删除 — Validates: Requirements 1.1"""

    @given(n=st.integers(min_value=1, max_value=5))
    @settings(max_examples=100)
    def test_cascade_delete(self, n: int) -> None:
        # Feature: contract-invoice-upload, Property 2: 级联删除
        contract = _make_contract()
        payment = _make_payment(contract)
        inv_pks = [_make_invoice(payment, file_path=f"contracts/invoices/{payment.pk}/{i}.pdf").pk for i in range(n)]
        payment.delete()
        assert Invoice.objects.filter(pk__in=inv_pks).count() == 0


# ---------------------------------------------------------------------------
# Property 3: 默认倒序排列
# Feature: contract-invoice-upload, Property 3: 默认倒序排列
# ---------------------------------------------------------------------------


class TestProperty3DefaultOrdering(HypothesisTestCase):
    """Property 3: 默认倒序排列 — Validates: Requirements 1.3"""

    @given(n=st.integers(min_value=2, max_value=8))
    @settings(max_examples=100)
    def test_default_ordering_descending(self, n: int) -> None:
        # Feature: contract-invoice-upload, Property 3: 默认倒序排列
        from django.utils import timezone

        contract = _make_contract()
        payment = _make_payment(contract)
        base = timezone.now()
        for i in range(n):
            inv = _make_invoice(payment, file_path=f"contracts/invoices/{payment.pk}/{i}.pdf")
            Invoice.objects.filter(pk=inv.pk).update(uploaded_at=base + datetime.timedelta(seconds=i))

        qs = list(Invoice.objects.filter(payment=payment))
        times = [inv.uploaded_at for inv in qs]
        assert times == sorted(times, reverse=True)


# ---------------------------------------------------------------------------
# Property 4: 文件保存参数正确性
# Feature: contract-invoice-upload, Property 4: 文件保存参数正确性
# ---------------------------------------------------------------------------


class TestProperty4SaveParams(HypothesisTestCase):
    """Property 4: 文件保存参数正确性 — Validates: Requirements 2.1, 2.2, 2.3, 2.4"""

    @given(payment_id=st.integers(min_value=1, max_value=9999))
    @settings(max_examples=100)
    def test_save_params_correct(self, payment_id: int) -> None:
        # Feature: contract-invoice-upload, Property 4: 文件保存参数正确性
        captured: dict[str, Any] = {}

        def fake_save(
            uploaded_file: Any,
            rel_dir: str,
            allowed_extensions: list[str] | None = None,
            max_size_bytes: int | None = None,
            use_uuid_name: bool = True,
            **kwargs: Any,
        ) -> tuple[str, str]:
            captured["rel_dir"] = rel_dir
            captured["allowed_extensions"] = allowed_extensions
            captured["max_size_bytes"] = max_size_bytes
            captured["use_uuid_name"] = use_uuid_name
            return f"{rel_dir}/fake.pdf", "fake.pdf"

        mock_file = MagicMock()
        mock_file.name = "invoice.pdf"

        with patch("apps.contracts.services.contract.invoice_upload_service.storage") as mock_storage:
            mock_storage.save_uploaded_file.side_effect = fake_save
            # 需要 payment 存在才能创建 Invoice，mock create
            with patch("apps.contracts.models.Invoice.objects") as mock_mgr:
                mock_mgr.create.return_value = MagicMock(spec=Invoice)
                svc = InvoiceUploadService()
                svc.save_invoice_file(mock_file, payment_id)

        assert captured["rel_dir"] == f"contracts/invoices/{payment_id}"
        assert captured["allowed_extensions"] == [".pdf", ".jpg", ".jpeg", ".png"]
        assert captured["max_size_bytes"] == 20 * 1024 * 1024
        assert captured["use_uuid_name"] is True


# ---------------------------------------------------------------------------
# Property 5: 保存失败不创建数据库记录
# Feature: contract-invoice-upload, Property 5: 保存失败不创建数据库记录
# ---------------------------------------------------------------------------


class TestProperty5SaveFailureNoRecord(HypothesisTestCase):
    """Property 5: 保存失败不创建 DB 记录 — Validates: Requirements 2.5"""

    @given(payment_id=st.integers(min_value=1, max_value=9999))
    @settings(max_examples=100)
    def test_save_failure_no_db_record(self, payment_id: int) -> None:
        # Feature: contract-invoice-upload, Property 5: 保存失败不创建数据库记录
        mock_file = MagicMock()
        mock_file.name = "invoice.pdf"

        before_count = Invoice.objects.filter(payment_id=payment_id).count()

        with patch("apps.contracts.services.contract.invoice_upload_service.storage") as mock_storage:
            mock_storage.save_uploaded_file.side_effect = OSError("disk full")
            svc = InvoiceUploadService()
            with pytest.raises(OSError):
                svc.save_invoice_file(mock_file, payment_id)

        after_count = Invoice.objects.filter(payment_id=payment_id).count()
        assert after_count == before_count


# ---------------------------------------------------------------------------
# Property 6: 查询与删除 Round-Trip
# Feature: contract-invoice-upload, Property 6: 查询与删除 Round-Trip
# ---------------------------------------------------------------------------


class TestProperty6ListDeleteRoundTrip(HypothesisTestCase):
    """Property 6: 查询与删除 round-trip — Validates: Requirements 5.1, 5.3"""

    @given(n=st.integers(min_value=1, max_value=5))
    @settings(max_examples=100)
    def test_list_then_delete(self, n: int) -> None:
        # Feature: contract-invoice-upload, Property 6: 查询与删除 Round-Trip
        contract = _make_contract()
        payment = _make_payment(contract)
        invoices = [_make_invoice(payment, file_path=f"contracts/invoices/{payment.pk}/{i}.pdf") for i in range(n)]

        svc = InvoiceUploadService()
        qs = svc.list_invoices_by_payment(payment.pk)
        assert qs.count() == n

        target = invoices[0]
        with patch("apps.contracts.services.contract.invoice_upload_service.storage") as mock_storage:
            mock_storage.delete_media_file.return_value = True
            svc.delete_invoice(target.pk)
            mock_storage.delete_media_file.assert_called_once_with(target.file_path)

        assert svc.list_invoices_by_payment(payment.pk).count() == n - 1
        assert not Invoice.objects.filter(pk=target.pk).exists()


# ---------------------------------------------------------------------------
# Property 7: 按合同查询覆盖所有收款
# Feature: contract-invoice-upload, Property 7: 按合同查询覆盖所有收款
# ---------------------------------------------------------------------------


class TestProperty7ListByContract(HypothesisTestCase):
    """Property 7: list_invoices_by_contract 覆盖所有收款 — Validates: Requirements 5.2"""

    @given(payment_counts=st.lists(st.integers(min_value=1, max_value=3), min_size=1, max_size=3))
    @settings(max_examples=100)
    def test_list_by_contract_covers_all(self, payment_counts: list[int]) -> None:
        # Feature: contract-invoice-upload, Property 7: 按合同查询覆盖所有收款
        contract = _make_contract()
        all_inv_pks: set[int] = set()
        for idx, count in enumerate(payment_counts):
            payment = _make_payment(contract, amount=f"{(idx + 1) * 100}.00")
            for i in range(count):
                inv = _make_invoice(payment, file_path=f"contracts/invoices/{payment.pk}/{i}.pdf")
                all_inv_pks.add(inv.pk)

        svc = InvoiceUploadService()
        result = svc.list_invoices_by_contract(contract.pk)
        returned_pks = {inv.pk for invs in result.values() for inv in invs}
        assert all_inv_pks == returned_pks


# ---------------------------------------------------------------------------
# Property 8: 模板渲染完整性
# Feature: contract-invoice-upload, Property 8: 模板渲染完整性
# ---------------------------------------------------------------------------


class TestProperty8TemplateRendering(HypothesisTestCase):
    """Property 8: 模板渲染完整性 — Validates: Requirements 4.1, 4.2"""

    @given(
        original_filename=st.text(
            min_size=1,
            max_size=40,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="._-"),
        ).filter(lambda s: s.strip() != ""),
        remark=st.text(max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"))),
    )
    @settings(max_examples=100)
    def test_template_contains_invoice_fields(self, original_filename: str, remark: str) -> None:
        # Feature: contract-invoice-upload, Property 8: 模板渲染完整性
        from django.template.loader import render_to_string

        contract = _make_contract()
        payment = _make_payment(contract)
        inv = _make_invoice(payment, original_filename=original_filename, remark=remark)

        html = render_to_string(
            "admin/contracts/contract/partials/finance.html",
            {
                "contract": contract,
                "payments": [payment],
                "total_payment_amount": payment.amount,
                "invoices_by_payment": {payment.pk: [inv]},
                "media_url": "/media/",
                "payment_progress": {},
                "invoice_summary": {},
            },
        )

        assert original_filename in html
        assert f"/media/{inv.file_path}" in html


# ---------------------------------------------------------------------------
# Property 9: 删除 Invoice 时清理物理文件
# Feature: contract-invoice-upload, Property 9: 删除 Invoice 时清理物理文件
# ---------------------------------------------------------------------------


class TestProperty9DeleteCleansFile(HypothesisTestCase):
    """Property 9: 删除时清理物理文件 — Validates: Requirements 3.4, 5.3"""

    @given(
        file_path=st.builds(
            lambda a, b: f"contracts/invoices/{a}/{b}.pdf",
            a=st.integers(min_value=1, max_value=999),
            b=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789"),
        )
    )
    @settings(max_examples=100)
    def test_delete_calls_storage(self, file_path: str) -> None:
        # Feature: contract-invoice-upload, Property 9: 删除 Invoice 时清理物理文件
        contract = _make_contract()
        payment = _make_payment(contract)
        inv = _make_invoice(payment, file_path=file_path)

        with patch("apps.contracts.services.contract.invoice_upload_service.storage") as mock_storage:
            mock_storage.delete_media_file.return_value = True
            svc = InvoiceUploadService()
            svc.delete_invoice(inv.pk)
            mock_storage.delete_media_file.assert_called_once_with(file_path)


# ---------------------------------------------------------------------------
# Unit Tests — example scenarios
# ---------------------------------------------------------------------------


class TestInvoiceInlineIsTabular(TestCase):
    def test_invoice_inline_is_tabular(self) -> None:
        from django.contrib import admin

        from apps.contracts.admin.contractpayment_admin import InvoiceInline

        try:
            import nested_admin

            assert issubclass(InvoiceInline, nested_admin.NestedTabularInline)
        except ImportError:
            assert issubclass(InvoiceInline, admin.TabularInline)


class TestInvoiceAdminFormHasFileField(TestCase):
    def test_form_has_file_field(self) -> None:
        from apps.contracts.admin.contractpayment_admin import InvoiceAdminForm

        assert "file" in InvoiceAdminForm().fields


class TestInvoiceInlineFields(TestCase):
    def test_inline_fields_contain_required(self) -> None:
        from apps.contracts.admin.contractpayment_admin import InvoiceInline

        for field in ("original_filename", "uploaded_at", "remark"):
            assert field in InvoiceInline.fields


class TestInvoiceInlineExtra(TestCase):
    def test_extra_is_one(self) -> None:
        from apps.contracts.admin.contractpayment_admin import InvoiceInline

        assert InvoiceInline.extra == 1


@pytest.mark.django_db
class TestListByPaymentNonexistent(TestCase):
    def test_nonexistent_payment_returns_empty(self) -> None:
        svc = InvoiceUploadService()
        qs = svc.list_invoices_by_payment(999999)
        assert qs.count() == 0


@pytest.mark.django_db
class TestDeleteNonexistentInvoiceRaises(TestCase):
    def test_delete_nonexistent_raises(self) -> None:
        from apps.core.exceptions import NotFoundError

        svc = InvoiceUploadService()
        with pytest.raises(NotFoundError):
            svc.delete_invoice(999999)


@pytest.mark.django_db
class TestNoInvoicesTemplateShowsPlaceholder(TestCase):
    def test_no_invoices_shows_placeholder(self) -> None:
        from django.template.loader import render_to_string

        contract = _make_contract()
        payment = _make_payment(contract)
        html = render_to_string(
            "admin/contracts/contract/partials/finance.html",
            {
                "contract": contract,
                "payments": [payment],
                "total_payment_amount": payment.amount,
                "invoices_by_payment": {},
                "media_url": "/media/",
                "payment_progress": {},
                "invoice_summary": {},
            },
        )
        assert "暂无发票" in html or "No invoices" in html
