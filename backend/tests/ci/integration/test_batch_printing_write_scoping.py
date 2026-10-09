"""批量打印写权限收敛测试（安全审计 2026Q4 L-4）。

打印规则/预置是**全局**资源（一条规则决定全所文档落到哪台打印机），
历史上四个写端点只挂了 ``JWTOrSessionAuth()``，任何登录用户都能改。
本文件显式构造普通律师（非管理员），验证写操作被 403 拒绝、数据未被改动，
而读端点对普通用户保持开放（前端列表页需要）。
"""

from __future__ import annotations

import json

import pytest
from django.test import Client
from django.utils import timezone

from apps.batch_printing.models import PrintKeywordRule, PrintPresetSnapshot
from apps.organization.models import LawFirm, Lawyer


def _make_lawyer(username: str, *, is_admin: bool = False) -> Lawyer:
    firm, _ = LawFirm.objects.get_or_create(name=f"律所-{username}")
    return Lawyer.objects.create_user(
        username=username,
        password="testpass123",  # pragma: allowlist secret
        law_firm=firm,
        is_admin=is_admin,
    )


def _login(username: str) -> Client:
    client = Client()
    assert client.login(username=username, password="testpass123")  # pragma: allowlist secret
    return client


def _make_preset(printer_name: str = "canonprinter") -> PrintPresetSnapshot:
    return PrintPresetSnapshot.objects.create(
        printer_name=printer_name,
        printer_display_name="Canon Printer",
        preset_name="黑白双面",
        preset_source="mac_plist",
        raw_settings_payload={"number-up": "1"},
        executable_options_payload={"sides": "two-sided-long-edge"},
        supported_option_names=["sides"],
        last_synced_at=timezone.now(),
    )


def _make_rule(preset: PrintPresetSnapshot, keyword: str = "归档") -> PrintKeywordRule:
    return PrintKeywordRule.objects.create(
        keyword=keyword,
        priority=10,
        enabled=True,
        printer_name=preset.printer_name,
        preset_snapshot=preset,
        notes="默认规则",
    )


