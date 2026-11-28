"""合同列表（slim=true）单请求的查询预算与日志噪声门禁。

真库实测（178 份合同、page_size=50、uvicorn 单 worker，2026-11-27）：
- 一次请求 **150 条** 带完整 traceback 的 ERROR（3 个 resolver × 50 行：
  `resolve_client_payment_records` / `resolve_finalized_materials` / `resolve_can_archive`）；
- 一次请求 **113 条 SQL**，其中 **96 条**是同一个 `cases_clientidentitydoc` 补查
  （占 85%，`get_contract_queryset` 只预取到 `contract_parties__client` 这一层）；
- 交错 A/B（旧/新服务器轮流吃同一份负载，N=40/边，load average 100+ 下仍稳定）：
  p50 **355.9 → 103.7ms**、p95 **565.3 → 153.2ms**（逐对中位数差 +253.3ms）；
  同批请求的日志体积 **11.3MB → 6.8KB**。

根因：slim 序列化代理对 finalized_materials / client_payment_records 抛 AttributeError，
而 resolver 的 blanket `except Exception` 把它当失败记 ERROR——一条正常的设计路径被
记成了 150 次失败；另一头是当事人证件没预取到 `client__identity_docs`。
修法落地后（0 日志 / 12 条 SQL）本文件把两件事钉死：
1. 查询数只由固定 prefetch 组决定、与行数无关：任何 per-row 补查 = N+1 复发；
2. 整段调用期间不得出现任何 resolver 日志：降级分支被正常路径覆盖，不再刷栈。

为什么种子必须带「当事人 + 证件」：只建合同（不建 contract_party / identity_doc）时，
上面那 96 条 N+1 根本不会发生，预算门禁就形同需设——实测过：拆掉
`contract_parties__client__identity_docs` 预取后，无当事人的种子仍然全绿。
"""

from __future__ import annotations

import datetime
import logging
import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.client.models import ClientIdentityDoc
from apps.contracts.api.contract_api import _serialize_contract
from apps.contracts.models import ContractParty, ContractPayment
from apps.contracts.services.contract.query.service import ContractQueryService
from apps.testing.factories import ClientFactory, ClientIdentityDocFactory, ContractFactory

PAGE_SIZE = 50
CONTRACT_COUNT = 12
_PAYMENT_DATE = datetime.date(2026, 1, 1)
# 整个 contracts 目录跑完时库里会残留其他用例的合同（实测有 id 远小于本案种子的孤儿行），
# 分页第 1 页会把它们一起取回来、撑成 31 行。名字带本次运行标签 + search 过滤，
# 让这一页只含本案种子，查询数与断言都与残留数据无关。
_RUN_TAG = uuid.uuid4().hex[:8]
_NAME_PREFIX = f"预算合同-{_RUN_TAG}-"

# 预算来历（实测）：本种子 12 行合同、每行 1 当事人 + 1 证件，计到 12 条——
#   1  count(*)                —— list_contracts_page 的 total
#   1  合同页本身
#   3  facets 的三次全表聚合（端点默认 include_facets=true，按默认口径测）
#  ~7  固定 prefetch 组（contract_parties__client__identity_docs / payments /
#      reminders / assignments__lawyer / supplementary_agreements__parties__client__identity_docs …）
#
# 从 20 收到 14 的两笔节省（含拆分口径变更）：
#   1）payments__invoices → payments：ContractPaymentOut 没有 invoices 字段，多下一层
#      纯浪费（-1）；
#   2）"cases" 预取从通用组移进 `if not slim:`，slim 主路径不再拉整页案件（-1），
#      前提是 _case_count 子查询包了 Coalesce(..., 0)——否则注解为 NULL 的合同会落到
#      ContractOut.resolve_case_count 的 obj.cases.count() 兜底，slim 侧反而逐行补
#      COUNT（真库 50 行页面 28 行无案件，实测拆掉预取后 19 → 46 条）。
#      下方 test_case_count_annotation_has_no_nulls 钉住这个前提。
# 余量只留 2：本种子 12 行，任何 per-row 补查至少 +12，余量藏不住 N+1。
# 真实做过反向验证：把两条 identity_docs 预取拆掉，本用例立刻变红（12 → 23 条）。
_QUERY_BUDGET = 14


