"""``GET /api/v1/cases/cases`` 的 search / sort 两个下推参数的契约门禁。

背景：前端「银行批量诉讼 · 案件列表」原先是**前端过滤 + 前端排序**（关键词过滤
name / cause_of_action，"待立案优先"再按 id 倒序）。上服务端分页后这两个逻辑只会
作用在当前页，所以必须先下推后端：

- ``search=<kw>``：name icontains OR cause_of_action icontains（大小写不敏感）
- ``sort=filable_first``：待立案优先——filing_number 为空 且 status=active 的排在前，
  其余在后；同组内 id DESC。不传 / 未知值 → 历史默认 ``-id``。

本文件钉三件事：
1. search 只命中 name 或 cause_of_action，且 ``count_cases`` 与 ``list_cases`` **同口径**
   （X-Total-Count 必须等于「不带分页的全量命中数」，否则翻页对不上——本任务最容易
   出的错就是 search 只进了 list 没进 count）；
2. sort=filable_first 的分组与组内顺序（4 条数据覆盖两组；额外一条历史空串数据）；
3. 不传两个参数时行为与改动前逐条一致（``-id``），未知 sort 值等于没传（不 400）。

反向验证（本文件是不是真门禁）：把 ``CaseSearchService.count_cases`` 里的
``search=search`` 去掉，``TestSearchScope::test_total_matches_full_match_count`` 立刻
变红（total 3 → 变成全集 4），见该用例 assert 消息。
"""

from __future__ import annotations

import pytest

from apps.cases.models import Case
from apps.cases.services.case.case_search_service import CaseSearchService
from apps.core.models.enums import CaseStatus
from apps.testing.factories import CaseFactory, ContractFactory

LIST_URL = "/api/v1/cases/cases"


def _seed_search_cases() -> tuple[int, dict[str, int]]:
    """一个合同下 4 件案子：1 件名命中、1 件案由命中、1 件两者都命中、1 件无关。"""
    contract = ContractFactory(name="search契约合同")
    by_name = CaseFactory(contract=contract, name="中原银行借款合同纠纷", cause_of_action="买卖合同纠纷")
    by_cause = CaseFactory(contract=contract, name="张三诉李四", cause_of_action="金融借款合同纠纷")
    both = CaseFactory(contract=contract, name="借款担保纠纷", cause_of_action="借款合同")
    # 关键词只出现在当事人姓名里，**不该**被 search 命中（契约只覆盖 name / cause_of_action）
    unrelated = CaseFactory(contract=contract, name="王五诉赵六", cause_of_action="劳动争议")
    return contract.pk, {
        "by_name": by_name.pk,
        "by_cause": by_cause.pk,
        "both": both.pk,
        "unrelated": unrelated.pk,
    }


def _seed_filable_cases() -> tuple[int, list[tuple[str, int]]]:
    """一个合同下 6 件案子，覆盖「可立案 / 不可立案」两组；返回 (contract_id, [(name, id)])。

    「可立案」= filing_number 为空 且 status=active。其中 ``filable_blank`` 的历史数据显示
    为空串而非 NULL（``Case.save`` 只保证新写入存 NULL），用 ``.update()`` 绕过 save
    模拟这批历史数据——SQL 条件必须同时覆盖 NULL 与 ''。
    """
    contract = ContractFactory(name="filable契约合同")
    created = [
        ("filable_new", CaseFactory(contract=contract, name="filable_new", status=CaseStatus.ACTIVE)),
        (
            "filed",
            CaseFactory(contract=contract, name="filed", status=CaseStatus.ACTIVE, filing_number="2026_CIVIL_AJ_0001"),
        ),
        ("closed_no_number", CaseFactory(contract=contract, name="closed_no_number", status=CaseStatus.CLOSED)),
        (
            "closed_filed",
            CaseFactory(
                contract=contract, name="closed_filed", status=CaseStatus.CLOSED, filing_number="2026_CIVIL_AJ_0002"
            ),
        ),
        ("filable_old", CaseFactory(contract=contract, name="filable_old", status=CaseStatus.ACTIVE)),
        ("filable_blank", CaseFactory(contract=contract, name="filable_blank", status=CaseStatus.ACTIVE)),
    ]
    blank_id = dict(created)["filable_blank"].pk
    Case.objects.filter(pk=blank_id).update(filing_number="")
    return contract.pk, [(name, case.pk) for name, case in created]


