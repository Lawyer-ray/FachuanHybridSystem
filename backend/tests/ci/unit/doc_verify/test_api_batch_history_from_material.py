"""批量裁决 / 核对历史 / 从收件箱附件直接核对：三条新端点的硬事实。

守三件事：

1. 批量裁决**逐条判**：一条脏 id 只跳过它自己，且每条各写一行（append-only，
   两次调用后历史行数会超过核对条数）；
2. `/runs` 是**全量**历史（含已裁决），分页 total 与 state 过滤都要对，外案 403；
3. `/runs/from-material` 的字节由服务端从收件箱取，取不到是 404（带 reason）不是 500。

API 用独立的 `NinjaAPI` 挂同一个 router，并接上仓库真实的异常处理器：既验状态码
映射（ValidationException→400、PermissionDenied→403、NotFoundError→404），又不依赖
`apiSystem` 全局装配的加载顺序。挂载点本身另有一条用例守（resolve 真实 URL）。
"""

from __future__ import annotations

import hashlib
from itertools import count
from typing import Any

import pytest
from django.urls import resolve
from django.utils import timezone
from ninja import NinjaAPI
from ninja.testing import TestClient

from apps.cases.models import CaseAssignment
from apps.core.exceptions import register_exception_handlers
from apps.doc_verify.api import router
from apps.doc_verify.domain.contracts import AssertionKind, Finding, Inbound, Report, Severity
from apps.doc_verify.models import CaptureSource, OutboundArtifact, VerificationDecision, VerificationRun, VerifyState
from apps.doc_verify.services.verify import deps
from apps.doc_verify.services.verify import from_material as from_material_service
from apps.message_hub.models import InboxMessage
from apps.message_hub.services.manual_upload_service import get_or_create_manual_source
from apps.testing.factories import CaseFactory, LawyerFactory

PDF_BYTES = b"%PDF-1.7 returned from client"

#: `/runs` 的对外字段集合。`from-material` 与 `/runs` 必须一字不差（同一份 run_detail）。
RUN_OUT_FIELDS = {
    "id",
    "artifact_id",
    "case_id",
    "case_name",
    "doc_type",
    "state",
    "state_label",
    "tier",
    "inbound_file_name",
    "inbound_sha256",
    "page_count",
    "findings",
    "coverage",
    "source_message_id",
    "created_at",
}

_SEQUENCE = count(1)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(scope="module")
def client() -> TestClient:
    api = NinjaAPI(urls_namespace="doc_verify_batch_history_test")
    register_exception_handlers(api)
    api.add_router("/doc-verify", router)
    return TestClient(api)


def _artifact(case: Any = None, *, doc_type: str = "起诉状") -> OutboundArtifact:
    return OutboundArtifact.objects.create(
        case=case,
        doc_type=doc_type,
        version="V4_20261106",
        file_name=f"{doc_type}_V4.pdf",
        file_sha256=_sha(b"%PDF-1.7 outbound baseline"),
        page_count=2,
        page_signatures=[[0.5, 0.25], [0.5, 0.25]],
        text_layer="诉讼请求：返还本金 100000 元",
        capture_source=CaptureSource.SEND_TO_CLIENT,
        verify_required=True,
    )


def _run(artifact: OutboundArtifact, *, state: str = VerifyState.CHANGED) -> VerificationRun:
    return VerificationRun.objects.create(
        artifact=artifact,
        run_key=f"batch-history-{next(_SEQUENCE)}",
        state=state,
        inbound_sha256=_sha(PDF_BYTES),
        page_count=2,
    )


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


def _patch_deps(monkeypatch: pytest.MonkeyPatch, *, findings: list[Finding] | None = None) -> None:
    """替换比对引擎与提取器：这两个依赖的真实实现有自己的单测，这里只验 API 形状。"""

    def fake_extract(data: bytes, file_name: str = "") -> Any:
        return Inbound(
            sha256=_sha(data),
            page_count=2,
            page_signatures=((0.5, 0.25), (0.5, 0.25)),
            text="诉讼请求：返还本金 10000 元",
            file_name=file_name,
        )

    def fake_compare(baseline: Any, inbound: Any, *, tier: int = 0) -> Any:
        return Report(findings=list(findings or []), coverage={}, tier=tier)

    monkeypatch.setattr(deps, "extract_document", fake_extract)
    monkeypatch.setattr(deps, "compare_documents", fake_compare)


