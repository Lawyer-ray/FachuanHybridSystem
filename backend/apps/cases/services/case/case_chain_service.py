"""案件链查询（前序/后代案件的串联）。

从 Case 模型下沉的查询逻辑：模型层只留字段与简单展示，
跨行聚合查询归 service。
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from apps.cases.models import Case


def get_case_chain(
    case: Case,
    *,
    user: Any | None = None,
    org_access: dict[str, Any] | None = None,
    perm_open_access: bool = False,
) -> list[Case]:
    """获取完整案件链（按 start_date 升序）。

    链通常 2~4 层，优化为：
    1. 逐层回溯到根（N 次轻量查询，N=链深；visited 防环）
    2. 单次查询取所有后代（链短时 1 次即可）
    3. 一次性取出完整案件，按收案日期排序

    安全审计（2026-10-19）：新增可选 user/org_access/perm_access 参数，
    传入 user 时按 CaseAccessPolicy 行级口径过滤——无权访问的案件从链上隐藏；
    默认不传则保持既有行为（不过滤），兼容既有调用方。
    """
    from .case_access_policy import CaseAccessPolicy

    # 1. 回溯到链首
    root_id: int = case.pk
    visited: set[int] = {root_id}
    while True:
        parent_id = Case.objects.filter(pk=root_id).values_list("previous_case_id", flat=True).first()
        if not parent_id or parent_id in visited:
            break
        visited.add(parent_id)
        root_id = parent_id

    # 2. 前向 BFS：单次查询取所有后代
    chain: list[int] = [root_id]
    frontier = [root_id]
    while frontier:
        children = list(Case.objects.filter(previous_case_id__in=frontier).values_list("pk", flat=True))
        frontier = [c for c in children if c not in chain]
        chain.extend(frontier)

    # 3. 一次性取出所有案件，按收案日期排序；仅在显式传入 user 时做行级过滤
    chain_qs: QuerySet[Case, Case] = Case.objects.filter(pk__in=chain).order_by("start_date", "pk")
    if user is not None:
        chain_qs = CaseAccessPolicy().filter_queryset(chain_qs, user, org_access, perm_open_access)
    return list(chain_qs)
