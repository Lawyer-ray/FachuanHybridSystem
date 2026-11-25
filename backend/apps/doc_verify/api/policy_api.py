"""案件级核对策略 API：前端那个「回传后核对内容」勾选框的唯一落点。

**为什么要有这个端点**：策略只写在代码里，勾选框就只是画着好看；批量小额案件
想关掉省时间、疑难案子想把证据清单也打开，都得能落库。
"""

from __future__ import annotations

from typing import Any

from ninja import Router

from apps.doc_verify.api._operator import require_operator
from apps.doc_verify.schemas import PolicyIn, PolicyOut
from apps.doc_verify.services import artifact_store, policy_store

router = Router(tags=["回传件核对"])


@router.get("/policy", response=PolicyOut)
def get_policy(request: Any, case_id: int) -> dict[str, Any]:
    """该案每类高风险文书的实际策略（库里没有就取代码默认）。"""
    operator = require_operator(request, purpose="查看核对策略")
    artifact_store.load_case(case_id, user=operator)
    return {"case_id": case_id, "items": policy_store.effective_items(case_id)}


@router.put("/policy", response=PolicyOut)
def put_policy(request: Any, payload: PolicyIn) -> dict[str, Any]:
    """批量改策略（`doc_types` 留空 = 改全部高风险类），返回改后的全量。"""
    operator = require_operator(request, purpose="修改核对策略")
    artifact_store.load_case(payload.case_id, user=operator)
    items = policy_store.set_policy(case_id=payload.case_id, doc_types=payload.doc_types, enabled=payload.enabled)
    return {"case_id": payload.case_id, "items": items}
