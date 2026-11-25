"""案件级策略的读写：库里没有记录时回落到代码默认。

**回落方向只有一个**：库里没有 → 用 `services/verify/policy.should_verify` 的默认值。
反过来（库里没有就当不做）会让新案子默认全关，功能上线第一天就静默失效。
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.doc_verify.models.policy import VerificationPolicy
from apps.doc_verify.services.verify.policy import HIGH_RISK_DOC_TYPES, should_verify


def effective_items(case_id: int) -> list[dict[str, Any]]:
    """该案每类高风险文书的**实际**策略（库里的值，没有就取默认）。"""
    stored = {row.doc_type: row.enabled for row in VerificationPolicy.objects.filter(case_id=case_id)}
    return [
        {
            "doc_type": doc_type,
            "enabled": stored.get(doc_type, True),
            "default": should_verify(doc_type),
        }
        for doc_type in HIGH_RISK_DOC_TYPES
    ]


def is_required(*, case_id: int | None, doc_type: str) -> bool:
    """这份文书回传后要不要自动核对。

    命中规则与默认策略同一套：库里存的是主干（`起诉状`），文书名里含它即命中；
    一格都没命中就回落到代码默认。
    """
    name = (doc_type or "").strip()
    if not name:
        return False
    if case_id is None:
        return should_verify(name)
    for row in VerificationPolicy.objects.filter(case_id=case_id):
        if row.doc_type and row.doc_type in name:
            return bool(row.enabled)
    return should_verify(name)


@transaction.atomic
def set_policy(*, case_id: int, doc_types: list[str], enabled: bool) -> list[dict[str, Any]]:
    """批量改策略；空 doc_types 视为「改全部高风险类」。返回改后的全量。"""
    targets = [name.strip() for name in (doc_types or []) if name and name.strip()] or list(HIGH_RISK_DOC_TYPES)
    for doc_type in targets:
        VerificationPolicy.objects.update_or_create(
            case_id=case_id,
            doc_type=doc_type,
            defaults={"enabled": enabled},
        )
    return effective_items(case_id)
