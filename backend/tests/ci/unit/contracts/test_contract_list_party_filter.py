"""按当事人姓名查合同（party 过滤）的单元测试。

场景来源：材料预处理收到客户送审的合同（客户与第三方签订），
这类合同没有法院案号、也没有律所 OA 编号，判断「它属于哪个委托」
唯一可靠的锚点是**当事人名称**。因此 list_contracts 提供 party 参数，
匹配 ContractParty.client.name，而不是合同名。
"""

from __future__ import annotations

import pytest

from apps.testing.factories import ClientFactory, ContractFactory


def _bind_party(contract, client, role=None):
    from apps.contracts.models.party import ContractParty, PartyRole

    return ContractParty.objects.create(
        contract=contract,
        client=client,
        role=role or PartyRole.PRINCIPAL,
    )


@pytest.mark.django_db
class TestListFilterByParty:
    """_apply_list_filters 的 party 分支"""

    def _service(self):
        from apps.contracts.services.contract.query.service import ContractQueryService

        return ContractQueryService()

    def test_filters_by_party_name(self) -> None:
        """按当事人名命中合同；不相关合同被排除。"""
        svc = self._service()
        client = ClientFactory(name="某某酒店管理有限公司")
        hit = ContractFactory(name="常年法律顾问合同")
        _bind_party(hit, client)
        miss = ContractFactory(name="无关合同")
        _bind_party(miss, ClientFactory(name="某某贸易有限公司"))

        qs = svc.get_contract_queryset()
        out = svc._apply_list_filters(
            qs,
            case_type=None,
            status=None,
            search=None,
            fee_mode=None,
            is_filed=None,
            party="某某酒店",
        )

        ids = list(out.values_list("id", flat=True))
        assert hit.id in ids
        assert miss.id not in ids

    def test_party_matches_any_role(self) -> None:
        """对方当事人也能命中——客户送审合同的对方常是本所不代理的公司。"""
        svc = self._service()
        from apps.contracts.models.party import PartyRole

        opposing = ClientFactory(name="广东某某装饰工程有限公司")
        contract = ContractFactory(name="装修工程合同")
        _bind_party(contract, opposing, role=PartyRole.OPPOSING)

        qs = svc.get_contract_queryset()
        out = svc._apply_list_filters(
            qs,
            case_type=None,
            status=None,
            search=None,
            fee_mode=None,
            is_filed=None,
            party="某某装饰",
        )

        assert contract.id in list(out.values_list("id", flat=True))

    def test_party_no_duplicate_rows(self) -> None:
        """同一合同挂了多个当事人且都被命中时，不出现重复行（distinct）。"""
        svc = self._service()
        contract = ContractFactory(name="顾问合同")
        _bind_party(contract, ClientFactory(name="某某酒店管理有限公司 A"))
        _bind_party(contract, ClientFactory(name="某某酒店管理有限公司 B"))

        qs = svc.get_contract_queryset()
        out = svc._apply_list_filters(
            qs,
            case_type=None,
            status=None,
            search=None,
            fee_mode=None,
            is_filed=None,
            party="某某酒店",
        )

        ids = list(out.values_list("id", flat=True))
        assert ids.count(contract.id) == 1

    def test_party_empty_does_not_filter(self) -> None:
        """party 为空/None 时不生效，不影响原列表。"""
        svc = self._service()
        contract = ContractFactory(name="顾问合同")

        qs = svc.get_contract_queryset()
        for value in (None, ""):
            out = svc._apply_list_filters(
                qs,
                case_type=None,
                status=None,
                search=None,
                fee_mode=None,
                is_filed=None,
                party=value,
            )
            assert contract.id in list(out.values_list("id", flat=True))

    def test_party_and_search_combine(self) -> None:
        """party 与 search 可叠加（AND 语义）：既姓对应当事人、合同名也含关键词。"""
        svc = self._service()
        client = ClientFactory(name="某某酒店管理有限公司")
        both = ContractFactory(name="常年法律顾问合同")
        _bind_party(both, client)
        only_party = ContractFactory(name="装修工程合同")
        _bind_party(only_party, client)

        qs = svc.get_contract_queryset()
        out = svc._apply_list_filters(
            qs,
            case_type=None,
            status=None,
            search="顾问",
            fee_mode=None,
            is_filed=None,
            party="某某酒店",
        )

        ids = list(out.values_list("id", flat=True))
        assert both.id in ids
        assert only_party.id not in ids