def _message(operator: Any, *, part_indexes: tuple[int, ...] = (0,)) -> InboxMessage:
    """一条属于 `operator` 的材料包消息（上传人本人可见，见 `inbox_access`）。"""
    return InboxMessage.objects.create(
        source=get_or_create_manual_source(),
        message_id=f"material-{next(_SEQUENCE)}",
        subject="回传件",
        received_at=timezone.now(),
        has_attachments=True,
        uploaded_by=operator,
        attachments_meta=[
            {
                "filename": f"回传件_{index}.pdf",
                "original_filename": f"回传件_{index}.pdf",
                "content_type": "application/pdf",
                "size": len(PDF_BYTES),
                "part_index": index,
            }
            for index in part_indexes
        ],
    )


class _StubFetcher:
    """替掉真实 fetcher：本用例只验「字节从收件箱来」，不验 IMAP / 本地读盘。"""

    def __init__(self, *, content: bytes = PDF_BYTES, error: Exception | None = None) -> None:
        self._content = content
        self._error = error

    def download_attachment(self, source: Any, message_id: str, part_index: int) -> tuple[bytes, str, str]:
        if self._error is not None:
            raise self._error
        return self._content, "回传件.pdf", "application/pdf"


def _stub_fetcher(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> None:
    stub = _StubFetcher(**kwargs)
    monkeypatch.setattr(from_material_service, "get_fetcher", lambda source_type: stub)


@pytest.mark.django_db
class TestBatchDecisions:
    def test_three_ids_with_one_already_decided(self, client: TestClient) -> None:
        artifact = _artifact()
        already = _run(artifact)
        pending_a = _run(artifact)
        pending_b = _run(artifact)
        VerificationDecision.objects.create(verification=already, action="accept", reason="之前已核")
        operator = LawyerFactory()

        response = client.post(
            "/doc-verify/decisions/batch",
            json={"run_ids": [already.id, pending_a.id, pending_b.id], "action": "reject", "reason": "金额不符"},
            auth=operator,
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["decided"] == 2
        assert body["skipped"] == 1
        by_run = {item["run_id"]: item for item in body["items"]}
        assert by_run[already.id]["skipped_reason"] == "ALREADY_DECIDED"
        assert "decision_id" in by_run[pending_a.id]
        assert "decision_id" in by_run[pending_b.id]
        new_rows = VerificationDecision.objects.filter(verification__in=[pending_a, pending_b])
        assert new_rows.count() == 2
        assert set(new_rows.values_list("action", flat=True)) == {"reject"}
        assert set(new_rows.values_list("reason", flat=True)) == {"金额不符"}
        assert set(new_rows.values_list("decided_by_id", flat=True)) == {operator.id}
        # 已有裁决的历史行一个字都没动
        assert VerificationDecision.objects.filter(verification=already).get().action == "accept"

    def test_dirty_ids_are_skipped_one_by_one(self, client: TestClient) -> None:
        case = CaseFactory()
        operator = LawyerFactory()
        CaseAssignment.objects.create(case=case, lawyer=operator)
        pending = _run(_artifact(case=case))
        not_needing_decision = _run(_artifact(case=case), state=VerifyState.IDENTICAL)
        foreign_case = CaseFactory()
        CaseAssignment.objects.create(case=foreign_case, lawyer=LawyerFactory())
        foreign = _run(_artifact(foreign_case))
        missing_id = 10_000_000

        response = client.post(
            "/doc-verify/decisions/batch",
            json={"run_ids": [pending.id, not_needing_decision.id, foreign.id, missing_id], "action": "accept"},
            auth=operator,
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert (body["decided"], body["skipped"]) == (1, 3)
        by_run = {item["run_id"]: item for item in body["items"]}
        assert "decision_id" in by_run[pending.id]
        assert by_run[not_needing_decision.id]["skipped_reason"] == "STATE_NOT_NEEDS_DECISION"
        assert by_run[foreign.id]["skipped_reason"] == "CASE_FORBIDDEN"
        assert by_run[missing_id]["skipped_reason"] == "RUN_NOT_FOUND"
        assert VerificationDecision.objects.filter(verification=foreign).count() == 0

    def test_repeated_batches_only_append(self, client: TestClient) -> None:
        """`reissue` 不关闭这一条，所以再裁一次会**新增**一行，而不是改掉旧行。"""
        artifact = _artifact()
        run = _run(artifact)
        operator = LawyerFactory()

        first = client.post(
            "/doc-verify/decisions/batch",
            json={"run_ids": [run.id], "action": "reissue", "reason": "要求重出"},
            auth=operator,
        )
        second = client.post(
            "/doc-verify/decisions/batch",
            json={"run_ids": [run.id], "action": "accept", "reason": "收到新版"},
            auth=operator,
        )

        assert first.json()["decided"] == 1, first.content
        assert second.json()["decided"] == 1, second.content
        rows = list(VerificationDecision.objects.filter(verification=run).order_by("id"))
        assert [row.action for row in rows] == ["reissue", "accept"]
        assert rows[0].reason == "要求重出"
        # 历史行数 > 核对条数：append-only 的直接证据
        assert len(rows) > VerificationRun.objects.filter(artifact=artifact).count()

    @pytest.mark.parametrize("run_ids", [[], list(range(1, 202))])
    def test_empty_or_oversized_batch_is_400(self, client: TestClient, run_ids: list[int]) -> None:
        response = client.post(
            "/doc-verify/decisions/batch",
            json={"run_ids": run_ids, "action": "accept"},
            auth=LawyerFactory(),
        )

        assert response.status_code == 400

    def test_invalid_action_is_400_and_writes_nothing(self, client: TestClient) -> None:
        run = _run(_artifact())

        response = client.post(
            "/doc-verify/decisions/batch",
            json={"run_ids": [run.id], "action": "approve"},
            auth=LawyerFactory(),
        )

        assert response.status_code == 400
        assert VerificationDecision.objects.filter(verification=run).count() == 0


@pytest.mark.django_db
class TestRunHistory:
    def test_total_state_filter_and_paging(self, client: TestClient) -> None:
        case = CaseFactory()
        operator = LawyerFactory()
        CaseAssignment.objects.create(case=case, lawyer=operator)
        first = _run(_artifact(case, doc_type="起诉状"), state=VerifyState.CHANGED)
        second = _run(_artifact(case, doc_type="证据清单"), state=VerifyState.IDENTICAL)
        third = _run(_artifact(case, doc_type="授权委托书"), state=VerifyState.CHANGED)

        response = client.get(f"/doc-verify/runs?case_id={case.id}", auth=operator)

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["total"] == 3
        assert [item["id"] for item in body["items"]] == [third.id, second.id, first.id]
        assert set(body["items"][0]) == RUN_OUT_FIELDS

        filtered = client.get(f"/doc-verify/runs?case_id={case.id}&state=changed", auth=operator).json()
        assert filtered["total"] == 2
        assert {item["state"] for item in filtered["items"]} == {VerifyState.CHANGED}

        paged = client.get(f"/doc-verify/runs?case_id={case.id}&limit=1&offset=1", auth=operator).json()
        assert paged["total"] == 3
        assert [item["id"] for item in paged["items"]] == [second.id]

    def test_limit_is_clamped_to_at_least_one(self, client: TestClient) -> None:
        case = CaseFactory()
        operator = LawyerFactory()
        CaseAssignment.objects.create(case=case, lawyer=operator)
        _run(_artifact(case))
        _run(_artifact(case))

        body = client.get(f"/doc-verify/runs?case_id={case.id}&limit=0", auth=operator).json()

        assert body["total"] == 2
        assert len(body["items"]) == 1

    def test_unknown_state_is_400(self, client: TestClient) -> None:
        case = CaseFactory()
        operator = LawyerFactory()
        CaseAssignment.objects.create(case=case, lawyer=operator)

        response = client.get(f"/doc-verify/runs?case_id={case.id}&state=approved", auth=operator)

        assert response.status_code == 400

    def test_foreign_case_is_403(self, client: TestClient) -> None:
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=LawyerFactory())
        _run(_artifact(case))

        response = client.get(f"/doc-verify/runs?case_id={case.id}", auth=LawyerFactory())

        assert response.status_code == 403


@pytest.mark.django_db
class TestRunFromMaterial:
    def test_takes_bytes_from_the_inbox_attachment(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        operator = LawyerFactory()
        artifact = _artifact()
        message = _message(operator)
        _patch_deps(monkeypatch, findings=[_red_finding()])
        _stub_fetcher(monkeypatch)

        response = client.post(
            "/doc-verify/runs/from-material",
            json={"artifact_id": artifact.id, "message_id": message.id, "part_index": 0},
            auth=operator,
        )

        assert response.status_code == 200, response.content
        body = response.json()
        # 与 `/runs` 完全同形（同一份 run_detail）
        assert set(body) == RUN_OUT_FIELDS
        assert body["artifact_id"] == artifact.id
        assert body["inbound_sha256"] == _sha(PDF_BYTES)
        assert body["inbound_file_name"] == "回传件.pdf"
        assert body["state"] == VerifyState.CHANGED
        # 结论要能指回「是哪一份材料跑出来的」
        assert body["source_message_id"] == message.id
        assert VerificationRun.objects.filter(artifact=artifact).count() == 1

    def test_missing_part_index_is_404_with_reason(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        operator = LawyerFactory()
        artifact = _artifact()
        message = _message(operator, part_indexes=(0,))
        _patch_deps(monkeypatch)
        _stub_fetcher(monkeypatch)

        response = client.post(
            "/doc-verify/runs/from-material",
            json={"artifact_id": artifact.id, "message_id": message.id, "part_index": 9},
            auth=operator,
        )

        assert response.status_code == 404, response.content
        assert response.json()["errors"]["reason"] == "附件不存在"
        assert VerificationRun.objects.filter(artifact=artifact).count() == 0

    def test_fetch_failure_is_404_not_500(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        operator = LawyerFactory()
        artifact = _artifact()
        message = _message(operator)
        _patch_deps(monkeypatch)
        _stub_fetcher(monkeypatch, error=ValueError("附件不存在: local_path 已失效"))

        response = client.post(
            "/doc-verify/runs/from-material",
            json={"artifact_id": artifact.id, "message_id": message.id, "part_index": 0},
            auth=operator,
        )

        assert response.status_code == 404, response.content
        assert "local_path 已失效" in response.json()["errors"]["reason"]
        assert VerificationRun.objects.filter(artifact=artifact).count() == 0

    def test_unknown_message_is_404(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        operator = LawyerFactory()
        artifact = _artifact()
        _patch_deps(monkeypatch)
        _stub_fetcher(monkeypatch)

        response = client.post(
            "/doc-verify/runs/from-material",
            json={"artifact_id": artifact.id, "message_id": 10_000_000, "part_index": 0},
            auth=operator,
        )

        assert response.status_code == 404
        assert response.json()["code"] == "INBOX_MESSAGE_NOT_FOUND"

    def test_foreign_case_is_403(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        operator = LawyerFactory()
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=LawyerFactory())
        artifact = _artifact(case)
        message = _message(operator)
        _patch_deps(monkeypatch)
        _stub_fetcher(monkeypatch)

        response = client.post(
            "/doc-verify/runs/from-material",
            json={"artifact_id": artifact.id, "message_id": message.id, "part_index": 0},
            auth=operator,
        )

        assert response.status_code == 403


def test_new_routes_are_mounted() -> None:
    """主装配里的 `/api/v1/doc-verify` 前缀（这三条挂了＝前端拿到 404）。"""
    batch = resolve("/api/v1/doc-verify/decisions/batch")
    assert "decisions/batch" in str(batch.route)

    history = resolve("/api/v1/doc-verify/runs")
    assert str(history.route).endswith("/runs")

    from_material = resolve("/api/v1/doc-verify/runs/from-material")
    assert str(from_material.route).endswith("/runs/from-material")
