from apps.contracts.services.contract.assemblers.contract_details_assembler import ContractDetailsAssembler


class _Rel:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)


class _Obj:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_contract_details_assembler_builds_expected_shape():
    client = _Obj(id=10, name="甲公司", client_type="COMPANY")
    party = _Obj(id=1, client=client, role="PRINCIPAL")

    law_firm = _Obj(name="律所A")
    lawyer = _Obj(id=20, real_name="张三", law_firm=law_firm)
    assignment = _Obj(id=2, lawyer=lawyer, is_primary=True, order=1)

    case_client = _Obj(id=11, name="乙公司")
    case_party = _Obj(id=3, client=case_client, legal_status="被告")
    authority = _Obj(id=4, name="机构X", authority_type="TYPE")
    case = _Obj(
        id=30,
        name="案件1",
        cause_of_action="买卖合同纠纷",
        target_amount=100,
        parties=_Rel([case_party]),
        supervising_authorities=_Rel([authority]),
    )

    contract = _Obj(
        id=100,
        name="合同1",
        case_type="CIVIL",
        status="active",
        fee_mode="FIXED",
        fixed_amount=200,
        risk_rate=None,
        custom_terms="x",
        representation_stages=["一审"],
        specified_date=None,
        start_date=None,
        end_date=None,
        is_archived=False,
        contract_parties=_Rel([party]),
        assignments=_Rel([assignment]),
        cases=_Rel([case]),
    )

    out = ContractDetailsAssembler().to_dict(contract)
    assert out["id"] == 100
    assert out["contract_parties"][0]["client_name"] == "甲公司"
    assert out["assignments"][0]["lawyer_name"] == "张三"
    assert out["cases"][0]["parties"][0]["client_name"] == "乙公司"
    assert out["cases"][0]["supervising_authorities"][0]["name"] == "机构X"

