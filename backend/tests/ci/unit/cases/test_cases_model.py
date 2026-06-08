"""Cases Model 测试 - Case, CaseLog, CaseParty, CaseAssignment, CaseChat"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.cases.models import (
    Case,
    CaseAssignment,
    CaseLog,
    CaseParty,
    CaseChat,
    CaseNumber,
    SupervisingAuthority,
)
from apps.contracts.models import Contract
from apps.organization.models import Lawyer
from apps.client.models import Client


@pytest.mark.django_db
class TestCaseModel:
    """Case 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回案件名称"""
        contract = Contract.objects.create(name="测试合同", case_type="civil")
        case = Case.objects.create(name="测试案件", contract=contract)
        assert str(case) == "测试案件"

    def test_create_case_with_contract(self) -> None:
        """创建案件关联合同"""
        contract = Contract.objects.create(name="关联合同", case_type="civil")
        case = Case.objects.create(name="合同案件", contract=contract)
        assert case.contract.name == "关联合同"

    def test_create_case_with_status(self) -> None:
        """创建案件指定状态"""
        contract = Contract.objects.create(name="状态测试合同", case_type="civil")
        case = Case.objects.create(name="状态案件", contract=contract, status="active")
        assert case.status == "active"

    def test_create_case_with_case_type(self) -> None:
        """创建案件指定类型"""
        contract = Contract.objects.create(name="类型测试合同", case_type="civil")
        case = Case.objects.create(name="类型案件", contract=contract, case_type="civil")
        assert case.case_type == "civil"

    def test_create_case_with_dates(self) -> None:
        """创建案件包含日期字段"""
        contract = Contract.objects.create(name="日期测试合同", case_type="civil")
        today = date.today()
        case = Case.objects.create(
            name="日期案件",
            contract=contract,
            start_date=today,
            effective_date=today + timedelta(days=30),
        )
        assert case.start_date == today
        assert case.effective_date == today + timedelta(days=30)

    def test_create_case_with_target_amount(self) -> None:
        """创建案件包含涉案金额"""
        from decimal import Decimal

        contract = Contract.objects.create(name="金额测试合同", case_type="civil")
        case = Case.objects.create(
            name="金额案件", contract=contract, target_amount=Decimal("100000.00")
        )
        assert case.target_amount == Decimal("100000.00")

    def test_case_previous_case(self) -> None:
        """案件前序案件关联"""
        contract = Contract.objects.create(name="前序测试合同", case_type="civil")
        case1 = Case.objects.create(name="一审案件", contract=contract)
        case2 = Case.objects.create(name="二审案件", contract=contract, previous_case=case1)
        assert case2.previous_case == case1
        assert case1.next_cases.count() == 1


@pytest.mark.django_db
class TestCaseLogModel:
    """CaseLog 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回日志信息"""
        contract = Contract.objects.create(name="日志测试合同", case_type="civil")
        case = Case.objects.create(name="日志测试案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="log_lawyer", real_name="日志律师")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="测试日志内容")
        # CaseLog.__str__ 返回 case_id-actor_id-created_at 格式
        assert str(case.id) in str(log)

    def test_create_log_with_actor(self) -> None:
        """创建日志关联操作人"""
        contract = Contract.objects.create(name="操作人测试合同", case_type="civil")
        case = Case.objects.create(name="操作人测试案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="actor_lawyer", real_name="操作人律师")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="操作人日志")
        assert log.actor.username == "actor_lawyer"

    def test_create_log_content(self) -> None:
        """创建日志包含内容"""
        contract = Contract.objects.create(name="内容测试合同", case_type="civil")
        case = Case.objects.create(name="内容测试案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="content_lawyer", real_name="内容律师")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="提醒日志")
        assert log.content == "提醒日志"


@pytest.mark.django_db
class TestCasePartyModel:
    """CaseParty 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回当事人信息"""
        contract = Contract.objects.create(name="当事人测试合同", case_type="civil")
        case = Case.objects.create(name="当事人测试案件", contract=contract)
        client = Client.objects.create(name="测试当事人", client_type="natural")
        party = CaseParty.objects.create(case=case, client=client, legal_status="plaintiff")
        assert "测试当事人" in str(party) or "plaintiff" in str(party)

    def test_create_party_with_legal_status(self) -> None:
        """创建当事人指定法律地位"""
        contract = Contract.objects.create(name="地位测试合同", case_type="civil")
        case = Case.objects.create(name="地位测试案件", contract=contract)
        client = Client.objects.create(name="原告", client_type="natural")
        party = CaseParty.objects.create(case=case, client=client, legal_status="plaintiff")
        assert party.legal_status == "plaintiff"


@pytest.mark.django_db
class TestCaseAssignmentModel:
    """CaseAssignment 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回指派信息"""
        contract = Contract.objects.create(name="指派测试合同", case_type="civil")
        case = Case.objects.create(name="指派测试案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="assign_lawyer", real_name="指派律师")
        assignment = CaseAssignment.objects.create(case=case, lawyer=lawyer)
        # CaseAssignment.__str__ 返回 case_id-lawyer_id 格式
        assert str(case.id) in str(assignment)
        assert str(lawyer.id) in str(assignment)


@pytest.mark.django_db
class TestCaseChatModel:
    """CaseChat 模型测试"""

    def test_create_chat(self) -> None:
        """创建聊天记录"""
        contract = Contract.objects.create(name="聊天测试合同", case_type="civil")
        case = Case.objects.create(name="聊天测试案件", contract=contract)
        chat = CaseChat.objects.create(case=case, chat_id="test_chat_001", name="测试群聊")
        assert chat.chat_id == "test_chat_001"
        assert chat.name == "测试群聊"


@pytest.mark.django_db
class TestSupervisingAuthorityModel:
    """SupervisingAuthority 模型测试"""

    def test_create_authority(self) -> None:
        """创建主管机关"""
        contract = Contract.objects.create(name="机关测试合同", case_type="civil")
        case = Case.objects.create(name="机关测试案件", contract=contract)
        authority = SupervisingAuthority.objects.create(
            case=case, name="测试法院", authority_type="court"
        )
        assert authority.name == "测试法院"
        assert authority.authority_type == "court"
