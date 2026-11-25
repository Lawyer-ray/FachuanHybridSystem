"""出站基线的读写门面：API 层只跟这里打交道（四层规范：API 不碰 Model.objects）。"""

from __future__ import annotations

from typing import Any

from apps.cases.models import Case
from apps.core.exceptions import NotFoundError
from apps.doc_verify.models import OutboundArtifact
from apps.doc_verify.services.anchor.capture import capture_baseline
from apps.doc_verify.services.anchor.persist import create_artifact
from apps.doc_verify.services.policy_store import is_required


def load_case(case_id: int) -> Case:
    case = Case.objects.filter(id=case_id).first()
    if case is None:
        raise NotFoundError(message="案件不存在", code="CASE_NOT_FOUND", errors={"case_id": case_id})
    return case


def capture_outbound(
    *,
    data: bytes,
    file_name: str,
    doc_type: str,
    version: str = "",
    case_id: int | None = None,
    capture_source: str = "manual",
    verify_required: bool | None = None,
    captured_by: Any = None,
    note: str = "",
) -> OutboundArtifact:
    """冻结一份出站基线。`verify_required` 不传时按案件策略决定（默认值见 policy）。"""
    case = load_case(case_id) if case_id is not None else None
    required = is_required(case_id=case_id, doc_type=doc_type) if verify_required is None else verify_required
    baseline = capture_baseline(
        data=data,
        file_name=file_name,
        doc_type=doc_type,
        version=version,
    )
    return create_artifact(
        case=case,
        baseline=baseline,
        capture_source=capture_source,
        verify_required=required,
        captured_by=captured_by,
        note=note,
        policy_snapshot={"verify_required": required, "source": capture_source},
    )


def list_artifacts(*, case_id: int) -> list[dict[str, Any]]:
    """该案的出站基线清单（新→旧）。前端据此知道「哪些文书已有基线可比」。"""
    rows = OutboundArtifact.objects.filter(case_id=case_id).order_by("-captured_at", "-id")
    return [
        {
            "id": row.id,
            "case_id": row.case_id,
            "doc_type": row.doc_type,
            "version": row.version,
            "file_name": row.file_name,
            "file_sha256": row.file_sha256,
            "page_count": row.page_count,
            "capture_source": row.capture_source,
            "verify_required": row.verify_required,
            "captured_at": row.captured_at,
        }
        for row in rows
    ]


def artifact_detail(row: OutboundArtifact) -> dict[str, Any]:
    """一份基线的对外形状（创建与列表共用，避免两处字段漂移）。"""
    return {
        "id": row.id,
        "case_id": row.case_id,
        "doc_type": row.doc_type,
        "version": row.version,
        "file_name": row.file_name,
        "file_sha256": row.file_sha256,
        "page_count": row.page_count,
        "capture_source": row.capture_source,
        "verify_required": row.verify_required,
        "captured_at": row.captured_at,
    }
