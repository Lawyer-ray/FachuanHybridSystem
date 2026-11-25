"""把内存基线落成 :class:`OutboundArtifact`：**只增不改** + 幂等。

## 基线被改写等于销毁证据

同一次出站（同一案件 / 文书名 / 版本 / 字节 SHA-256）只会有一条基线：
重复调用 ``create_artifact`` 返回既有那一行，**一个字段都不覆盖**。
要去纠正一条基线，正确做法是给个新版本标签再捕获一条，而不是原地改。

## 幂等键与并发

幂等键 = ``(case_id, doc_type, version, file_sha256)``。模型是冻结的，没有这条
唯一约束（建表时没加），所以「先查后建」在事务 + ``select_for_update`` 下只能
收窄并发窗口、不能消灭它：并发两次捕获同一份字节，理论上可能落两行。
后果是多一条同内容的基线（列表多一行），不会产生两份不同的结论——
真出现时按 ``id`` 去重即可，不需要靠改基线来「修复」。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from django.db import transaction

from apps.doc_verify.domain.contracts import Baseline
from apps.doc_verify.models.artifact import OutboundArtifact

logger = logging.getLogger(__name__)


def create_artifact(
    *,
    case: Any,
    baseline: Baseline,
    capture_source: str = "manual",
    verify_required: bool = False,
    captured_by: Any = None,
    note: str = "",
    policy_snapshot: Mapping[str, Any] | None = None,
) -> OutboundArtifact:
    """落一条出站基线；同幂等键已存在则原样返回既有行。

    ``case`` 是 ``cases.Case`` 实例（或 ``None``：无案件的人工补锚），
    ``captured_by`` 是 ``organization.Lawyer`` 实例（或 ``None``）。
    """
    with transaction.atomic():
        existing = (
            OutboundArtifact.objects.select_for_update()
            .filter(
                case=case,
                doc_type=baseline.doc_type,
                version=baseline.version,
                file_sha256=baseline.sha256,
            )
            .order_by("id")
            .first()
        )
        if existing is not None:
            logger.info(
                "基线已存在，直接复用不覆盖: id=%s doc_type=%s version=%s sha=%s",
                existing.pk,
                existing.doc_type,
                existing.version or "-",
                existing.file_sha256[:12],
            )
            return existing

        artifact = OutboundArtifact.objects.create(
            case=case,
            doc_type=baseline.doc_type,
            version=baseline.version,
            # Baseline 契约不带文件名（只有 Inbound 带），出站文件名需要时写在 note 里
            file_name="",
            file_sha256=baseline.sha256,
            page_count=baseline.page_count,
            page_signatures=[list(signature) for signature in baseline.page_signatures],
            text_layer=baseline.text,
            masks=[dict(mask) for mask in baseline.masks],
            capture_source=capture_source,
            verify_required=verify_required,
            policy_snapshot=dict(policy_snapshot or {}),
            captured_by=captured_by,
            note=note,
        )

    logger.info(
        "基线已落库: id=%s doc_type=%s version=%s sha=%s 来源=%s 页数=%d",
        artifact.pk,
        artifact.doc_type,
        artifact.version or "-",
        artifact.file_sha256[:12],
        artifact.capture_source,
        artifact.page_count,
    )
    return artifact
