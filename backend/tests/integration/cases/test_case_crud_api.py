"""
案件 CRUD API 集成测试

通过直接调用 API 函数测试完整的 CRUD 流程。
使用 factories 创建测试数据。

Requirements: 5.1
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import Mock

import pytest

from apps.cases.api.case_api import create_case, delete_case, get_case, list_cases, search_cases, update_case
from apps.cases.models import Case, CaseNumber
from apps.cases.schemas import CaseIn, CaseUpdate
from apps.core.exceptions import ForbiddenError, NotFoundError
from tests.factories.case_factories import CaseFactory, CasePartyFactory
from tests.factories.client_factories import ClientFactory
from tests.factories.contract_factories import ContractFactory
from tests.factories.organization_factories import LawyerFactory


def _make_request(
    user: Any = None,
    *,
    perm_open_access: bool = True,
    org_access: Any = None,
) -> Mock:
    """构造模拟 request 对象。"""
    request = Mock()
    request.user = user
    request.perm_open_access = perm_open_access
    request.org_access = org_access
    return request


@pytest.mark.django_db
@pytest.mark.integration
class TestCaseCreateAPI:
    """案件创建 API 测试"""

    def test_create_case_minimal(self) -> None:
        """最小字段创建案件"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = CaseIn(  # type: ignore[call-arg]
            name="测试案件",
            is_archived=False,
            current_stage="first_trial",
        )
        result = create_case(request, payload)

        assert result.id is not None  # type: ignore[attr-defined]
        assert result.name == "测试案件"  # type: ignore[attr-defined]
        assert result.is_archived is False  # type: ignore[attr-defined]

    def test_create_case_with_contract(self) -> None:
        """关联合同创建案件"""
        lawyer = LawyerFactory(is_admin=True)
        contract = ContractFactory(status="active")
        request = _make_request(user=lawyer)

        # 直接通过 service 创建（不传 current_stage 避免阶段验证）
        from apps.cases.api.case_api import _get_case_service

        service = _get_case_service()
        data = {
            "name": "合同关联案件",
            "is_archived": False,
            "contract_id": contract.id,  # type: ignore[attr-defined]
        }
        result = service.create_case(data, user=lawyer)

        assert result.contract_id == contract.id  # type: ignore[attr-defined]

    def test_create_case_with_full_fields(self) -> None:
        """完整字段创建案件"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = CaseIn(  # type: ignore[call-arg]
            name="完整案件",
            status="active",
            is_archived=True,
            case_type="civil",
            target_amount=Decimal("50000.00"),
            preservation_amount=Decimal("10000.00"),
            cause_of_action="合同纠纷",
            current_stage="first_trial",
        )
        result = create_case(request, payload)

        assert result.name == "完整案件"  # type: ignore[attr-defined]
        assert result.is_archived is True  # type: ignore[attr-defined]
        assert result.case_type == "civil"  # type: ignore[attr-defined]
        assert result.cause_of_action == "合同纠纷"  # type: ignore[attr-defined]


@pytest.mark.django_db
@pytest.mark.integration
class TestCaseListAPI:
    """案件列表查询 API 测试"""

    def test_list_cases_empty(self) -> None:
        """空列表查询"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_cases(request)
        assert len(list(result)) == 0

    def test_list_cases_returns_all(self) -> None:
        """查询所有案件"""
        CaseFactory.create_batch(3)
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_cases(request)
        assert len(list(result)) == 3

    def test_list_cases_filter_by_case_type(self) -> None:
        """按案件类型过滤"""
        civil_contract = ContractFactory(case_type="civil")
        criminal_contract = ContractFactory(case_type="criminal")
        CaseFactory.create_batch(2, contract=civil_contract)
        CaseFactory(contract=criminal_contract)

        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_cases(request, case_type="civil")
        assert len(list(result)) == 2

    def test_list_cases_filter_by_case_number(self) -> None:
        """按案号搜索"""
        case = CaseFactory()
        from apps.cases.utils import normalize_case_number

        CaseNumber.objects.create(  # type: ignore[misc]
            case=case,
            number=normalize_case_number("（2024）粤01民初12345号"),
        )

        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_cases(request, case_number="（2024）粤01民初12345号")
        result_list = list(result)
        assert len(result_list) >= 1
        assert case.id in [c.id for c in result_list]  # type: ignore[attr-defined]