@pytest.mark.django_db
class TestSearchScope:
    def test_search_matches_name_or_cause_of_action(self, authenticated_client) -> None:
        """命中必须是 name 或 cause_of_action 的并集，当事人姓名不在契约内。"""
        contract_id, ids = _seed_search_cases()

        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&search=借款&slim=true")

        assert resp.status_code == 200
        assert {row["id"] for row in resp.json()} == {ids["by_name"], ids["by_cause"], ids["both"]}
        assert ids["unrelated"] not in {row["id"] for row in resp.json()}

    def test_search_is_case_insensitive(self, authenticated_client) -> None:
        """icontains：大写关键词也要命中（前端关键词来自用户输入，大小写不可控）。"""
        contract = ContractFactory(name="大小写合同")
        hit = CaseFactory(contract=contract, name="Alpha Bank Loan", cause_of_action="Financial Loan")
        CaseFactory(contract=contract, name="无关案件", cause_of_action="劳动争议")

        upper = authenticated_client.get(f"{LIST_URL}?contract_id={contract.pk}&search=ALPHA&slim=true")
        lower = authenticated_client.get(f"{LIST_URL}?contract_id={contract.pk}&search=loan&slim=true")

        assert [row["id"] for row in upper.json()] == [hit.pk]
        assert {row["id"] for row in lower.json()} == {hit.pk}

    def test_total_matches_full_match_count(self, authenticated_client) -> None:
        """count_cases 与 list_cases 同口径：total = 不带分页的全量命中数。

        反向验证：把 count_cases 里的 search=search 去掉，这里 total 会变成 4（全集），
        与「命中 3 条」对不上 → 用例红。
        """
        contract_id, ids = _seed_search_cases()

        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&search=借款&with_total=true&slim=true")

        assert resp.status_code == 200
        assert resp.headers["X-Total-Count"] == "3", (
            f"total={resp.headers.get('X-Total-Count')}：count_cases 没吃到 search，搜索时总数会恒为全集（4 条）"
        )
        assert {row["id"] for row in resp.json()} == {ids["by_name"], ids["by_cause"], ids["both"]}

    def test_total_stable_across_pages_under_search(self, authenticated_client) -> None:
        """翻页时 total 不变、两次分页拼起来正好是全量命中且无重叠。"""
        contract_id, ids = _seed_search_cases()

        first = authenticated_client.get(
            f"{LIST_URL}?contract_id={contract_id}&search=借款&slim=true&with_total=true&limit=2&offset=0"
        )
        second = authenticated_client.get(
            f"{LIST_URL}?contract_id={contract_id}&search=借款&slim=true&with_total=true&limit=2&offset=2"
        )

        assert first.headers["X-Total-Count"] == second.headers["X-Total-Count"] == "3"
        assert len(first.json()) == 2
        assert len(second.json()) == 1
        assert {row["id"] for row in first.json() + second.json()} == {ids["by_name"], ids["by_cause"], ids["both"]}

    def test_service_count_equals_service_list(self) -> None:
        """绕过 HTTP 直测 Service：同 search 下 count_cases == list_cases 的全量长度。"""
        contract_id, _ = _seed_search_cases()
        svc = CaseSearchService()

        listed = list(svc.list_cases(contract_id=contract_id, search="借款", perm_open_access=True, slim=True))

        assert len(listed) == 3
        assert svc.count_cases(contract_id=contract_id, search="借款", perm_open_access=True) == len(listed)


