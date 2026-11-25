"""读模型：单次核对详情与「待裁决清单」。

## 为什么「待裁决」的口径写在这一层

裁决过的件必须立刻从清单里消失，否则律师会把已经放行的东西再看一遍，
清单越长越没人看。而「哪些状态算需要裁决」「哪些动作算关掉了这一条」如果
前后端各有一份，前端漏一档就等于漏掉一次实质改动。所以口径只在这里写一次。
"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import NotFoundError
from apps.doc_verify.models import OutboundArtifact, VerificationRun, VerifyState

#: 需要律师裁决的状态。`no_difference_detected` 刻意不在其中：免费层没发现差异
#: 不等于需要人看，全塞进清单只会稀释真正要看的红/灰项。
NEEDS_DECISION_STATES: tuple[str, ...] = (VerifyState.CHANGED, VerifyState.UNVERIFIABLE)

#: 视为「已处置」的动作。`reissue` 不在其中：要求重出之后，客户会不会回传新版
#: 还不知道，这一条还在进行中，只是记了一笔处置意见。
DECIDED_ACTIONS: tuple[str, ...] = ("accept", "reject")


def get_artifact(artifact_id: int) -> OutboundArtifact:
    """按 id 取出站基线；不存在时给 404，而不是返回一个空对象去跑比对。"""
    artifact = OutboundArtifact.objects.select_related("case").filter(id=artifact_id).first()
    if artifact is None:
        raise NotFoundError(message=f"出站基线不存在：{artifact_id}", errors={"artifact_id": artifact_id})
    return artifact


def get_run(run_id: int) -> VerificationRun:
    """按 id 取核对运行；不存在时给 404。"""
    run = VerificationRun.objects.select_related("artifact").filter(id=run_id).first()
    if run is None:
        raise NotFoundError(message=f"核对运行不存在：{run_id}", errors={"run_id": run_id})
    return run


def run_detail(run: VerificationRun) -> dict[str, Any]:
    """一次核对的对外形状（详情与清单共用同一份，避免两处字段漂移）。"""
    artifact = run.artifact
    return {
        "id": run.id,
        "artifact_id": run.artifact_id,
        "case_id": artifact.case_id,
        "doc_type": artifact.doc_type,
        "state": run.state,
        "state_label": run.get_state_display(),
        "tier": run.tier,
        "inbound_file_name": run.inbound_file_name,
        "inbound_sha256": run.inbound_sha256,
        "page_count": run.page_count,
        "findings": list(run.findings or []),
        "coverage": dict(run.coverage or {}),
        "source_message_id": run.source_message_id,
        "created_at": run.created_at,
    }


def list_unverified(case_id: int) -> list[dict[str, Any]]:
    """该案待裁决清单：要求核对、状态需裁决、且没有 accept/reject 裁决。"""
    runs = (
        VerificationRun.objects.filter(
            artifact__case_id=case_id,
            artifact__verify_required=True,
            state__in=NEEDS_DECISION_STATES,
        )
        .exclude(decisions__action__in=DECIDED_ACTIONS)
        .select_related("artifact")
        .order_by("-created_at", "-id")
    )
    return [run_detail(run) for run in runs]
