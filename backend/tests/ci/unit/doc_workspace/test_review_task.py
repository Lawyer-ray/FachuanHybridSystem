"""后台任务入口：幂等、失败态、找不到轮次。

**为什么单独测**：接口层把执行丢后台，`tasks.execute_review_run` 是那条路上唯一的
入口。它必须幂等——队列重投、手动重跑都不能把已完成的轮次再跑一遍（会重复消耗
模型额度，还可能覆盖律师已经决策过的状态）。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.doc_workspace.models import ReviewRun, RunStatus
from apps.doc_workspace.services import review_pipeline
from apps.doc_workspace.tasks import execute_review_run

pytestmark = pytest.mark.django_db


def _builtin_snapshot() -> list[dict[str, Any]]:
    from apps.doc_workspace.services import playbook_service

    return playbook_service.snapshot_rules(playbook_service.ensure_builtin())


def _run(**kw: Any) -> ReviewRun:
    defaults = {
        "owner_kind": "contract",
        "owner_id": 1,
        "subpath": "a.docx",
        "status": RunStatus.QUEUED,
        # 必须给真实的标准快照：空快照会让所有结论被当成「自创检查项」丢掉
        "playbook_snapshot": _builtin_snapshot(),
        "stance": "neutral",
        "contract_type": "",
    }
    defaults.update(kw)
    return ReviewRun.objects.create(**defaults)


def test_missing_run_is_a_soft_failure() -> None:
    assert execute_review_run(999999) == {"ok": False, "reason": "run_not_found"}


def test_done_run_is_skipped(monkeypatch: Any) -> None:
    run = _run(status=RunStatus.DONE)

    def boom(*_a: Any, **_kw: Any) -> None:
        raise AssertionError("已完成的轮次不该重跑")

    monkeypatch.setattr(review_pipeline, "execute_run", boom)
    assert execute_review_run(run.id)["skipped"] is True


def test_queued_run_executes(monkeypatch: Any) -> None:
    run = _run()
    monkeypatch.setattr(
        review_pipeline, "execute_run", lambda r, **_kw: review_pipeline.review_model.finish_run(r)
    )
    result = execute_review_run(run.id)
    assert result["ok"] is True
    run.refresh_from_db()
    assert run.status == RunStatus.DONE


def test_execute_marks_failed_on_llm_error(monkeypatch: Any) -> None:
    """模型挂了必须落成 failed，不能永远停在 running。"""
    run = _run()

    def boom(_messages: list[dict[str, str]]) -> str:
        raise RuntimeError("模型超时")

    review_pipeline.execute_run(run, caller=boom, text="甲方愿意支付人民币壹万元整。")
    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert "模型超时" in run.error_message


def test_execute_is_idempotent_on_findings(monkeypatch: Any) -> None:
    """重跑同一轮不会把清单翻倍。"""
    run = _run()
    payload = [
        {
            "rule_key": "subject.identity",
            "verdict": "missing",
            "severity": "high",
            "title": "主体信息缺失",
            "reason": "缺统一社会信用代码",
            "impact": "可能影响合同效力，损失 10 万元",
        }
    ]
    caller = lambda _m: json.dumps(payload, ensure_ascii=False)  # noqa: E731

    review_pipeline.execute_run(run, caller=caller, text="甲方愿意支付人民币壹万元整。")
    review_pipeline.execute_run(run, caller=caller, text="甲方愿意支付人民币壹万元整。")

    assert run.findings.count() == 1
