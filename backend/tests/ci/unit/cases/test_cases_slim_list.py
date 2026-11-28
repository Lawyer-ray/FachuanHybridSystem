"""``GET /api/v1/cases/cases`` 的两个增量参数（slim / with_total）的契约门禁。

背景（真库实测，115 行）：一次默认请求 258 条 SQL / 755KB，列表页却只读 7 个字段。
本轮加的两个参数都是**可选增量**，不传时响应逐字节不变（红线）：

- ``slim=true``：列表项换 CaseSlimOut（标量列与 CaseOut 同口径，剔除 7 个嵌套集合），
  **预取同步裁剪**——只改 schema 不裁预取的话 SQL 一条也不省，所以下面既钉形状
  也钉查询数。
- ``with_total=true``：真实总数走响应头 ``X-Total-Count``，响应体仍是裸数组
  （4 个既有消费方按裸数组消费，换信封会同时红）。

反向验证（本条查询数门禁是不是真门禁）：把 ``get_case_queryset`` 里的
``if slim: return Case.objects.all()`` 删掉（预取裁剪失效、schema 仍裁），
``test_slim_true_cuts_sql_not_just_fields`` 立刻变红——两个数字见该用例的 assert 消息。
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.cases.models import CaseParty
from apps.cases.services.case.case_queryset import get_case_queryset
from apps.client.models import ClientIdentityDoc
from apps.testing.factories import CaseFactory, CaseLogFactory, ClientFactory, ClientIdentityDocFactory, ContractFactory

LIST_URL = "/api/v1/cases/cases"
CASE_COUNT = 5

# CaseOut 的完整键集（21 个）。列表页消费方（bank-litigation/types.ts CaseRow）
# 只 Pick 7 个，但**默认响应不能少任何一个**——这是「不改默认行为」的锚点。
CASE_OUT_KEYS = {
    "id",
    "name",
    "status",
    "is_filed",
    "filing_number",
    "case_type",
    "start_date",
    "effective_date",
    "specified_date",
    "target_amount",
    "preservation_amount",
    "cause_of_action",
    "current_stage",
    "contract_id",
    "parties",
    "assignments",
    "logs",
    "case_numbers",
    "supervising_authorities",
    "chats",
    "contacts",
}

# 7 个嵌套集合：slim=true 必须一个都不出现
HEAVY_COLLECTIONS = {
    "parties",
    "assignments",
    "logs",
    "case_numbers",
    "supervising_authorities",
    "chats",
    "contacts",
}


def _seed(count: int = CASE_COUNT) -> int:
    """一个合同下 N 个案件，每件都带当事人 + 证件 + 日志（= 全量路径的真实现场）。"""
    contract = ContractFactory()
    for i in range(count):
        case = CaseFactory(contract=contract, name=f"slim案件-{contract.pk}-{i}", current_stage="first_trial")
        client = ClientFactory(name=f"slim当事人-{contract.pk}-{i}")
        CaseParty.objects.create(case=case, client=client, legal_status="plaintiff")
        ClientIdentityDocFactory(client=client, doc_type=ClientIdentityDoc.ID_CARD)
        CaseLogFactory(case=case)
    return contract.pk


def _business_queries(ctx: CaptureQueriesContext) -> list[str]:
    """连接级配置语句（statement_timeout 中间件的 set_config 等）不属业务查询预算。"""
    return [q["sql"] for q in ctx.captured_queries if not q["sql"].lstrip().upper().startswith(("SELECT SET_CONFIG", "SET "))]


@pytest.mark.django_db
class TestCasesSlimList:
    def test_default_response_keeps_full_shape(self, authenticated_client) -> None:
        """不传参数：21 个键一个不少，7 个嵌套集合都在（= 逐字节不变的字段集锚点）。"""
        contract_id = _seed()
        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}")

        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == CASE_COUNT
        assert set(rows[0].keys()) == CASE_OUT_KEYS
        assert HEAVY_COLLECTIONS <= set(rows[0].keys())
        assert "X-Total-Count" not in resp.headers  # 不传 with_total 就不带这个头

    def test_slim_true_drops_heavy_collections(self, authenticated_client) -> None:
        """slim=true：只剩 13 个标量列 + contract_id，7 个嵌套集合一个都不出现。"""
        contract_id = _seed()
        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&slim=true")

        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == CASE_COUNT
        assert set(rows[0].keys()) == CASE_OUT_KEYS - HEAVY_COLLECTIONS
        assert not (HEAVY_COLLECTIONS & set(rows[0].keys()))

    def test_slim_true_keeps_list_page_fields_and_labels(self, authenticated_client) -> None:
        """列表页 CaseRow 的 7 个 Pick 必须都在，且 status/current_stage 仍是中文标签。

        CaseListPage.tsx 拿 `c.status === '在办'` 判「待立案优先」并直接渲染文案；
        返回代码值（active）会让这一页半英半中。
        """
        contract_id = _seed()
        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&slim=true")
        row = resp.json()[0]

        for field in ("id", "name", "status", "current_stage", "cause_of_action", "target_amount", "filing_number"):
            assert field in row, f"列表页要读 {field}，slim 不能裁它"
        assert row["status"] == "在办"
        assert row["current_stage"] == "一审"

    def test_slim_true_cuts_sql_not_just_fields(self, authenticated_client) -> None:
        """slim=true 的 SQL 条数必须明显少于 slim=false（预取同步裁剪）。

        同一个种子、同一条 URL，只差一个 slim 参数。种子是「案件 + 当事人 + 证件 +
        日志」，全量路径会把 10+ 条预取全花掉；瘦身路径没有嵌套集合要填，只该剩 1 条
        案件页查询（+1 条合同可见性/权限相关的既有查询余量）。
        """
        contract_id = _seed()
        with CaptureQueriesContext(connection) as full_ctx:
            full_resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}")
        with CaptureQueriesContext(connection) as slim_ctx:
            slim_resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&slim=true")

        assert full_resp.status_code == slim_resp.status_code == 200
        full_n = len(_business_queries(full_ctx))
        slim_n = len(_business_queries(slim_ctx))

        assert slim_n < full_n, f"瘦身列表没省 SQL：slim=false {full_n} 条 / slim=true {slim_n} 条"
        assert slim_n <= 3, (
            f"slim=true 用了 {slim_n} 条 SQL（全量 {full_n} 条）：预取裁剪失效，"
            f"检查 get_case_queryset(slim=True) 是否仍带 prefetch_related"
        )
        # 差额至少 = 7 个嵌套集合各一条预取的一半（留足余量，只钉「明显」
        assert full_n - slim_n >= 5, f"SQL 只少了 {full_n - slim_n} 条（全量 {full_n} / 瘦身 {slim_n}）"

    def test_slim_rerouted_queryset_would_fail_budget(self) -> None:
        """get_case_queryset(slim=True) 不带任何预取（不预取的证据，绕过 HTTP 直测 queryset）。"""
        _seed()
        qs = get_case_queryset(slim=True)
        assert qs._prefetch_related_lookups == ()
        assert qs.query.select_related is False


@pytest.mark.django_db
class TestCasesWithTotalHeader:
    def test_total_header_equals_real_total(self, authenticated_client) -> None:
        contract_id = _seed()
        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&with_total=true")

        assert resp.status_code == 200
        assert resp.headers["X-Total-Count"] == str(CASE_COUNT)
        assert len(resp.json()) == CASE_COUNT  # 响应体仍是裸数组

    def test_total_header_ignores_limit_and_offset(self, authenticated_client) -> None:
        """总数是「过滤后的全集」，不随 limit/offset 变（翻页时才能算页数）。"""
        contract_id = _seed()
        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&limit=1&offset=1&with_total=true")

        assert resp.status_code == 200
        assert resp.headers["X-Total-Count"] == str(CASE_COUNT)
        assert len(resp.json()) == 1

    def test_total_header_with_slim_and_filters(self, authenticated_client) -> None:
        """slim 与 with_total 正交：组合使用时总数仍按 status 过滤口径算。"""
        contract_id = _seed()
        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&status=active&slim=true&with_total=true")

        assert resp.status_code == 200
        assert resp.headers["X-Total-Count"] == str(CASE_COUNT)
        assert set(resp.json()[0].keys()) == CASE_OUT_KEYS - HEAVY_COLLECTIONS

    def test_total_header_on_case_number_branch(self, authenticated_client) -> None:
        """案号分支不切片（历史行为），X-Total-Count 仍等于命中数。"""
        from apps.cases.models import CaseNumber

        contract_id = _seed()
        case = CaseFactory(contract=ContractFactory(name="slim案号合同"), name="slim案号案件")
        CaseNumber.objects.create(case=case, number="(2026)slim9001号")
        resp = authenticated_client.get(f"{LIST_URL}?case_number=slim9001&with_total=true")

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.headers["X-Total-Count"] == "1"
        # 同一个种子的合同列表总数不受影响（口径确实按过滤条件走）
        baseline = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&with_total=true")
        assert baseline.headers["X-Total-Count"] == str(CASE_COUNT)
