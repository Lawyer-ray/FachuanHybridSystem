"""跨案件待裁决清单 + 案件可见性。

## 两条硬事实

1. `GET /pending` 是**跨案件**入口：只返回当前律师看得见的案子（`accessible_case_ids`），
   而且必须带 `case_name`——只有「起诉状」三个字的清单没法用；
2. 单案端点（`/unverified`、`/runs/{id}`）对外案要 **403**：知道 id 不等于有权看。
"""

from __future__ import annotations

import hashlib

import pytest
from django.urls import resolve
from ninja import NinjaAPI
from ninja.testing import TestClient

from apps.cases.models import CaseAssignment
from apps.core.exceptions import register_exception_handlers
from apps.doc_verify.api import router
from apps.doc_verify.models import CaptureSource, OutboundArtifact, VerificationRun, VerifyState
from apps.testing.factories import CaseFactory, LawyerFactory

PDF_SHA = hashlib.sha256(b"%PDF-1.7 outbound").hexdigest()


def _artifact(case, *, doc_type: str = "民事起诉状") -> OutboundArtifact:
    return OutboundArtifact.objects.create(
        case=case,
        doc_type=doc_type,
        version="V4",
        file_name="起诉状.pdf",
        file_sha256=PDF_SHA,
        page_count=1,
        text_layer="诉讼请求：10000 元",
        capture_source=CaptureSource.SEND_TO_CLIENT,
        verify_required=True,
    )


def _pending_run(artifact: OutboundArtifact) -> VerificationRun:
    return VerificationRun.objects.create(
        artifact=artifact,
        run_key=f"key-{artifact.pk}",
        state=VerifyState.CHANGED,
        tier=0,
        inbound_sha256=hashlib.sha256(b"inbound").hexdigest(),
        page_count=1,
        findings=[{"kind": "field", "code": "AMOUNT_MISMATCH", "title": "金额不一致", "severity": "red"}],
        coverage={},
    )


@pytest.fixture(scope="module")
def client() -> TestClient:
    api = NinjaAPI(urls_namespace="doc_verify_pending_test")
    register_exception_handlers(api)
    api.add_router("/doc-verify", router)
    return TestClient(api)


@pytest.mark.django_db
class TestPendingVisibility:
    def test_pending_only_returns_my_cases(self, client: TestClient) -> None:
        mine, theirs = CaseFactory(), CaseFactory()
        me, other = LawyerFactory(), LawyerFactory()
        CaseAssignment.objects.create(case=mine, lawyer=me)
        CaseAssignment.objects.create(case=theirs, lawyer=other)
        my_run = _pending_run(_artifact(mine))

        response = client.get("/doc-verify/pending", auth=me)

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [my_run.pk]
        # 全局清单必须能定位到是哪一件：只有「起诉状」三个字没有用
        assert body[0]["case_name"] == mine.name

    def test_pending_is_empty_for_a_lawyer_without_cases(self, client: TestClient) -> None:
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=LawyerFactory())
        _pending_run(_artifact(case))

        response = client.get("/doc-verify/pending", auth=LawyerFactory())

        assert response.status_code == 200
        assert response.json() == []

    def test_pending_honours_limit(self, client: TestClient) -> None:
        case = CaseFactory()
        me = LawyerFactory()
        CaseAssignment.objects.create(case=case, lawyer=me)
        for index in range(3):
            _pending_run(_artifact(case, doc_type=f"起诉状{index}"))

        assert len(client.get("/doc-verify/pending?limit=2", auth=me).json()) == 2

    def test_foreign_case_is_403_on_case_scoped_endpoints(self, client: TestClient) -> None:
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=LawyerFactory())
        run = _pending_run(_artifact(case))
        outsider = LawyerFactory()

        assert client.get(f"/doc-verify/unverified?case_id={case.pk}", auth=outsider).status_code == 403
        assert client.get(f"/doc-verify/runs/{run.pk}", auth=outsider).status_code == 403
        assert (
            client.post(f"/doc-verify/runs/{run.pk}/decision", json={"action": "accept"}, auth=outsider).status_code
            == 403
        )


def test_pending_route_is_mounted() -> None:
    """挂载点被真装配过：路径变了这里先红，而不是等前端 404。

    不断言 handler 函数名：Ninja 会把同步 handler 包一层 `sync_view_wrapper`，
    断言名字等于锁死实现细节。能 resolve 到 `/doc-verify` 前缀下的 pending 路由即已挂载。
    """
    match = resolve("/api/v1/doc-verify/pending")
    assert "pending" in str(match.route)
