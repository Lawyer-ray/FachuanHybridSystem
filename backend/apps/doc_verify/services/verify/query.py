"""读模型：单次核对详情、「待裁决清单」与本案件核对历史。

## 为什么「待裁决」的口径写在这一层

裁决过的件必须立刻从清单里消失，否则律师会把已经放行的东西再看一遍，
清单越长越没人看。而「哪些状态算需要裁决」「哪些动作算关掉了这一条」如果
前后端各有一份，前端漏一档就等于漏掉一次实质改动。所以口径只在这里写一次。
"""

from __future__ import annotations

from typing import Any

from apps.cases.services.case.case_visibility import accessible_case_ids
from apps.core.exceptions import NotFoundError, ValidationException
from apps.doc_verify.models import OutboundArtifact, VerificationRun, VerifyState

#: 需要律师裁决的状态。`no_difference_detected` 刻意不在其中：免费层没发现差异
#: 不等于需要人看，全塞进清单只会稀释真正要看的红/灰项。
NEEDS_DECISION_STATES: tuple[str, ...] = (VerifyState.CHANGED, VerifyState.UNVERIFIABLE)

#: 视为「已处置」的动作。`reissue` 不在其中：要求重出之后，客户会不会回传新版
#: 还不知道，这一条还在进行中，只是记了一笔处置意见。
DECIDED_ACTIONS: tuple[str, ...] = ("accept", "reject")

#: 核对历史单页上限。一页 200 条已经够翻很久，再多只会把首屏拖慢；
#: 要全量就分页拿，不要靠调大 limit。
RUN_PAGE_MAX_LIMIT = 200


def get_artifact(artifact_id: int) -> OutboundArtifact:
    """按 id 取出站基线；不存在时给 404，而不是返回一个空对象去跑比对。"""
    artifact = OutboundArtifact.objects.select_related("case").filter(id=artifact_id).first()
    if artifact is None:
        raise NotFoundError(message=f"出站基线不存在：{artifact_id}", errors={"artifact_id": artifact_id})
    return artifact


def get_run(run_id: int) -> VerificationRun:
    """按 id 取核对运行；不存在时给 404。"""
    run = VerificationRun.objects.select_related("artifact__case").filter(id=run_id).first()
    if run is None:
        raise NotFoundError(message=f"核对运行不存在：{run_id}", errors={"run_id": run_id})
    return run


def run_detail(run: VerificationRun) -> dict[str, Any]:
    """一次核对的对外形状（详情、清单、历史共用同一份，避免两处字段漂移）。"""
    artifact = run.artifact
    case = artifact.case
    return {
        "id": run.id,
        "artifact_id": run.artifact_id,
        "case_id": artifact.case_id,
        # 跨案件清单里只有「起诉状」没有案名，律师没法判断是哪一件
        "case_name": getattr(case, "name", "") or "",
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
        .select_related("artifact__case")
        .order_by("-created_at", "-id")
    )
    return [run_detail(run) for run in runs]


def list_case_runs(
    *,
    case_id: int,
    state: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """该案的**全量**核对历史（含已裁决的），分页返回 `{total, items}`。

    与 `list_unverified` 的区别只有一个：这里不筛「待裁决」、不排除已裁决——案件详情页
    要看的是「这案核过几次、结论怎么变」，只给待裁决清单等于把历史删掉一半。
    `total` 是**过滤后**的总数，不是本页条数：前端靠它知道还有几页。
    """
    queryset = VerificationRun.objects.filter(artifact__case_id=case_id).select_related("artifact__case")
    normalized_state = (state or "").strip()
    if normalized_state:
        if normalized_state not in set(VerifyState.values):
            raise ValidationException(
                message=f"核对状态不合法：{normalized_state!r}",
                errors={"state": list(VerifyState.values)},
            )
        queryset = queryset.filter(state=normalized_state)
    total = queryset.count()
    capped = max(1, min(int(limit), RUN_PAGE_MAX_LIMIT))
    start = max(0, int(offset))
    rows = queryset.order_by("-created_at", "-id")[start : start + capped]
    return {"total": total, "items": [run_detail(row) for row in rows]}


def list_pending(*, user: Any, limit: int = 100) -> list[dict[str, Any]]:
    """**跨案件**待裁决清单（材料准备页的全局入口）。

    筛选口径与 `list_unverified` 一字不差，只是不限案件；可见性用 `accessible_case_ids`
    收窄（None = 管理员，不收窄）。`limit` 封顶而不是分页：这是「提醒还有多少事」的
    入口，不是台账；真要全量请按案查。
    """
    queryset = (
        VerificationRun.objects.filter(
            artifact__verify_required=True,
            state__in=NEEDS_DECISION_STATES,
        )
        .exclude(decisions__action__in=DECIDED_ACTIONS)
        .select_related("artifact__case")
        .order_by("-created_at", "-id")
    )
    visible = accessible_case_ids(user)
    if visible is not None:
        if not visible:
            return []
        queryset = queryset.filter(artifact__case_id__in=visible)
    capped = max(1, min(int(limit or 100), 500))
    return [run_detail(run) for run in queryset[:capped]]
