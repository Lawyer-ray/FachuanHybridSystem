"""策略落库 + 基线 API：勾选框背后真正生效的那两件事。

两条断言最要紧：
1. **库里没记录时回落到代码默认**（否则新案子默认全关，功能上线第一天就静默失效）；
2. **策略改完立刻影响基线冻结的 `verify_required`**（否则勾选框只是画着好看）。
"""

from __future__ import annotations

import base64

import pymupdf
import pytest
from ninja import NinjaAPI
from ninja.testing import TestClient

from apps.core.exceptions import register_exception_handlers
from apps.doc_verify.api import artifact_router, policy_router
from apps.doc_verify.models import OutboundArtifact, VerificationPolicy
from apps.doc_verify.services import policy_store
from apps.doc_verify.services.anchor.persist import create_artifact
from apps.doc_verify.services.verify.policy import HIGH_RISK_DOC_TYPES
from apps.testing.factories import CaseFactory, LawyerFactory


def _pdf(text: str = "民事起诉状 诉讼请求 10000 元") -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 100), text, fontsize=12, fontname="china-s")
    data = document.tobytes()
    document.close()
    return data


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@pytest.fixture(scope="module")
def client() -> TestClient:
    api = NinjaAPI(urls_namespace="doc_verify_policy_test")
    register_exception_handlers(api)
    api.add_router("/doc-verify", policy_router)
    api.add_router("/doc-verify", artifact_router)
    return TestClient(api)


@pytest.mark.django_db
class TestPolicyStore:
    def test_falls_back_to_code_default_when_nothing_stored(self) -> None:
        case = CaseFactory()
        items = policy_store.effective_items(case.pk)

        assert [item["doc_type"] for item in items] == list(HIGH_RISK_DOC_TYPES)
        assert all(item["enabled"] is True for item in items)
        assert all(item["default"] is True for item in items)

    def test_disabling_writes_a_row_and_is_immediately_effective(self) -> None:
        case = CaseFactory()
        policy_store.set_policy(case_id=case.pk, doc_types=["起诉状"], enabled=False)

        assert VerificationPolicy.objects.filter(case_id=case.pk, doc_type="起诉状", enabled=False).exists()
        assert policy_store.is_required(case_id=case.pk, doc_type="民事起诉状（一审）") is False
        # 没被改到的类别仍按默认（要核）
        assert policy_store.is_required(case_id=case.pk, doc_type="授权委托书") is True

    def test_empty_doc_types_means_all_high_risk(self) -> None:
        case = CaseFactory()
        items = policy_store.set_policy(case_id=case.pk, doc_types=[], enabled=False)

        assert all(item["enabled"] is False for item in items)

    def test_substring_match_tolerates_archival_naming(self) -> None:
        case = CaseFactory()
        policy_store.set_policy(case_id=case.pk, doc_types=["起诉状"], enabled=False)

        assert policy_store.is_required(case_id=case.pk, doc_type="起诉状_定稿_20261106") is False
        assert policy_store.is_required(case_id=case.pk, doc_type="民事起诉状") is False
        assert policy_store.is_required(case_id=case.pk, doc_type="证据清单") is False  # 默认也不核

    def test_without_case_uses_code_default(self) -> None:
        assert policy_store.is_required(case_id=None, doc_type="民事起诉状") is True
        assert policy_store.is_required(case_id=None, doc_type="证据清单") is False


@pytest.mark.django_db
class TestArtifactApi:
    def test_creates_baseline_with_policy_default(self, client: TestClient) -> None:
        case = CaseFactory()
        response = client.post(
            "/doc-verify/artifacts",
            json={
                "case_id": case.pk,
                "doc_type": "民事起诉状",
                "version": "V4_20261106",
                "file_name": "起诉状.pdf",
                "file_base64": _b64(_pdf()),
                "capture_source": "send_to_client",
            },
            auth=LawyerFactory(),
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["verify_required"] is True  # 高风险类默认要核
        assert body["page_count"] == 1
        assert body["file_sha256"]

    def test_explicit_flag_overrides_policy(self, client: TestClient) -> None:
        case = CaseFactory()
        policy_store.set_policy(case_id=case.pk, doc_types=["起诉状"], enabled=False)

        response = client.post(
            "/doc-verify/artifacts",
            json={
                "case_id": case.pk,
                "doc_type": "民事起诉状",
                "file_base64": _b64(_pdf("另一份起诉状 20000 元")),
                "verify_required": True,
            },
            auth=LawyerFactory(),
        )

        assert response.status_code == 200, response.content
        assert response.json()["verify_required"] is True

    def test_is_idempotent_on_same_bytes(self, client: TestClient) -> None:
        case = CaseFactory()
        payload = {
            "case_id": case.pk,
            "doc_type": "送达地址确认书",
            "version": "V1",
            "file_base64": _b64(_pdf("送达地址确认书 收件人 张三")),
        }

        first = client.post("/doc-verify/artifacts", json=payload, auth=LawyerFactory())
        second = client.post("/doc-verify/artifacts", json=payload, auth=LawyerFactory())

        assert first.json()["id"] == second.json()["id"]
        assert OutboundArtifact.objects.filter(case_id=case.pk).count() == 1

    def test_list_returns_case_baselines(self, client: TestClient) -> None:
        case = CaseFactory()
        _ = create_artifact(
            case=case,
            baseline=_baseline("授权委托书", _pdf("授权委托书 张三 李四")),
            verify_required=True,
        )

        response = client.get(f"/doc-verify/artifacts?case_id={case.pk}", auth=LawyerFactory())

        assert response.status_code == 200
        assert [item["doc_type"] for item in response.json()] == ["授权委托书"]

    def test_invalid_base64_is_400(self, client: TestClient) -> None:
        case = CaseFactory()
        response = client.post(
            "/doc-verify/artifacts",
            json={"case_id": case.pk, "doc_type": "起诉状", "file_base64": "不是 base64"},
            auth=LawyerFactory(),
        )

        assert response.status_code == 400
        assert response.json()["success"] is False


def _baseline(doc_type: str, data: bytes):
    from apps.doc_verify.services.anchor.capture import capture_baseline

    return capture_baseline(data=data, file_name=f"{doc_type}.pdf", doc_type=doc_type, version="V1")


@pytest.mark.django_db
class TestPolicyApi:
    def test_get_policy_returns_defaults(self, client: TestClient) -> None:
        case = CaseFactory()
        response = client.get(f"/doc-verify/policy?case_id={case.pk}", auth=LawyerFactory())

        assert response.status_code == 200
        assert {item["doc_type"] for item in response.json()["items"]} == set(HIGH_RISK_DOC_TYPES)

    def test_put_policy_turns_everything_off(self, client: TestClient) -> None:
        case = CaseFactory()
        response = client.put(
            "/doc-verify/policy",
            json={"case_id": case.pk, "enabled": False},
            auth=LawyerFactory(),
        )

        assert response.status_code == 200
        assert all(item["enabled"] is False for item in response.json()["items"])
        assert policy_store.is_required(case_id=case.pk, doc_type="民事起诉状") is False

    def test_unknown_case_is_404(self, client: TestClient) -> None:
        response = client.get("/doc-verify/policy?case_id=99999999", auth=LawyerFactory())
        assert response.status_code == 404
        assert response.json()["success"] is False

    def test_anonymous_is_rejected(self, client: TestClient) -> None:
        """没有操作人就没有留痕，读策略也拒（403 由全局异常处理器给出）。"""
        case = CaseFactory()
        response = client.get(f"/doc-verify/policy?case_id={case.pk}")
        assert response.status_code == 403
        assert response.json()["success"] is False