def _seed() -> list[str]:
    """N 份合同，每份一条收款 + 一个带证件的当事人——覆盖新手位里最容易长成 N+1 的三条关系。"""
    names: list[str] = []
    for i in range(CONTRACT_COUNT):
        name = f"{_NAME_PREFIX}{i}"
        names.append(name)
        contract = ContractFactory(name=name)
        client = ClientFactory(name=f"{_NAME_PREFIX}当事人-{i}")
        ContractParty.objects.create(contract=contract, client=client)
        ClientIdentityDocFactory(client=client, doc_type=ClientIdentityDoc.ID_CARD)
        ContractPayment.objects.create(
            contract=contract,
            amount=100 + i,
            received_at=_PAYMENT_DATE + datetime.timedelta(days=i),
        )
    return names


def _render_slim_page() -> list[dict]:
    """复刻 list_contracts 端点 sync 段做的事：分页取数 + 逐行 slim 序列化。"""
    data = ContractQueryService().list_contracts_page(
        page=1, page_size=PAGE_SIZE, slim=True, search=_NAME_PREFIX, perm_open_access=True
    )
    return [_serialize_contract(contract, slim=True) for contract in data["items"]]


@pytest.mark.django_db
class TestSlimListQueryBudget:
    def test_slim_page_query_count_is_bounded(self) -> None:
        names = _seed()
        with CaptureQueriesContext(connection) as ctx:
            items = _render_slim_page()

        assert {item["name"] for item in items} == set(names)  # 这一页确实只有本案种子
        # 连接级配置语句（statement_timeout 中间件的 set_config 等）不属业务查询预算
        business = [
            q for q in ctx.captured_queries if not q["sql"].lstrip().upper().startswith(("SELECT SET_CONFIG", "SET "))
        ]
        assert len(business) <= _QUERY_BUDGET, (
            f"slim 列表用掉 {len(business)} 条 SQL（预算 {_QUERY_BUDGET}）：N+1 复发，"
            f"检查 get_contract_queryset(slim=True) 的 prefetch 组是否被拆散，"
            f"或 _case_count 的 Coalesce 被拆掉（NULL 注解会让每行回落到 cases.count()）"
        )

    def test_case_count_annotation_has_no_nulls(self) -> None:
        """slim 路径去掉 "cases" 预取的前提：注解本身必须是 0 而不是 NULL。

        ContractOut.resolve_case_count 把 None 当「没有注解」、回落到
        `obj.cases.count()`——预取一旦拆掉，每行没有案件就是一个 COUNT(*)。
        所以这里不靠序列化结果（0 和「NULL + count()==0」输出相同），直接看
        注解列本身。本文件的种子完全不建案件，每一行都走「聚合子查询无匹配行」分支。
        """
        _seed()
        counts = list(
            ContractQueryService()
            .get_contract_queryset(slim=True)
            .filter(name__startswith=_NAME_PREFIX)
            .order_by("id")
            .values_list("_case_count", flat=True)
        )

        assert counts, "种子合同没进 queryset，断言会真空通过"
        assert None not in counts, f"_case_count 注解出现 NULL（Coalesce 被拆掉？）: {counts}"

    def test_slim_page_writes_no_error_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """序列化期不许再有任何 resolver 日志：被剔除的重关系走空 relation，不进异常分支。

        契约就是「一条日志都没有」：预期内路径现在是正常返回 []，不该降级；
        旧设计在这里每行每字段记一条带 traceback 的 ERROR，实测占 p50 的 133ms。
        """
        names = _seed()
        contract_logger = logging.getLogger("apps.contracts")
        # 项目 LOGGING 把 `apps` logger 配成 propagate=False（apps/core/infrastructure/
        # logging.py:409），而 caplog 的 handler 只挂在 root 上；换环境下 caplog 可能
        # 一条都收不到、断言真空通过。把 caplog 的 handler 直接挂到 `apps.contracts`。
        contract_logger.addHandler(caplog.handler)
        caplog.clear()
        try:
            with caplog.at_level(logging.DEBUG, logger="apps.contracts"):
                items = _render_slim_page()
        finally:
            contract_logger.removeHandler(caplog.handler)

        assert {item["name"] for item in items} == set(names)
        records = [record for record in caplog.records if record.name.startswith("apps.contracts")]
        loud = [record for record in records if record.levelno >= logging.WARNING]
        assert not loud, f"slim 列表打出 WARNING/ERROR 日志（traceback 刷屏复发）: {[r.getMessage() for r in loud]}"
        assert not [record for record in records if record.exc_info], (
            f"slim 列表写了 traceback（133ms 开销的来源）: {[r.getMessage() for r in records]}"
        )
        assert not records, f"slim 列表期间 resolver 不应进降级分支: {[(r.levelname, r.getMessage()) for r in records]}"
