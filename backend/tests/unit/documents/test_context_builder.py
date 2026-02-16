# -*- coding: utf-8 -*-
"""
ContextBuilder 单元测试
"""

import pytest
from decimal import Decimal
from datetime import date
from django.test import TestCase

from apps.documents.services.generation.context_builder import ContextBuilder
from apps.contracts.models import Contract, ContractParty, ContractAssignment, PartyRole, FeeMode
from apps.client.models import Client
from apps.organization.models import Lawyer, LawFirm
from apps.core.enums import CaseType, CaseStatus


class ContextBuilderTest(TestCase):
    """ContextBuilder 测试类"""
    
    def setUp(self):
        """设置测试数据"""
        self.context_builder = ContextBuilder()
        
        # 创建律所
        self.law_firm = LawFirm.objects.create(
            name="测试律所",
            address="测试地址",
            phone="12345678901"
        )
        
        # 创建律师
        self.lawyer1 = Lawyer.objects.create(
            username="lawyer1",
            real_name="张律师",
            phone="13800138001",
            license_no="12345678901234567890",
            law_firm=self.law_firm
        )
        
        self.lawyer2 = Lawyer.objects.create(
            username="lawyer2", 
            real_name="李律师",
            phone="13800138002",
            license_no="09876543210987654321",
            law_firm=self.law_firm
        )
        
        # 创建当事人
        self.client1 = Client.objects.create(
            name="张三",
            phone="13900139001",
            address="北京市朝阳区",
            id_number="110101199001011234",
            client_type=Client.NATURAL
        )
        
        self.client2 = Client.objects.create(
            name="李四",
            phone="13900139002", 
            address="上海市浦东区",
            id_number="310115199002022345",
            client_type=Client.NATURAL
        )
        
        self.client3 = Client.objects.create(
            name="某某公司",
            phone="13900139003",
            address="深圳市南山区",
            id_number="91440300123456789X",
            client_type=Client.LEGAL,
            legal_representative="王五"
        )
        
        # 创建合同
        self.contract = Contract.objects.create(
            name="测试合同",
            case_type=CaseType.CIVIL,
            status=CaseStatus.ACTIVE,
            specified_date=date(2024, 1, 15),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            fee_mode=FeeMode.FIXED,
            fixed_amount=Decimal('50000.00'),
            risk_rate=Decimal('30.00'),
            custom_terms="测试条款",
            representation_stages=["一审", "二审"]
        )
        
        # 创建合同当事人
        ContractParty.objects.create(
            contract=self.contract,
            client=self.client1,
            role=PartyRole.PRINCIPAL
        )
        
        ContractParty.objects.create(
            contract=self.contract,
            client=self.client2,
            role=PartyRole.BENEFICIARY
        )
        
        ContractParty.objects.create(
            contract=self.contract,
            client=self.client3,
            role=PartyRole.OPPOSING
        )
        
        # 创建律师指派
        ContractAssignment.objects.create(
            contract=self.contract,
            lawyer=self.lawyer1,
            is_primary=True,
            order=1
        )
        
        ContractAssignment.objects.create(
            contract=self.contract,
            lawyer=self.lawyer2,
            is_primary=False,
            order=2
        )
    
    def test_build_contract_context_success(self):
        """测试成功构建合同上下文"""
        context = self.context_builder.build_contract_context(self.contract.id)
        
        # 验证合同基本信息
        self.assertEqual(context['contract_name'], '测试合同')
        self.assertEqual(context['contract_type'], '民商事')
        self.assertEqual(context['contract_type_code'], 'civil')
        self.assertEqual(context['contract_date'], '2024年01月15日')
        self.assertEqual(context['contract_start_date'], '2024年01月01日')
        self.assertEqual(context['contract_end_date'], '2024年12月31日')
        self.assertEqual(context['fee_mode'], '固定收费')
        self.assertEqual(context['fee_mode_code'], 'FIXED')
        self.assertEqual(context['fixed_amount'], '50,000.00')
        self.assertEqual(context['fixed_amount_raw'], Decimal('50000.00'))
        self.assertEqual(context['risk_rate'], '30.00%')
        self.assertEqual(context['risk_rate_raw'], Decimal('30.00'))
        self.assertEqual(context['custom_terms'], '测试条款')
        self.assertEqual(context['representation_stages'], '一审, 二审')
        
        # 验证委托人信息
        self.assertEqual(context['principal_name'], '张三')
        self.assertEqual(context['principal_id_number'], '110101199001011234')
        self.assertEqual(context['principal_phone'], '13900139001')
        self.assertEqual(context['principal_address'], '北京市朝阳区')
        self.assertEqual(len(context['all_principals']), 1)
        self.assertEqual(context['all_principals'][0]['name'], '张三')
        
        # 验证受益人信息
        self.assertEqual(context['beneficiary_name'], '李四')
        self.assertEqual(context['beneficiary_id_number'], '310115199002022345')
        
        # 验证对方当事人信息
        self.assertEqual(context['opposing_party_name'], '某某公司')
        self.assertEqual(context['all_opposing_parties'], ['某某公司'])
        
        # 验证主办律师信息
        self.assertEqual(context['primary_lawyer_name'], '张律师')
        self.assertEqual(context['primary_lawyer_phone'], '13800138001')
        self.assertEqual(context['primary_lawyer_license'], '12345678901234567890')
        
        # 验证所有律师列表
        self.assertEqual(len(context['all_lawyers']), 2)
        self.assertEqual(context['all_lawyers'][0]['name'], '张律师')
        self.assertEqual(context['all_lawyers'][0]['is_primary'], True)
        self.assertEqual(context['all_lawyers'][1]['name'], '李律师')
        self.assertEqual(context['all_lawyers'][1]['is_primary'], False)
    
    def test_build_contract_context_not_found(self):
        """测试合同不存在的情况"""
        context = self.context_builder.build_contract_context(99999)
        self.assertEqual(context, {})
    
    def test_build_contract_context_no_parties(self):
        """测试没有当事人的合同"""
        # 创建一个没有当事人的合同
        contract_no_parties = Contract.objects.create(
            name="无当事人合同",
            case_type=CaseType.CIVIL,
            status=CaseStatus.ACTIVE,
            specified_date=date(2024, 1, 15)
        )
        
        context = self.context_builder.build_contract_context(contract_no_parties.id)
        
        # 验证空的当事人信息
        self.assertEqual(context['principal_name'], '')
        self.assertEqual(context['principal_id_number'], '')
        self.assertEqual(context['principal_phone'], '')
        self.assertEqual(context['principal_address'], '')
        self.assertEqual(context['all_principals'], [])
        self.assertEqual(context['beneficiary_name'], '')
        self.assertEqual(context['beneficiary_id_number'], '')
        self.assertEqual(context['opposing_party_name'], '')
        self.assertEqual(context['all_opposing_parties'], [])
    
    def test_build_contract_context_no_lawyers(self):
        """测试没有律师的合同"""
        # 创建一个没有律师的合同
        contract_no_lawyers = Contract.objects.create(
            name="无律师合同",
            case_type=CaseType.CIVIL,
            status=CaseStatus.ACTIVE,
            specified_date=date(2024, 1, 15)
        )
        
        context = self.context_builder.build_contract_context(contract_no_lawyers.id)
        
        # 验证空的律师信息
        self.assertEqual(context['primary_lawyer_name'], '')
        self.assertEqual(context['primary_lawyer_phone'], '')
        self.assertEqual(context['primary_lawyer_license'], '')
        self.assertEqual(context['all_lawyers'], [])
    
    def test_format_date(self):
        """测试日期格式化"""
        test_date = date(2024, 1, 15)
        formatted = self.context_builder._format_date(test_date)
        self.assertEqual(formatted, '2024年01月15日')
        
        # 测试 None 值
        formatted_none = self.context_builder._format_date(None)
        self.assertEqual(formatted_none, '')
    
    def test_format_currency(self):
        """测试货币格式化"""
        amount = Decimal('12345.67')
        formatted = self.context_builder._format_currency(amount)
        self.assertEqual(formatted, '12,345.67')
        
        # 测试 None 值
        formatted_none = self.context_builder._format_currency(None)
        self.assertEqual(formatted_none, '')
    
    def test_format_percentage(self):
        """测试百分比格式化"""
        rate = Decimal('25.50')
        formatted = self.context_builder._format_percentage(rate)
        self.assertEqual(formatted, '25.50%')
        
        # 测试 None 值
        formatted_none = self.context_builder._format_percentage(None)
        self.assertEqual(formatted_none, '')
    
    def test_custom_date_format(self):
        """测试自定义日期格式"""
        custom_builder = ContextBuilder(date_format='%Y-%m-%d')
        test_date = date(2024, 1, 15)
        formatted = custom_builder._format_date(test_date)
        self.assertEqual(formatted, '2024-01-15')