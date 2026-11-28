"""Business logic services."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.cases.models import Case


def get_case_queryset(*, slim: bool = False) -> QuerySet[Case, Case]:
    """案件查询集（带序列化所需的预取）。

    slim=True：只取 Case 自身的标量列（CaseSlimOut 一个嵌套集合都不含），因此
    **不做任何 select_related / prefetch_related**——预取是给 CaseOut 的嵌套集合用的，
    瘦身列表带上它等于白花 10+ 条 SQL 与几倍响应体积（真库实测 258 条 → 见
    tests/ci/unit/cases/test_cases_slim_list.py）。

    注意：预取裁剪必须和 schema 裁剪同时改，只改 schema 时 `slim=true` 一条 SQL
    都省不掉——那条用例就是为了钉住这一点。
    """
    if slim:
        return Case.objects.all()
    return Case.objects.select_related(
        "contract",
    ).prefetch_related(
        "parties__client",
        # 当事人证件：CaseOut → CasePartyOut.client_detail 是 ClientOut，而
        # ClientOut.resolve_identity_docs（client_schemas.py:57-68）读 client.identity_docs。
        # 只预取到 client 这一层时，每个当事人的每份证件都各发一条
        # cases_clientidentitydoc 查询——真库 115 行页面实测 239 条，是该接口重复
        # SQL 的第一名。再下一层即可。
        "parties__client__identity_docs",
        "assignments__lawyer",
        "assignments__lawyer__law_firm",
        "logs__actor",
        "logs__attachments",
        "case_numbers",
        "supervising_authorities",
        "chats",
        "contacts__authority",
        "contract__supplementary_agreements__parties__client",
        # 补充协议的当事人证件同理（同一批 CaseOut 里补充协议方的 ClientOut 也会逐条补查）
        "contract__supplementary_agreements__parties__client__identity_docs",
    )
