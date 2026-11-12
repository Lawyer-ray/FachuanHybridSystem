"""发票待认领 API —— 红字发票（冲红重开）层测试。

锁定的行为（对应 docs/harness/backend/invoice-intake-red.md §5）：

1. **响应契约**：``InvoiceIntakeOut`` 带 ``is_red`` / 红票两个票面事实 /
   ``offset_invoice`` / ``supersedes_intake_id`` / ``superseded_by_intake_id`` /
   ``reatch_group``，且蓝票返回的组是 ``None``（不能把普通行也塞进组里）。
2. **分组装配**（§5.2）：``group_key = "red:<被冲票号>"``，原票 / 红票 / 重开票三段
   的 ``intake_id`` 与 ``invoice_id`` 各自正确——尤其原票那段同时有两个 id，
   混用会让前端把「已入账的原票」渲染成「还没落账」。
3. **端点存在性与转发**：三个新端点（confirm-red-reenact / confirm-red-only / reparse）
   挂上了 router，且把入参**原样**传给 service（``amount_override`` 是必须显式落痕
   的开关，弄丢了就变成静默放行不等额重开）。
4. **老端点守卫**（§5.3）：红票走 ``/confirm`` 必须 400 + ``INVOICE_RED_USE_DEDICATED_ENDPOINT``，
   且**不得**触达 service——这是「多出一张孤立负票」这条事故路径的唯一闸门。
5. **层归属**：``reatch_group`` 的装配在 API 层，查库在 Service 层；API 文件里
   不得出现 ``Model.objects``（四层架构基线 0）。
6. **后台**：``list_display`` 有 ``is_red`` 徽标列，``fieldsets`` 有「冲红信息」只读分组，
   巡检筛选「红票但原票不在库」能同时按 FK 与票号两种落库形态捞出来。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client

from apps.contracts.models import Contract, ContractPayment, Invoice, InvoiceIntake, InvoiceIntakeStatus
from apps.message_hub.models import InboxMessage, MessageSource
from apps.organization.models import AccountCredential, Lawyer

PREFIX = "/api/v1/contracts/finance/invoice-intake"

#: 真实样本票号（docs §1，脱敏到后 8 位仍可人眼对上）
ORIGINAL_NUMBER = "11111111111111111111"
RED_NUMBER = "33333333333333333333"
REISSUE_NUMBER = "44444444444444444444"


# ── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def lawyer(db: Any) -> Lawyer:
    return Lawyer.objects.create(username="red_api_lawyer", real_name="测试律师", is_admin=True, is_superuser=True)


@pytest.fixture
def source(db: Any, lawyer: Lawyer) -> MessageSource:
    credential = AccountCredential.objects.create(
        lawyer=lawyer, site_name="测试邮箱", account="red@example.com", password="x"
    )
    return MessageSource.objects.create(
        credential=credential, source_type="imap", display_name="测试邮箱", sync_since="2026-01-01T00:00:00Z"
    )


@pytest.fixture
def message(db: Any, source: MessageSource) -> InboxMessage:
    from django.utils import timezone

    return InboxMessage.objects.create(
        source=source,
        message_id="red-msg-1",
        subject="【发票】红字发票",
        sender="finance@example.com",
        received_at=timezone.now(),
        body_text="请查收红字发票",
    )


@pytest.fixture
def http(db: Any, lawyer: Lawyer) -> Client:
    client = Client()
    client.force_login(lawyer)
    return client


@pytest.fixture
def contract(db: Any) -> Contract:
    contract = Contract.objects.create(name="某某非诉专项", case_type="civil", status="active")
    contract.fixed_amount = Decimal("40000")
    contract.fee_mode = "FIXED"
    contract.save(update_fields=["fixed_amount", "fee_mode"])
    return contract


@pytest.fixture
def payment(db: Any, contract: Contract) -> ContractPayment:
    return ContractPayment.objects.create(contract=contract, amount=Decimal("40000"), received_at=date(2026, 11, 10))


def _intake(message: InboxMessage, **kwargs: Any) -> InvoiceIntake:
    seq = InvoiceIntake.objects.count() + 1
    base: dict[str, Any] = {
        "inbox_message": message,
        "dedupe_key": f"red-key-{seq}",
        "status": InvoiceIntakeStatus.PENDING,
    }
    base.update(kwargs)
    return InvoiceIntake.objects.create(**base)


def _red_triplet(
    message: InboxMessage, payment: ContractPayment, contract: Contract
) -> tuple[InvoiceIntake, InvoiceIntake, InvoiceIntake, Invoice]:
    """造出真实样本的完整三态：原蓝票已入账、红票待决、重开蓝票待决。"""
    original_invoice = Invoice.objects.create(
        payment=payment,
        file_path="invoices/original.pdf",
        original_filename="original.pdf",
        invoice_number=ORIGINAL_NUMBER,
        invoice_date=date(2026, 11, 10),
        total_amount=Decimal("10000.00"),
    )
    original = _intake(
        message,
        invoice_number=ORIGINAL_NUMBER,
        invoice_date=date(2026, 11, 10),
        total_amount=Decimal("10000.00"),
        status=InvoiceIntakeStatus.CONFIRMED,
        confirmed_contract=contract,
        confirmed_payment=payment,
        invoice=original_invoice,
    )
    red = _intake(
        message,
        invoice_number=RED_NUMBER,
        invoice_date=date(2026, 11, 11),
        total_amount=Decimal("-10000.00"),
        red_against_number=ORIGINAL_NUMBER,
        red_confirmation_no="22222222222222222222",  # 测试用确认单号
        offset_invoice=original_invoice,
    )
    # 重开蓝票 ``supersedes_intake`` 指向的是**被替代的原票 intake**（不是红票）。
    # 与扫描层 ``_find_supersede_target`` 一致：它在已确认 intake 里找被红票点名的原票。
    reissue = _intake(
        message,
        invoice_number=REISSUE_NUMBER,
        invoice_date=date(2026, 11, 11),
        total_amount=Decimal("10000.00"),
        supersedes_intake=original,
    )
    return original, red, reissue, original_invoice


# ── 1. 响应契约 ──────────────────────────────────────────


@pytest.mark.django_db
class TestResponseContract:
    def test_red_intake_exposes_red_facts(self, http: Client, message: InboxMessage, payment: ContractPayment, contract: Contract) -> None:
        _original, red, _reissue, original_invoice = _red_triplet(message, payment, contract)

        body = http.get(f"{PREFIX}/{red.pk}").json()

        assert body["is_red"] is True
        assert body["red_against_number"] == ORIGINAL_NUMBER
        assert body["red_confirmation_no"] == "22222222222222222222"
        assert body["offset_invoice"]["id"] == original_invoice.pk
        assert body["offset_invoice"]["invoice_number"] == ORIGINAL_NUMBER
        assert body["offset_invoice"]["total_amount"] == "10000.00"
        assert body["offset_invoice"]["contract_id"] == contract.pk

    def test_blue_intake_is_not_red_and_has_no_group(
        self, http: Client, message: InboxMessage, payment: ContractPayment, contract: Contract
    ) -> None:
        original, _red, _reissue, _inv = _red_triplet(message, payment, contract)

        body = http.get(f"{PREFIX}/{original.pk}").json()

        assert body["is_red"] is False
        assert body["red_against_number"] == ""
        assert body["offset_invoice"] is None
        assert body["reatch_group"] is None

    def test_negative_amount_alone_counts_as_red(self, http: Client, message: InboxMessage) -> None:
        """``is_red`` 是派生事实：备注栏没抽出票号，但金额为负就是红票。"""
        intake = _intake(message, invoice_number=RED_NUMBER, total_amount=Decimal("-1.00"))

        body = http.get(f"{PREFIX}/{intake.pk}").json()

        assert body["is_red"] is True
        assert body["red_against_number"] == ""


# ── 2. 分组装配（§5.2）────────────────────────────────────


@pytest.mark.django_db
class TestReatchGroupAssembly:
    def test_group_key_and_three_segments(
        self, http: Client, message: InboxMessage, payment: ContractPayment, contract: Contract
    ) -> None:
        original, red, reissue, original_invoice = _red_triplet(message, payment, contract)

        group = http.get(f"{PREFIX}/{red.pk}").json()["reatch_group"]

        assert group["group_key"] == f"red:{ORIGINAL_NUMBER}"
        # 原票段：两个 id 都要在，且分别指向「生成的 intake」与「已入账的发票」
        assert group["original"]["intake_id"] == original.pk
        assert group["original"]["invoice_id"] == original_invoice.pk
        assert group["original"]["total_amount"] == "10000.00"
        # 红票段：待决，没有 invoice_id
        assert group["red"]["intake_id"] == red.pk
        assert group["red"]["invoice_id"] is None
        assert group["red"]["total_amount"] == "-10000.00"
        # 重开段
        assert group["reissue"]["intake_id"] == reissue.pk
        assert group["reissue"]["invoice_number"] == REISSUE_NUMBER

    def test_reissue_row_carries_the_same_group_key(
        self, http: Client, message: InboxMessage, payment: ContractPayment, contract: Contract
    ) -> None:
        """组内**每个成员**都要拿到 group_key，否则前端会重复渲染。

        回归锚点：曾只给红票下发组事实，重开蓝票对不上任何组 → 首页出现
        「一张组卡片 + 一条重复的新票」（真实数据 #18/#19 实测就是这个现象）。
        """
        _original, red, reissue, _invoice = _red_triplet(message, payment, contract)

        red_group = http.get(f"{PREFIX}/{red.pk}").json()["reatch_group"]
        reissue_group = http.get(f"{PREFIX}/{reissue.pk}").json()["reatch_group"]

        assert reissue_group is not None
        assert reissue_group["group_key"] == red_group["group_key"]
        # 两段的红票与新票必须一致，前端据此只渲染一个组
        assert reissue_group["red"]["intake_id"] == red.pk
        assert reissue_group["reissue"]["intake_id"] == reissue.pk

    def test_reissue_pointing_at_confirmed_original_still_groups(
        self, http: Client, message: InboxMessage, payment: ContractPayment, contract: Contract
    ) -> None:
        """真实样本形态：原票 intake 早已确认（不在 pending 列表）也要能拼出重开段。

        回归锚点：旧实现按 ``supersedes_intake_id__in=<本批 pending ids>`` 查重开票，
        而重开票指向的是**已确认**的原票 intake（永远不在本批），结果重开段恒为 None。
        """
        original, red, reissue, _invoice = _red_triplet(message, payment, contract)

        # 只把红票放进「本批」（模拟首页列表：已确认的原票不在其中）
        from apps.contracts.services.payment.invoice_intake_service import red_group_facts

        groups = red_group_facts([red])

        assert groups[red.pk] is not None
        assert groups[red.pk]["original"]["intake_id"] == original.pk
        assert groups[red.pk]["reissue"]["intake_id"] == reissue.pk

    def test_red_without_original_in_library_has_null_original(
        self, http: Client, message: InboxMessage
    ) -> None:
        """原票不在库：组仍成立（红票段必填），original 为 None。"""
        red = _intake(
            message,
            invoice_number=RED_NUMBER,
            total_amount=Decimal("-10000.00"),
            red_against_number="55555555555555555555",
        )

        group = http.get(f"{PREFIX}/{red.pk}").json()["reatch_group"]

        assert group["group_key"] == "red:55555555555555555555"
        assert group["original"] is None
        assert group["red"]["intake_id"] == red.pk
        assert group["reissue"] is None

    def test_red_without_reissue_still_grouped(
        self, http: Client, message: InboxMessage, payment: ContractPayment, contract: Contract
    ) -> None:
        """只有红票没有重开（半组状态）必须能表达。"""
        _original, red, reissue, _inv = _red_triplet(message, payment, contract)
        reissue.supersedes_intake = None
        reissue.save(update_fields=["supersedes_intake"])

        group = http.get(f"{PREFIX}/{red.pk}").json()["reatch_group"]

        assert group["reissue"] is None
        assert group["original"] is not None

    def test_offset_resolved_by_number_when_fk_missing(
        self, http: Client, message: InboxMessage, payment: ContractPayment, contract: Contract
    ) -> None:
        """历史脏数据：入池时扫描层还没写 ``offset_invoice``，只能按票号现查。"""
        original_invoice = Invoice.objects.create(
            payment=payment,
            file_path="invoices/original.pdf",
            original_filename="original.pdf",
            invoice_number=ORIGINAL_NUMBER,
            total_amount=Decimal("10000.00"),
        )
        red = _intake(
            message,
            invoice_number=RED_NUMBER,
            total_amount=Decimal("-10000.00"),
            red_against_number=ORIGINAL_NUMBER,
        )

        group = http.get(f"{PREFIX}/{red.pk}").json()["reatch_group"]

        assert group["original"]["invoice_id"] == original_invoice.pk
        # 原票从未经过 intake 链路 → intake_id 为空，但发票段仍然给得出
        assert group["original"]["intake_id"] is None

    def test_pending_list_carries_group(
        self, http: Client, message: InboxMessage, payment: ContractPayment, contract: Contract
    ) -> None:
        _original, red, _reissue, _inv = _red_triplet(message, payment, contract)

        rows = http.get(f"{PREFIX}/pending").json()

        by_id = {row["id"]: row for row in rows}
        assert by_id[red.pk]["reatch_group"]["group_key"] == f"red:{ORIGINAL_NUMBER}"


# ── 3. 新端点 ────────────────────────────────────────────


@pytest.mark.django_db
class TestRedEndpoints:
    def test_confirm_red_reenact_forwards_arguments(
        self, http: Client, monkeypatch: pytest.MonkeyPatch, message: InboxMessage
    ) -> None:
        intake = _intake(message, invoice_number=RED_NUMBER, total_amount=Decimal("-10000.00"), red_against_number=ORIGINAL_NUMBER)
        captured: dict[str, Any] = {}

        def _fake_confirm(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            intake.status = InvoiceIntakeStatus.CONFIRMED
            return {"red_intake": intake}

        monkeypatch.setattr(
            "apps.contracts.services.payment.invoice_intake_service.confirm_red_reenact", _fake_confirm
        )

        resp = http.post(
            f"{PREFIX}/{intake.pk}/confirm-red-reenact",
            data={"new_intake_id": 42, "note": "重开不等额", "amount_override": True},
            content_type="application/json",
        )

        assert resp.status_code == 200, resp.content
        assert captured["red_intake_id"] == intake.pk
        assert captured["new_intake_id"] == 42
        assert captured["note"] == "重开不等额"
        assert captured["amount_override"] is True
        assert resp.json()["status"] == InvoiceIntakeStatus.CONFIRMED

    def test_confirm_red_only_forwards_arguments(
        self, http: Client, monkeypatch: pytest.MonkeyPatch, message: InboxMessage
    ) -> None:
        intake = _intake(message, invoice_number=RED_NUMBER, total_amount=Decimal("-10000.00"), red_against_number=ORIGINAL_NUMBER)
        captured: dict[str, Any] = {}

        def _fake_confirm_only(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            intake.status = InvoiceIntakeStatus.CONFIRMED
            return {"red_intake": intake}

        monkeypatch.setattr("apps.contracts.services.payment.invoice_intake_service.confirm_red_only", _fake_confirm_only)

        resp = http.post(
            f"{PREFIX}/{intake.pk}/confirm-red-only",
            data={"note": "客户不要这张票"},
            content_type="application/json",
        )

        assert resp.status_code == 200, resp.content
        assert captured["red_intake_id"] == intake.pk
        assert captured["note"] == "客户不要这张票"

    def test_reparse_endpoint_returns_action(self, http: Client, monkeypatch: pytest.MonkeyPatch, message: InboxMessage) -> None:
        intake = _intake(message, invoice_number=RED_NUMBER, total_amount=None)

        def _fake_reparse(**kwargs: Any) -> InvoiceIntake:
            assert kwargs["intake_id"] == intake.pk
            return intake

        monkeypatch.setattr("apps.contracts.services.payment.invoice_intake_service.reparse_invoice_intake", _fake_reparse)

        resp = http.post(f"{PREFIX}/{intake.pk}/reparse", data={}, content_type="application/json")

        assert resp.status_code == 200, resp.content
        assert resp.json()["success"] is True
        assert resp.json()["intake_id"] == intake.pk

    def test_routes_are_registered(self, http: Client, message: InboxMessage) -> None:
        """三条路径必须真的通（挂漏了前端只会拿到 404，很难查）。

        不用路由表内省：ninja 的 ``api_v1`` 是嵌套 add_router 装配的，
        子 router 的 path 在挂载前是空串，内省出来的结果不可信。

        这里不只看状态码——只看 ``!= 404`` 无法区分“路由通了但业务未接通”。
        构造一张**不满足守卫条件**的票（金é为负、无合同、无附件），让请求穿过
        路由直达 Service 层，然后断言它给出了**业务错误码**：
        能拿到 Service 抛出的业务码，就证明路由已挂、参数已解析、Service 已接通
        三件事同时成立（404/405/422 给不出这种东西）。
        """
        intake = _intake(message, invoice_number=RED_NUMBER, total_amount=Decimal("-1.00"))

        # 两条冲红端点：先撞“红字发票未匹配到项目”（在 G1 之前），同样是 Service 层业务码
        for path in (
            f"{PREFIX}/{intake.pk}/confirm-red-reenact",
            f"{PREFIX}/{intake.pk}/confirm-red-only",
        ):
            resp = http.post(path, data={}, content_type="application/json")
            assert resp.status_code != 404, f"{path} 未注册"
            body = resp.json()
            assert body.get("success") is False, (path, body)
            assert body.get("code") == "INVOICE_INTAKE_NO_CONTRACT", (path, body)

        # reparse 走另一个分支：附件不存在时应报“附件已不在磁盘上”
        resp = http.post(f"{PREFIX}/{intake.pk}/reparse", data={}, content_type="application/json")
        assert resp.status_code != 404
        body = resp.json()
        assert body.get("success") is False
        assert body.get("code") == "INVOICE_FILE_MISSING", body


# ── 4. 老端点守卫（§5.3）─────────────────────────────────


@pytest.mark.django_db
class TestConfirmGuard:
    def test_red_intake_cannot_use_confirm_endpoint(
        self, http: Client, monkeypatch: pytest.MonkeyPatch, message: InboxMessage, contract: Contract
    ) -> None:
        intake = _intake(
            message,
            invoice_number=RED_NUMBER,
            total_amount=Decimal("-10000.00"),
            red_against_number=ORIGINAL_NUMBER,
            suggested_contract=contract,
        )

        def _must_not_be_called(**kwargs: Any) -> None:
            raise AssertionError("红票不得触达 confirm_invoice_intake")

        monkeypatch.setattr(
            "apps.contracts.services.payment.invoice_intake_service.confirm_invoice_intake", _must_not_be_called
        )

        resp = http.post(f"{PREFIX}/{intake.pk}/confirm", data={}, content_type="application/json")

        assert resp.status_code == 400
        assert resp.json()["code"] == "INVOICE_RED_USE_DEDICATED_ENDPOINT"

    def test_blue_intake_still_uses_confirm_endpoint(
        self, http: Client, monkeypatch: pytest.MonkeyPatch, message: InboxMessage, contract: Contract
    ) -> None:
        """守卫只拦红票，蓝票路径不受影响（回归保护）。"""
        intake = _intake(
            message,
            invoice_number=ORIGINAL_NUMBER,
            total_amount=Decimal("10000.00"),
            suggested_contract=contract,
        )
        called: dict[str, Any] = {}

        def _fake_confirm(**kwargs: Any) -> InvoiceIntake:
            called.update(kwargs)
            intake.status = InvoiceIntakeStatus.CONFIRMED
            return intake

        monkeypatch.setattr(
            "apps.contracts.services.payment.invoice_intake_service.confirm_invoice_intake", _fake_confirm
        )

        resp = http.post(f"{PREFIX}/{intake.pk}/confirm", data={}, content_type="application/json")

        assert resp.status_code == 200, resp.content
        assert called["intake_id"] == intake.pk


# ── 5. 层归属 ────────────────────────────────────────────


class TestLayerDiscipline:
    def test_api_module_has_no_model_objects(self) -> None:
        """四层架构基线 0：ORM 一律在 Service，API 只做参数与响应装配。"""
        from pathlib import Path

        source_path = Path(__file__).resolve().parents[4] / "apps" / "contracts" / "api" / "invoice_intake_api.py"
        assert ".objects." not in source_path.read_text(encoding="utf-8")

    def test_group_facts_live_in_service(self) -> None:
        from apps.contracts.services.payment.invoice_intake_service import red_group_facts

        assert callable(red_group_facts)


# ── 6. 管理后台 ──────────────────────────────────────────


@pytest.mark.django_db
class TestAdminRedSupport:
    def test_list_display_has_red_columns(self) -> None:
        from apps.contracts.admin.invoice_intake_admin import InvoiceIntakeAdmin

        assert "is_red" in InvoiceIntakeAdmin.list_display
        assert "red_against_number" in InvoiceIntakeAdmin.list_display

    def test_fieldsets_have_red_group_readonly(self) -> None:
        from apps.contracts.admin.invoice_intake_admin import InvoiceIntakeAdmin

        red_fieldset = next(
            (fs for fs in InvoiceIntakeAdmin.fieldsets if "冲红信息" in str(fs[0])),
            None,
        )
        assert red_fieldset is not None
        fields = red_fieldset[1]["fields"]
        assert "is_red" in fields
        assert "red_against_number" in fields
        assert "red_confirmation_no" in fields
        assert "offset_invoice" in fields

    def test_red_badge_renders(self, message: InboxMessage) -> None:
        from django.contrib.admin.sites import AdminSite

        from apps.contracts.admin.invoice_intake_admin import InvoiceIntakeAdmin

        model_admin = InvoiceIntakeAdmin(InvoiceIntake, AdminSite())
        red = _intake(message, invoice_number=RED_NUMBER, total_amount=Decimal("-10000.00"))
        blue = _intake(message, invoice_number=ORIGINAL_NUMBER, total_amount=Decimal("10000.00"))

        assert "红字" in str(model_admin.is_red(red))
        assert "红字" not in str(model_admin.is_red(blue))

    def test_filter_finds_red_without_original(
        self, message: InboxMessage, payment: ContractPayment, contract: Contract
    ) -> None:
        """巡检：红票但原票不在库（按票号找不到任何 ``Invoice``）。"""
        from apps.contracts.admin.invoice_intake_admin import RedAgainstMissingFilter

        dangling = _intake(
            message,
            invoice_number=RED_NUMBER,
            total_amount=Decimal("-10000.00"),
            red_against_number="77777777777777777777",  # 系统里不存在的票号
        )
        _original, linked_red, _reissue, _inv = _red_triplet(message, payment, contract)

        class _Request:
            pass

        flt = RedAgainstMissingFilter.__new__(RedAgainstMissingFilter)
        flt.value = lambda: "missing"  # type: ignore[method-assign]

        matched = set(flt.queryset(_Request(), InvoiceIntake.objects.all()).values_list("pk", flat=True))

        assert dangling.pk in matched
        assert linked_red.pk not in matched