@pytest.mark.django_db
class TestFilableFirstSort:
    def test_filable_first_groups_and_order(self, authenticated_client) -> None:
        """可立案组在前，组内 id DESC；有案号 / 已结案 / 无案号但已结 全在第二组。

        期望：可立案组 {filable_blank, filable_old, filable_new}（id DESC），
        随后不可立案组 {closed_filed, closed_no_number, filed}（id DESC）。
        """
        contract_id, created = _seed_filable_cases()
        case_id = dict(created)

        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&sort=filable_first&slim=true")

        assert resp.status_code == 200
        assert [row["id"] for row in resp.json()] == [
            case_id["filable_blank"],
            case_id["filable_old"],
            case_id["filable_new"],
            case_id["closed_filed"],
            case_id["closed_no_number"],
            case_id["filed"],
        ]
        # 组内 id 严格递减（不是碰巧按名字排的）
        rows = resp.json()
        for group in (rows[:3], rows[3:]):
            assert [row["id"] for row in group] == sorted((row["id"] for row in group), reverse=True)

    def test_filable_first_total_ignores_sort(self, authenticated_client) -> None:
        """sort 不影响 total：口径只由过滤条件决定（排序只是顺序）。"""
        contract_id, _ = _seed_filable_cases()

        resp = authenticated_client.get(
            f"{LIST_URL}?contract_id={contract_id}&sort=filable_first&with_total=true&slim=true"
        )

        assert resp.headers["X-Total-Count"] == "6"

    def test_sort_and_search_combine(self, authenticated_client) -> None:
        """两个参数正交：search 先收敛集合，sort 再排。"""
        contract = ContractFactory(name="组合合同")
        filable = CaseFactory(
            contract=contract, name="借款可立案", cause_of_action="借款合同", status=CaseStatus.ACTIVE
        )
        filed = CaseFactory(
            contract=contract,
            name="借款已建档",
            cause_of_action="借款合同",
            status=CaseStatus.ACTIVE,
            filing_number="2026_CIVIL_AJ_0003",
        )
        closed = CaseFactory(contract=contract, name="借款已结", cause_of_action="借款合同", status=CaseStatus.CLOSED)
        CaseFactory(contract=contract, name="无关案件", cause_of_action="劳动争议")

        resp = authenticated_client.get(
            f"{LIST_URL}?contract_id={contract.pk}&search=借款&sort=filable_first&slim=true&with_total=true"
        )

        # 命中 3 条：可立案的排最前；第二组内按 id DESC（closed 比 filed 后建）
        assert resp.headers["X-Total-Count"] == "3"
        assert [row["id"] for row in resp.json()] == [filable.pk, closed.pk, filed.pk]


@pytest.mark.django_db
class TestDefaultBehaviourUnchanged:
    def test_default_order_is_id_desc(self, authenticated_client) -> None:
        """不传 sort → 历史默认 -id（逐条与改动前的 order_by("-id") 一致）。"""
        contract_id, created = _seed_filable_cases()

        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&slim=true")

        assert [row["id"] for row in resp.json()] == [case_id for _, case_id in reversed(created)]

    @pytest.mark.parametrize("sort", ["", "unknown", "id", "-created_at"])
    def test_unknown_sort_falls_back_to_id_desc(self, authenticated_client, sort: str) -> None:
        """sort 只认白名单；未知值当作没传（前端生成物里是自由字符串，不能 400）。"""
        contract_id, created = _seed_filable_cases()

        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&slim=true&sort={sort}")

        assert resp.status_code == 200
        assert [row["id"] for row in resp.json()] == [case_id for _, case_id in reversed(created)]

    def test_no_search_returns_everything(self, authenticated_client) -> None:
        """不传 search → 不做关键词过滤（4 条件全在）。"""
        contract_id, ids = _seed_search_cases()

        resp = authenticated_client.get(f"{LIST_URL}?contract_id={contract_id}&slim=true")

        assert {row["id"] for row in resp.json()} == set(ids.values())
