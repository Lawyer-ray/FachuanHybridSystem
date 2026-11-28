"""案件列表（GET /api/v1/cases/cases）单页的查询预算门禁。

真库实测（115 行、单 worker）：一次请求 **258 条 SQL**，响应 755KB；其中
`cases_clientidentitydoc` **239 条**，重复次数第一名。根因不是序列化写错了，而是
`get_case_queryset()` 只预取到 `parties__client` 这一层：`CaseOut.parties` 的
`client_detail` 是 `ClientOut`，而 `ClientOut.resolve_identity_docs`
（apps/client/schemas/client_schemas.py:57-68）要读 `client.identity_docs`
——没预取就是「每个当事人的证件各发一条」。

反向验证（本条门禁是不是真门禁）：把 `get_case_queryset()` 里的
`parties__client__identity_docs` 删掉、别的都不动，同一个用例立刻变红：

- 绿（有预取，种子 10 个案件 × 1 当事人 × 1 证件）：**11 条**；
- 红（无预取，同一份种子）：**20 条**（= 11 - 1 条预取 + 10 条逐行补查）。
  多出来的 10 条正好等于案件数——per-row 补查藏不住。

为什么种子必须是「案件 + 当事人 + 证件」三件套：只建案件（不建 CaseParty /
ClientIdentityDoc）时上面那 239 条 N+1 根本不会发生，预算门禁形同虚设
（合同侧门禁实测过同样的坑）。

日志/提醒（`warm_reminder_cache_for_cases`）不在此门禁范围内：它们由端点在
序列化前一次性预热，与 queryset 的 prefetch 组无关，本用例种子也不建 CaseLog。
"""

from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.cases.models import CaseParty
from apps.cases.schemas.case_schemas import CaseOut
from apps.cases.services.case.case_queryset import get_case_queryset
from apps.client.models import ClientIdentityDoc
from apps.testing.factories import CaseFactory, ClientFactory, ClientIdentityDocFactory

CASE_COUNT = 10
# 同名残留：整个 cases 目录跑完时库里会有其他用例的案件，名字带本次运行标签 +
# startswith 过滤，让这条用例的查询数与断言都与残留数据无关。
_RUN_TAG = uuid.uuid4().hex[:8]
_NAME_PREFIX = f"预算案件-{_RUN_TAG}-"

# 预算来历（实测，种子 10 行）：**11 条**，与行数无关——
#   1  案件页本身（select_related contract 走 join，不额外发查询）
#   1  parties + client（select_related）/ 1 identity_docs
#   2  assignments__lawyer__law_firm（assignments / lawyer+law_firm）
#   1  logs / 1 logs__attachments
#   1  case_numbers / 1 supervising_authorities / 1 chats / 1 contacts__authority
#   ~2  contract__supplementary_agreements__parties__client__identity_docs 链
# 余量只留 2：本种子 10 行，任何 per-row 补查至少 +10，余量藏不住 N+1。
_QUERY_BUDGET = 13


def _seed() -> list[str]:
    """N 个案件，每个带一个「有证件」的当事人——即 239 条 N+1 的最小复现场景。"""
    names: list[str] = []
    for i in range(CASE_COUNT):
        name = f"{_NAME_PREFIX}{i}"
        names.append(name)
        case = CaseFactory(name=name)
        client = ClientFactory(name=f"{_NAME_PREFIX}当事人-{i}")
        CaseParty.objects.create(case=case, client=client)
        ClientIdentityDocFactory(client=client, doc_type=ClientIdentityDoc.ID_CARD)
    return names


def _render_page() -> list[dict]:
    """复刻 list_cases 端点 sync 段：queryset 取数 + 逐行 CaseOut.from_orm。"""
    cases = list(get_case_queryset().filter(name__startswith=_NAME_PREFIX).order_by("id"))
    return [CaseOut.from_orm(case).model_dump(by_alias=True, mode="json") for case in cases]


@pytest.mark.django_db
class TestCasesListQueryBudget:
    def test_list_page_query_count_is_bounded(self) -> None:
        names = _seed()
        with CaptureQueriesContext(connection) as ctx:
            items = _render_page()

        assert {item["name"] for item in items} == set(names)  # 这一页确实只有本案种子
        # 连接级配置语句（statement_timeout 中间件的 set_config 等）不属业务查询预算
        business = [
            q for q in ctx.captured_queries if not q["sql"].lstrip().upper().startswith(("SELECT SET_CONFIG", "SET "))
        ]
        assert len(business) <= _QUERY_BUDGET, (
            f"案件列表用掉 {len(business)} 条 SQL（预算 {_QUERY_BUDGET}）：N+1 复发，"
            f"检查 get_case_queryset() 的 prefetch 组是否被拆散（尤其 parties__client__identity_docs）"
        )
