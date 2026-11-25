"""审查接口：发起 / 看清单 / 逐条决策 / 批量采纳 / 一页纸。

**为什么这里要 patch 掉 `_dispatch`**：接口层把执行丢后台（线程或 django-q），
而测试用例被包在一个事务里，子线程看不到这个事务里的数据。所以测试里把分发
换成 no-op，再**同步**调用 `execute_run`——测的是接口契约，不是队列。

后台那条路（`apps/doc_workspace/tasks.py`）在 `test_review_task.py` 里单独测。
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from docx import Document

from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService
from apps.doc_workspace.api import review_api
from apps.doc_workspace.models import Finding, RejectReason
from apps.doc_workspace.services import review_pipeline

pytestmark = pytest.mark.django_db

KIND = "contract"
OWNER_ID = 916
SUBPATH = "1-合同/a.docx"
P1 = "甲方愿意支付人民币壹万元整。"


class _Service(BoundFolderBrowseService):
    root: Path

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def _require_access(self, **_kw: Any) -> None:
        return None

    def _local_root(self, _owner_id: int) -> Path:
        return self.root


@pytest.fixture
def wired(monkeypatch: Any, tmp_path: Path) -> Path:
    d = tmp_path / "1-合同"
    d.mkdir(parents=True)
    doc = Document()
    doc.add_paragraph(P1)
    buf = io.BytesIO()
    doc.save(buf)
    (d / "a.docx").write_bytes(buf.getvalue())

    from apps.contracts.services.contract.integrations import folder_browse_service as mod

    monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(tmp_path))
    # 队列换成 no-op：测试自己同步执行
    monkeypatch.setattr(review_api, "_dispatch", lambda _run_id: (True, ""))
    return tmp_path


def _payload() -> list[dict[str, Any]]:
    return [
        {
            "rule_key": "breach.liquidated_damages_cap",
            "verdict": "missing",
            "severity": "high",
            "quote": "",
            "title": "缺少违约金上限",
            "reason": "无上限可能被判赔超过实际损失",
            "impact": "可能承担合同价款 30% 以上的赔偿",
            "suggestion_original": P1,
            "suggestion_replacement": "甲方同意支付人民币壹万元整，违约金以合同总价款的 20% 为限。",
        },
        {
            "rule_key": "confidentiality.scope",
            "verdict": "missing",
            "severity": "low",
            "quote": "",
            "title": "缺少保密条款",
            "reason": "未约定保密信息范围",
            "impact": "商业信息泄露",
            "suggestion_original": "",
            "suggestion_replacement": "",
            "suggestion_note": "建议补充保密条款并明确例外情形。",
        },
    ]


def _start(client: Any, monkeypatch: Any, payload: list[dict[str, Any]] | None = None) -> int:
    response = client.post(
        "/api/v1/doc-workspace/review/runs",
        data=json.dumps({"kind": KIND, "owner_id": OWNER_ID, "subpath": SUBPATH}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    run_id = int(response.json()["run_id"])

    from apps.doc_workspace.models import ReviewRun

    run = ReviewRun.objects.get(id=run_id)
    review_pipeline.execute_run(run, caller=lambda _m: json.dumps(payload or _payload(), ensure_ascii=False))
    return run_id


class TestStartAndRead:
    def test_start_creates_queued_run(self, wired: Path, authenticated_client: Any) -> None:
        response = authenticated_client.post(
            "/api/v1/doc-workspace/review/runs",
            data=json.dumps({"kind": KIND, "owner_id": OWNER_ID, "subpath": SUBPATH, "stance": "party_a"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["run_id"] > 0
        assert body["status"] == "queued"

    def test_latest_returns_findings_after_run(self, wired: Path, authenticated_client: Any, monkeypatch: Any) -> None:
        _start(authenticated_client, monkeypatch)

        body = authenticated_client.get(
            "/api/v1/doc-workspace/review/runs/latest",
            {"kind": KIND, "owner_id": OWNER_ID, "subpath": SUBPATH},
        ).json()

        assert body["status"] == "done"
        assert len(body["findings"]) == 2
        assert body["summary"]["total"] == 2
        assert body["findings"][0]["delivery"] in ("revision", "comment")

    def test_latest_without_run_returns_none_status(self, wired: Path, authenticated_client: Any) -> None:
        body = authenticated_client.get(
            "/api/v1/doc-workspace/review/runs/latest",
            {"kind": KIND, "owner_id": OWNER_ID, "subpath": SUBPATH},
        ).json()
        assert body["status"] == "none"

    def test_meta_lists_enums(self, authenticated_client: Any) -> None:
        body = authenticated_client.get("/api/v1/doc-workspace/review/meta").json()
        assert {i["value"] for i in body["severity"]} == {"high", "medium", "low"}
        assert any(i["value"] == RejectReason.FALSE_POSITIVE for i in body["reject_reason"])


class TestDecide:
    def _first_finding(self, run_id: int) -> Finding:
        return Finding.objects.filter(run_id=run_id).order_by("ordinal").first()

    def test_accept_writes_revision_and_updates_status(
        self, wired: Path, authenticated_client: Any, monkeypatch: Any
    ) -> None:
        run_id = _start(authenticated_client, monkeypatch)
        finding = self._first_finding(run_id)

        body = authenticated_client.post(
            f"/api/v1/doc-workspace/review/findings/{finding.id}/decide",
            data=json.dumps({"action": "accept"}),
            content_type="application/json",
        ).json()

        assert body["ok"] is True
        assert body["status"] == "accepted"
        assert body["rev_ids"]

    def test_accept_with_missing_anchor_reports_stale_and_writes_nothing(
        self, wired: Path, authenticated_client: Any, monkeypatch: Any
    ) -> None:
        before = (wired / "1-合同" / "a.docx").read_bytes()
        payload = [
            {
                "rule_key": "subject.identity",
                "verdict": "deviation",
                "severity": "high",
                "quote": "文档里没有这句",
                "title": "主体信息不全",
                "reason": "缺统一社会信用代码",
                "impact": "合同可能无法履行，损失 10 万元",
                "suggestion_original": "文档里没有这句",
                "suggestion_replacement": "补上统一社会信用代码",
            }
        ]
        run_id = _start(authenticated_client, monkeypatch, payload)
        finding = self._first_finding(run_id)

        body = authenticated_client.post(
            f"/api/v1/doc-workspace/review/findings/{finding.id}/decide",
            data=json.dumps({"action": "accept"}),
            content_type="application/json",
        ).json()

        assert body["ok"] is False
        assert body["stale"] is True
        assert body["status"] == "stale"
        assert (wired / "1-合同" / "a.docx").read_bytes() == before

    def test_reject_requires_reason_code(self, wired: Path, authenticated_client: Any, monkeypatch: Any) -> None:
        run_id = _start(authenticated_client, monkeypatch)
        finding = self._first_finding(run_id)

        body = authenticated_client.post(
            f"/api/v1/doc-workspace/review/findings/{finding.id}/decide",
            data=json.dumps({"action": "reject"}),
            content_type="application/json",
        ).json()

        assert body["ok"] is False
        assert "理由码" in body["reason"]

    def test_reject_with_code_persists(self, wired: Path, authenticated_client: Any, monkeypatch: Any) -> None:
        run_id = _start(authenticated_client, monkeypatch)
        finding = self._first_finding(run_id)

        body = authenticated_client.post(
            f"/api/v1/doc-workspace/review/findings/{finding.id}/decide",
            data=json.dumps({"action": "reject", "reason_code": "commercial", "note": "谈判让步"}),
            content_type="application/json",
        ).json()

        assert body["ok"] is True
        finding.refresh_from_db()
        assert finding.status == "rejected"
        assert finding.reject_reason_code == "commercial"

    def test_moot_marks_terminal(self, wired: Path, authenticated_client: Any, monkeypatch: Any) -> None:
        run_id = _start(authenticated_client, monkeypatch)
        finding = self._first_finding(run_id)
        body = authenticated_client.post(
            f"/api/v1/doc-workspace/review/findings/{finding.id}/decide",
            data=json.dumps({"action": "moot"}),
            content_type="application/json",
        ).json()
        assert body["status"] == "moot"


class TestBulkAccept:
    def test_requires_confirm(self, wired: Path, authenticated_client: Any, monkeypatch: Any) -> None:
        run_id = _start(authenticated_client, monkeypatch)
        body = authenticated_client.post(
            f"/api/v1/doc-workspace/review/runs/{run_id}/bulk-accept",
            data=json.dumps({"severity": "high"}),
            content_type="application/json",
        ).json()
        assert body["accepted"] == 0
        assert "confirm" in body["details"][0]["reason"]

    def test_accepts_only_requested_severity(self, wired: Path, authenticated_client: Any, monkeypatch: Any) -> None:
        run_id = _start(authenticated_client, monkeypatch)

        body = authenticated_client.post(
            f"/api/v1/doc-workspace/review/runs/{run_id}/bulk-accept",
            data=json.dumps({"severity": "high", "confirm": True}),
            content_type="application/json",
        ).json()

        assert body["accepted"] == 1
        # 低危那条仍然待决
        assert Finding.objects.filter(run_id=run_id, status="proposed").count() == 1


class TestReport:
    def test_report_contains_top_items_and_disclaimer(
        self, wired: Path, authenticated_client: Any, monkeypatch: Any
    ) -> None:
        run_id = _start(authenticated_client, monkeypatch)
        body = authenticated_client.post(
            f"/api/v1/doc-workspace/review/runs/{run_id}/report",
            data=json.dumps({}),
            content_type="application/json",
        ).json()
        assert "审查要点" in body["markdown"]
        # 不承诺：AI 清单不是法律意见
        assert "不等于无风险" in body["markdown"]