@pytest.mark.django_db
@pytest.mark.integration
class TestCaseGetAPI:
    """案件详情查询 API 测试"""

    def test_get_case_success(self) -> None:
        """获取案件详情"""
        case = CaseFactory(name="详情测试案件")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = get_case(request, case.id)  # type: ignore[attr-defined]

        assert result.id == case.id  # type: ignore[attr-defined]
        assert result.name == "详情测试案件"  # type: ignore[attr-defined]

    def test_get_case_not_found(self) -> None:
        """获取不存在的案件"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            get_case(request, 999999)

    def test_get_case_permission_denied(self) -> None:
        """无权限访问案件"""
        case = CaseFactory()
        lawyer = LawyerFactory(is_admin=False)
        request = _make_request(
            user=lawyer,
            perm_open_access=False,
            org_access={"lawyers": set(), "extra_cases": set()},
        )

        with pytest.raises(ForbiddenError):
            get_case(request, case.id)  # type: ignore[attr-defined]


@pytest.mark.django_db
@pytest.mark.integration
class TestCaseUpdateAPI:
    """案件更新 API 测试"""

    def test_update_case_name(self) -> None:
        """更新案件名称"""
        case = CaseFactory(name="旧名称")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = CaseUpdate(name="新名称")
        result = update_case(request, case.id, payload)  # type: ignore[attr-defined]

        assert result.name == "新名称"  # type: ignore[attr-defined]
        case.refresh_from_db()  # type: ignore[attr-defined]
        assert case.name == "新名称"

    def test_update_case_status(self) -> None:
        """更新案件状态"""
        case = CaseFactory(status="active")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = CaseUpdate(status="closed")
        result = update_case(request, case.id, payload)  # type: ignore[attr-defined]

        assert result.status == "closed"  # type: ignore[attr-defined]

    def test_update_case_not_found(self) -> None:
        """更新不存在的案件"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = CaseUpdate(name="新名称")
        with pytest.raises(NotFoundError):
            update_case(request, 999999, payload)

    def test_update_case_partial(self) -> None:
        """部分更新（只更新指定字段）"""
        case = CaseFactory(name="原名称", cause_of_action="合同纠纷")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = CaseUpdate(cause_of_action="侵权纠纷")
        result = update_case(request, case.id, payload)  # type: ignore[attr-defined]

        assert result.name == "原名称"  # type: ignore[attr-defined]
        assert result.cause_of_action == "侵权纠纷"  # type: ignore[attr-defined]


@pytest.mark.django_db
@pytest.mark.integration
class TestCaseDeleteAPI:
    """案件删除 API 测试"""

    def test_delete_case_success(self) -> None:
        """删除案件"""
        case = CaseFactory()
        case_id = case.id  # type: ignore[attr-defined]
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = delete_case(request, case_id)

        assert result["success"] is True
        assert not Case.objects.filter(id=case_id).exists()

    def test_delete_case_not_found(self) -> None:
        """删除不存在的案件"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            delete_case(request, 999999)


@pytest.mark.django_db
@pytest.mark.integration
class TestCaseSearchAPI:
    """案件搜索 API 测试"""

    def test_search_by_name(self) -> None:
        """按案件名称搜索"""
        CaseFactory(name="张三诉李四合同纠纷")
        CaseFactory(name="王五诉赵六侵权纠纷")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = search_cases(request, q="张三")
        assert len(result) == 1
        assert result[0].name == "张三诉李四合同纠纷"  # type: ignore[attr-defined]

    def test_search_by_party_name(self) -> None:
        """按当事人姓名搜索"""
        case = CaseFactory(name="某案件")
        client = ClientFactory(name="测试当事人甲")
        CasePartyFactory(case=case, client=client)

        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = search_cases(request, q="测试当事人甲")
        assert len(result) >= 1
        assert case.id in [c.id for c in result]  # type: ignore[attr-defined]

    def test_search_empty_query(self) -> None:
        """空查询返回空结果"""
        CaseFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = search_cases(request, q="")
        assert len(result) == 0
