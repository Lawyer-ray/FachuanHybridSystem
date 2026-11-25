"""核对 API：四个路由的 200 与 400/403/404 路径。

用独立的 `NinjaAPI` 挂同一个 router，并接上仓库的真实异常处理器：
既验证状态码映射（ValidationException→400、PermissionDenied→403、NotFoundError→404），
又不依赖 `apiSystem` 全局装配的加载顺序。挂载点本身另有一条用例守（resolve 真实 URL）。
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

import pytest
from django.urls import resolve
from ninja import NinjaAPI
from ninja.testing import TestClient

from apps.core.exceptions import register_exception_handlers
from apps.doc_verify.api import router
from apps.doc_verify.domain.contracts import AssertionKind, Finding, Inbound, Report, Severity
from apps.doc_verify.models import CaptureSource, OutboundArtifact, VerificationDecision, VerificationRun, VerifyState
from apps.doc_verify.services.verify import deps
from apps.testing.factories import CaseFactory, LawyerFactory

PDF_BYTES = b"%PDF-1.7 api payload"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@pytest.fixture(scope="module")
def client() -> TestClient:
    api = NinjaAPI(urls_namespace="doc_verify_api_test")
    register_exception_handlers(api)
    api.add_router("/doc-verify", router)
    return TestClient(api)


def _artifact(**overrides: Any) -> OutboundArtifact:
    values: dict[str, Any] = {
        "doc_type": "起诉状",
        "version": "V4_20261106",
        "file_name": "起诉状_V4.pdf",
        "file_sha256": _sha(b"%PDF-1.7 outbound baseline"),
        "page_count": 2,
        "page_signatures": [[0.5, 0.25], [0.5, 0.25]],
        "text_layer": "诉讼请求：返还本金 100000 元",
        "capture_source": CaptureSource.SEND_TO_CLIENT,
        "verify_required": True,
    }
    values.update(overrides)
    return OutboundArtifact.objects.create(**values)


def _run(artifact: OutboundArtifact, *, state: str = VerifyState.CHANGED) -> VerificationRun:
    return VerificationRun.objects.create(
        artifact=artifact,
        run_key=f"api-key-{artifact.id}-{state}",
        state=state,
        inbound_sha256=_sha(PDF_BYTES),
        page_count=2,
    )


def _patch_deps(
    monkeypatch: pytest.MonkeyPatch,
    *,
    findings: list[Finding] | None = None,
    coverage: dict[str, Any] | None = None,
) -> None:
    """替换 lane A/B 的依赖（本分支里它们可能还没上树）。"""

    def fake_extract(data: bytes, file_name: str = "") -> Any:
        return Inbound(
            sha256=_sha(data),
            page_count=2,
            page_signatures=((0.5, 0.25), (0.5, 0.25)),
            text="诉讼请求：返还本金 10000 元",
            file_name=file_name,
        )

    def fake_compare(baseline: Any, inbound: Any, *, tier: int = 0) -> Any:
        return Report(findings=list(findings or []), coverage=dict(coverage or {}), tier=tier)

    monkeypatch.setattr(deps, "extract_document", fake_extract)
    monkeypatch.setattr(deps, "compare_documents", fake_compare)


def _red_finding() -> Finding:
    return Finding(
        kind=AssertionKind.FIELD,
        code="field_mismatch",
        title="金额不一致",
        severity=Severity.RED,
        expected="100000",
        actual="10000",
        page=2,
    )


@pytest.mark.django_db
class TestCreateRunEndpoint:
    def test_returns_run_with_state_findings_and_coverage(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        artifact = _artifact()
        _patch_deps(monkeypatch, findings=[_red_finding()], coverage={"comparable_pages": 2})

        response = client.post(
            "/doc-verify/runs",
            json={
                "artifact_id": artifact.id,
                "file_base64": _b64(PDF_BYTES),
                "file_name": "回传件.pdf",
                "source_message_id": 7,
            },
            auth=LawyerFactory(),
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["artifact_id"] == artifact.id
        assert body["state"] == VerifyState.CHANGED
        assert body["state_label"] == "疑似改动"
        assert body["page_count"] == 2
        assert body["inbound_sha256"] == _sha(PDF_BYTES)
        assert body["findings"][0]["code"] == "field_mismatch"
        assert body["coverage"] == {"comparable_pages": 2}
        assert body["source_message_id"] == 7
        assert VerificationRun.objects.filter(artifact=artifact).count() == 1

    def test_accepts_data_url_prefixed_base64(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_deps(monkeypatch)

        response = client.post(
            "/doc-verify/runs",
            json={
                "artifact_id": artifact.id,
                "file_base64": f"data:application/pdf;base64,{_b64(PDF_BYTES)}",
            },
            auth=LawyerFactory(),
        )

        assert response.status_code == 200, response.content
        assert response.json()["inbound_sha256"] == _sha(PDF_BYTES)

    def test_repeated_post_reuses_the_same_run(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_deps(monkeypatch)
        payload = {"artifact_id": artifact.id, "file_base64": _b64(PDF_BYTES)}

        first = client.post("/doc-verify/runs", json=payload, auth=LawyerFactory()).json()
        second = client.post("/doc-verify/runs", json=payload, auth=LawyerFactory()).json()

        assert first["id"] == second["id"]
        assert VerificationRun.objects.filter(artifact=artifact).count() == 1

    @pytest.mark.parametrize("file_base64", ["", "   ", "not-base64!!"])
    def test_unusable_payload_is_400(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, file_base64: str
    ) -> None:
        artifact = _artifact()
        _patch_deps(monkeypatch)

        response = client.post(
            "/doc-verify/runs",
            json={"artifact_id": artifact.id, "file_base64": file_base64},
            auth=LawyerFactory(),
        )

        assert response.status_code == 400
        assert "file_base64" in response.content.decode()

    def test_unknown_artifact_is_404(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_deps(monkeypatch)

        response = client.post(
            "/doc-verify/runs",
            json={"artifact_id": 10_000_000, "file_base64": _b64(PDF_BYTES)},
            auth=LawyerFactory(),
        )

        assert response.status_code == 404
        assert response.json()["success"] is False

    def test_tier_outside_the_contract_is_400(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_deps(monkeypatch)

        response = client.post(
            "/doc-verify/runs",
            json={"artifact_id": artifact.id, "file_base64": _b64(PDF_BYTES), "tier": 5},
            auth=LawyerFactory(),
        )

        assert response.status_code == 400
        assert VerificationRun.objects.filter(artifact=artifact).count() == 0


@pytest.mark.django_db
class TestGetRunEndpoint:
    def test_returns_run_detail(self, client: TestClient) -> None:
        run = _run(_artifact())

        response = client.get(f"/doc-verify/runs/{run.id}", auth=LawyerFactory())

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == run.id
        assert body["doc_type"] == "起诉状"
        assert body["state"] == VerifyState.CHANGED

    def test_unknown_run_is_404(self, client: TestClient) -> None:
        response = client.get("/doc-verify/runs/9999999", auth=LawyerFactory())

        assert response.status_code == 404
        # 断言错误体而不只是状态码：前端靠这条 envelope 决定提示什么
        assert response.json()["success"] is False


@pytest.mark.django_db
class TestDecisionEndpoint:
    def test_records_decision_with_operator_from_request_auth(self, client: TestClient) -> None:
        run = _run(_artifact())
        lawyer = LawyerFactory()

        response = client.post(
            f"/doc-verify/runs/{run.id}/decision",
            json={"action": "accept", "reason": "已核对原件"},
            auth=lawyer,
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["verification_id"] == run.id
        assert body["action"] == "accept"
        assert body["reason"] == "已核对原件"
        assert body["decided_by_id"] == lawyer.id
        assert VerificationDecision.objects.filter(verification=run).count() == 1

    def test_falls_back_to_request_user(self, client: TestClient) -> None:
        run = _run(_artifact())
        lawyer = LawyerFactory()

        response = client.post(
            f"/doc-verify/runs/{run.id}/decision",
            json={"action": "reject"},
            user=lawyer,
        )

        assert response.status_code == 200, response.content
        assert response.json()["decided_by_id"] == lawyer.id

    def test_missing_operator_is_403(self, client: TestClient) -> None:
        run = _run(_artifact())

        response = client.post(f"/doc-verify/runs/{run.id}/decision", json={"action": "accept"})

        assert response.status_code == 403
        assert VerificationDecision.objects.filter(verification=run).count() == 0

    def test_invalid_action_is_400(self, client: TestClient) -> None:
        run = _run(_artifact())

        response = client.post(
            f"/doc-verify/runs/{run.id}/decision",
            json={"action": "approve"},
            auth=LawyerFactory(),
        )

        assert response.status_code == 400
        assert VerificationDecision.objects.filter(verification=run).count() == 0

    def test_unknown_run_is_404(self, client: TestClient) -> None:
        response = client.post(
            "/doc-verify/runs/9999999/decision",
            json={"action": "accept"},
            auth=LawyerFactory(),
        )

        assert response.status_code == 404
        assert response.json()["success"] is False


@pytest.mark.django_db
class TestUnverifiedEndpoint:
    def test_lists_pending_runs_of_the_case(self, client: TestClient) -> None:
        case = CaseFactory()
        artifact = _artifact(case=case, doc_type="授权委托书")
        pending = _run(artifact, state=VerifyState.UNVERIFIABLE)

        response = client.get(f"/doc-verify/unverified?case_id={case.id}", auth=LawyerFactory())

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [pending.id]
        assert body[0]["doc_type"] == "授权委托书"
        assert body[0]["case_id"] == case.id

    def test_case_without_pending_runs_returns_empty_list(self, client: TestClient) -> None:
        case = CaseFactory()

        response = client.get(f"/doc-verify/unverified?case_id={case.id}", auth=LawyerFactory())

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.parametrize("case_id", [0, -3])
    def test_non_positive_case_id_is_400(self, client: TestClient, case_id: int) -> None:
        response = client.get(f"/doc-verify/unverified?case_id={case_id}", auth=LawyerFactory())

        assert response.status_code == 400
        assert response.json()["success"] is False


def test_router_is_mounted_on_the_main_api() -> None:
    """主装配里的 `/api/v1/doc-verify` 前缀（这条挂了＝前端拿到 404）。"""
    match = resolve("/api/v1/doc-verify/unverified")
    assert match.func is not None