@pytest.mark.django_db
class TestBatchPrintingWriteScoping:
    def test_non_admin_cannot_create_rule(self) -> None:
        """L-4 核心：普通律师不能创建全局打印规则。"""
        _make_lawyer("bp_plain")
        preset = _make_preset()

        resp = _login("bp_plain").post(
            "/api/v1/batch-printing/rules",
            data=json.dumps({"keyword": "起诉状", "preset_snapshot_id": preset.id}),
            content_type="application/json",
        )

        assert resp.status_code == 403
        assert not PrintKeywordRule.objects.filter(keyword="起诉状").exists()

    def test_non_admin_cannot_update_rule(self) -> None:
        """改他人规则同样越权，且原数据必须保持不动。"""
        _make_lawyer("bp_plain2")
        preset = _make_preset()
        rule = _make_rule(preset)

        resp = _login("bp_plain2").put(
            f"/api/v1/batch-printing/rules/{rule.id}",
            data=json.dumps({"enabled": False, "notes": "被篡改"}),
            content_type="application/json",
        )

        assert resp.status_code == 403
        rule.refresh_from_db()
        assert rule.enabled is True
        assert rule.notes == "默认规则"

    def test_non_admin_cannot_delete_rule(self) -> None:
        _make_lawyer("bp_plain3")
        preset = _make_preset()
        rule = _make_rule(preset)

        resp = _login("bp_plain3").delete(f"/api/v1/batch-printing/rules/{rule.id}")

        assert resp.status_code == 403
        assert PrintKeywordRule.objects.filter(id=rule.id).exists()

    def test_non_admin_cannot_sync_presets(self) -> None:
        """同步预置会读写全所打印机配置，同属全局写操作。"""
        _make_lawyer("bp_plain4")
        preset = _make_preset("epsonprinter")

        resp = _login("bp_plain4").post("/api/v1/batch-printing/presets/sync", data={})

        assert resp.status_code == 403
        assert resp.json()["code"] == "BATCH_PRINT_ADMIN_REQUIRED"
        # 权限门外拦截：预置不该被改动
        assert PrintPresetSnapshot.objects.filter(id=preset.id).exists()
        assert PrintPresetSnapshot.objects.filter(id=preset.id).first().printer_name == "epsonprinter"

    def test_is_staff_alone_is_not_admin(self) -> None:
        """is_staff 仅是 Django admin 准入标志，不算系统管理员。

        与 reminders / message_hub / archive 收敛口径一致（2026Q4 审计收紧）。
        """
        firm, _ = LawFirm.objects.get_or_create(name="律所-bp_staff")
        Lawyer.objects.create_user(
            username="bp_staff",
            password="testpass123",  # pragma: allowlist secret
            law_firm=firm,
            is_staff=True,
        )
        preset = _make_preset("epsonprinter")

        resp = _login("bp_staff").post(
            "/api/v1/batch-printing/rules",
            data=json.dumps({"keyword": "判决书", "preset_snapshot_id": preset.id}),
            content_type="application/json",
        )

        assert resp.status_code == 403
        assert not PrintKeywordRule.objects.filter(keyword="判决书").exists()

    def test_admin_can_sync_presets(self) -> None:
        """管理员可同步预置。

        顺带固化存量路由修复：``/presets/sync`` 曾因排在 ``/presets/{preset_id}``
        之后被动态段吞掉，任何方法都返回 405，前端「同步预置」按钮一直是坏的。
        """
        _make_lawyer("bp_admin_sync", is_admin=True)

        resp = _login("bp_admin_sync").post("/api/v1/batch-printing/presets/sync", data={})

        # 同步依赖本机 plutil/LibreOffice 探测，此处只断言「路由可达且过了权限门」
        assert resp.status_code != 405
        assert resp.status_code != 403
        # 返回的是预设同步结果（探测到/落库条数），不是权限错误体
        body = resp.json()
        assert isinstance(body.get("discovered"), int)
        assert isinstance(body.get("upserted"), int)

    def test_admin_can_create_rule(self) -> None:
        """管理员不受影响——正向路径必须仍然通。"""
        _make_lawyer("bp_admin", is_admin=True)
        preset = _make_preset("brotherprinter")

        resp = _login("bp_admin").post(
            "/api/v1/batch-printing/rules",
            data=json.dumps({"keyword": "委托合同", "preset_snapshot_id": preset.id}),
            content_type="application/json",
        )

        assert resp.status_code == 200
        rule = PrintKeywordRule.objects.get(keyword="委托合同")
        assert rule.printer_name == "brotherprinter"

    def test_superuser_can_update_rule(self) -> None:
        firm, _ = LawFirm.objects.get_or_create(name="律所-bp_super")
        Lawyer.objects.create_superuser(
            username="bp_super",
            password="testpass123",  # pragma: allowlist secret
            law_firm=firm,
        )
        preset = _make_preset()
        rule = _make_rule(preset, keyword="超管规则")

        resp = _login("bp_super").put(
            f"/api/v1/batch-printing/rules/{rule.id}",
            data=json.dumps({"enabled": False}),
            content_type="application/json",
        )

        assert resp.status_code == 200
        rule.refresh_from_db()
        assert rule.enabled is False

    def test_anonymous_cannot_write(self) -> None:
        """未登录一律拒绝（router 层 JWTOrSessionAuth 的既有行为，此处固化）。"""
        preset = _make_preset()
        resp = Client().post(
            "/api/v1/batch-printing/rules",
            data=json.dumps({"keyword": "匿名", "preset_snapshot_id": preset.id}),
            content_type="application/json",
        )
        assert resp.status_code in (401, 403)
        assert not PrintKeywordRule.objects.filter(keyword="匿名").exists()

    def test_non_admin_can_still_read(self) -> None:
        """读保持开放：前端规则列表页要能加载（收敛只针对写）。"""
        _make_lawyer("bp_reader")
        preset = _make_preset()
        _make_rule(preset)

        resp = _login("bp_reader").get("/api/v1/batch-printing/rules")

        assert resp.status_code == 200
        assert len(resp.json()) >= 1
