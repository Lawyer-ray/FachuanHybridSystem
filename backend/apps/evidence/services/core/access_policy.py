"""证据清单访问控制策略。

通过 EvidenceList -> Case -> CaseAssignment 链路验证用户访问权限。
"""

from __future__ import annotations

from typing import Any

from apps.cases.models import Case
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.core.security.access_context import AccessContext
from apps.evidence.models import EvidenceList


def _get_case_id_for_evidence_list(list_id: int) -> int:
    """从证据清单 ID 获取关联的案件 ID。"""
    try:
        ev_list = EvidenceList.objects.values("case_id").get(pk=list_id)
    except EvidenceList.DoesNotExist:
        from apps.core.exceptions import NotFoundError

        raise NotFoundError(f"证据清单 {list_id} 不存在")
    return ev_list["case_id"]


def ensure_evidence_list_access(list_id: int, ctx: AccessContext) -> None:
    """验证用户对证据清单的访问权限（通过关联案件的访问策略）。

    Args:
        list_id: 证据清单 ID
        ctx: 请求访问上下文

    Raises:
        ForbiddenError: 用户无权访问该证据清单关联的案件
    """
    case_id = _get_case_id_for_evidence_list(list_id)
    CaseAccessPolicy().ensure_access_ctx(case_id=case_id, ctx=ctx)


def ensure_case_access(case_id: int, ctx: AccessContext) -> None:
    """验证用户对案件的访问权限。

    Args:
        case_id: 案件 ID
        ctx: 请求访问上下文

    Raises:
        ForbiddenError: 用户无权访问该案件
    """
    CaseAccessPolicy().ensure_access_ctx(case_id=case_id, ctx=ctx)
