"""Admin 接口层测试：权限、方法、上传校验、错误降级。

不调用真实 LLM（用 monkeypatch 替掉 analyze_contract），只验证 HTTP 契约——
真实模型调用在人工验收时覆盖，避免 CI 里出现网络依赖。
"""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.organization.models import Lawyer

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

OPTIONS_URL = "/admin/contracts/contract/auto-intake/options/"
ANALYZE_URL = "/admin/contracts/contract/auto-intake/analyze/"


@pytest.fixture
def admin_client(db: object) -> Client:
    lawyer = Lawyer.objects.create_user(username="intake_admin", password="pw-intake-123", is_staff=True, is_admin=True)
    lawyer.is_superuser = True
    lawyer.save()
    client = Client()
    client.force_login(lawyer)
    return client


class TestOptionsEndpoint:
    def test_requires_login(self) -> None:
        response = Client().get(OPTIONS_URL)
        # 未登录被 admin 登录墙拦下：302 跳登录页（带 next），或 403 拒绝。
        # 只断状态码不够——必须确认**没有**返回业务数据（否则等于泄露模型列表）。
        assert response.status_code in (302, 403)
        if response.status_code == 302:
            assert "login" in response.headers.get("Location", "")
        else:
            assert response.get("Content-Type", "").startswith("text/html")
            assert b'"models"' not in response.content

    def test_returns_model_options(self, admin_client: Client) -> None:
        response = admin_client.get(OPTIONS_URL)
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        data = payload["data"]
        # 无平台配置时 llm_ready=False，但结构必须齐全（前端据此降级提示）
        assert "models" in data
        assert "accept" in data
        assert data["max_upload_mb"] > 0
        assert "llm_ready" in data


class TestAnalyzeEndpoint:
    def test_rejects_get(self, admin_client: Client) -> None:
        response = admin_client.get(ANALYZE_URL)
        assert response.status_code == 405
        # 405 必须带明确的错误体，前端据此提示而不是吞成"未知错误"
        payload = response.json()
        assert payload["ok"] is False
        assert payload["error"] == "Method not allowed"

    def test_requires_login(self) -> None:
        upload = SimpleUploadedFile("c.docx", b"x")
        response = Client().post(ANALYZE_URL, {"file": upload})
        # 未登录不得触发解析：要么跳登录页，要么 403 且不带任何解析结果
        assert response.status_code in (302, 403)
        if response.status_code == 302:
            assert "login" in response.headers.get("Location", "")
        else:
            assert b'"ok": true' not in response.content

    def test_missing_file(self, admin_client: Client) -> None:
        response = admin_client.post(ANALYZE_URL, {})
        assert response.status_code == 400
        assert "请选择" in response.json()["error"]

    def test_unsupported_extension(self, admin_client: Client) -> None:
        upload = SimpleUploadedFile("virus.exe", b"MZ")
        response = admin_client.post(ANALYZE_URL, {"file": upload})
        assert response.status_code == 400
        assert "不支持的文件类型" in response.json()["error"]

    def test_oversize_file(self, admin_client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.contracts.services.contract.intake import intake_service

        monkeypatch.setattr(intake_service, "MAX_UPLOAD_BYTES", 10)
        upload = SimpleUploadedFile("big.docx", b"x" * 100)
        response = admin_client.post(ANALYZE_URL, {"file": upload})
        assert response.status_code == 400
        assert "上限" in response.json()["error"]

    def test_llm_failure_returns_400_with_message(self, admin_client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.contracts.services.contract.intake import intake_service

        def _boom(**kwargs: object) -> dict[str, object]:
            raise intake_service.ContractIntakeError("大模型输出无法解析")

        monkeypatch.setattr(intake_service, "analyze_contract", _boom)
        upload = SimpleUploadedFile("c.docx", b"PK\x03\x04fake")
        response = admin_client.post(ANALYZE_URL, {"file": upload})
        assert response.status_code == 400
        assert "大模型输出无法解析" in response.json()["error"]

    def test_success_payload_shape(self, admin_client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.contracts.services.contract.intake import intake_service

        captured: dict[str, object] = {}

        def _fake_analyze(**kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {
                "draft": {"fields": {"name": "某公司_非诉"}, "parties": [], "lawyers": []},
                "document": {"filename": kwargs.get("filename")},
                "warnings": [],
                "model": kwargs.get("model_id"),
            }

        monkeypatch.setattr(intake_service, "analyze_contract", _fake_analyze)
        upload = SimpleUploadedFile("合同.docx", b"PK\x03\x04fake")
        response = admin_client.post(ANALYZE_URL, {"file": upload, "model": "kimi-2.6"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["data"]["draft"]["fields"]["name"] == "某公司_非诉"
        # 上传的模型名必须原样传给服务层（用户可自选模型）
        assert captured["model_id"] == "kimi-2.6"

    def test_temp_file_lands_under_tmp_for_cleanup(self, admin_client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
        """临时文件必须落在 MEDIA_ROOT/tmp 下，才能被既有定时清理任务覆盖。"""
        from django.conf import settings

        from apps.contracts.services.contract.intake import intake_service

        monkeypatch.setattr(intake_service, "analyze_contract", lambda **kwargs: {})
        upload = SimpleUploadedFile("合同.docx", b"PK\x03\x04fake")
        admin_client.post(ANALYZE_URL, {"file": upload})

        from pathlib import Path

        intake_dir = Path(settings.MEDIA_ROOT) / "tmp" / "contract_intake"
        assert intake_dir.is_dir()
        assert any(path.name.startswith("合同-") for path in intake_dir.iterdir())


class TestNoPersistence:
    def test_analysis_creates_no_contract_or_material(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """核心红线：AI 分析只产出草稿，绝不写业务表。"""
        from apps.contracts.models import Contract, FinalizedMaterial
        from apps.contracts.services.contract.intake import intake_service

        monkeypatch.setattr(
            intake_service,
            "analyze_contract",
            lambda **kwargs: {"draft": {"fields": {}}, "document": {}, "warnings": [], "model": ""},
        )
        before_contracts = Contract.objects.count()
        before_materials = FinalizedMaterial.objects.count()

        upload = SimpleUploadedFile("合同.docx", b"PK\x03\x04fake")
        admin_client.post(ANALYZE_URL, {"file": upload})

        assert Contract.objects.count() == before_contracts
        assert FinalizedMaterial.objects.count() == before_materials
