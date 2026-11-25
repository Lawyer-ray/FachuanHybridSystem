"""出站基线 API：冻结「我们发出去的那一份」。

挂在 `/api/v1/doc-verify`，与核对运行共用同一个前缀（两条 router 各自 add_router，
路径不重叠）。这一层只做参数提取与装配：字节解码、落库、策略判定都在 service。
"""

from __future__ import annotations

from typing import Any

from ninja import Router

from apps.doc_verify.api._operator import require_operator
from apps.doc_verify.schemas import ArtifactIn, ArtifactOut
from apps.doc_verify.services import artifact_store
from apps.doc_verify.services.verify.run import decode_inbound_payload

router = Router(tags=["回传件核对"])


@router.post("/artifacts", response=ArtifactOut)
def create_artifact(request: Any, payload: ArtifactIn) -> dict[str, Any]:
    """冻结一份出站基线（幂等：同案+同文书+同版本+同字节只留一行）。

    出站那一刻是**唯一**能确定「客户收到的是什么」的时点。事后拿最新定稿当基线
    去比客户按旧版改的回传件，会全盘误报。
    """
    operator = require_operator(request, purpose="冻结基线")
    data = decode_inbound_payload(payload.file_base64)
    artifact = artifact_store.capture_outbound(
        data=data,
        file_name=payload.file_name,
        doc_type=payload.doc_type,
        version=payload.version,
        case_id=payload.case_id,
        capture_source=payload.capture_source,
        verify_required=payload.verify_required,
        captured_by=operator,
        note=payload.note,
    )
    return artifact_store.artifact_detail(artifact)


@router.get("/artifacts", response=list[ArtifactOut])
def list_artifacts(request: Any, case_id: int) -> list[dict[str, Any]]:
    require_operator(request, purpose="查看基线")
    return artifact_store.list_artifacts(case_id=case_id)
