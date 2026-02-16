# -*- coding: utf-8 -*-
"""
补充协议占位符服务测试

测试补充协议相关的占位符服务是否正确注册和工作。
"""

from datetime import date
from unittest.mock import MagicMock, Mock

import pytest

from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.documents.services.placeholders.supplementary.basic_service import SupplementaryAgreementBasicService
from apps.documents.services.placeholders.supplementary.opposing_service import SupplementaryAgreementOpposingService
from apps.documents.services.placeholders.supplementary.principal_service import SupplementaryAgreementPrincipalService
from apps.documents.services.placeholders.supplementary.signature_service import SupplementaryAgreementSignatureService


class TestSupplementaryAgreementServiceRegistration:
    """测试补充协议服务注册"""

    def test_basic_service_registered(self):
        """测试基础服务已注册"""
        registry = PlaceholderRegistry()
        service = registry.get_service("supplementary_agreement_basic_service")
        assert service is not None
        assert isinstance(service, SupplementaryAgreementBasicService)

    def test_principal_service_registered(self):
        """测试委托人服务已注册"""
        registry = PlaceholderRegistry()
        service = registry.get_service("supplementary_agreement_principal_service")
        assert service is not None
        assert isinstance(service, SupplementaryAgreementPrincipalService)

    def test_opposing_service_registered(self):
        """测试对方当事人服务已注册"""
        registry = PlaceholderRegistry()
        service = registry.get_service("supplementary_agreement_opposing_service")
        assert service is not None
        assert isinstance(service, SupplementaryAgreementOpposingService)

    def test_signature_service_registered(self):
        """测试签名服务已注册"""
        registry = PlaceholderRegistry()
        service = registry.get_service("supplementary_agreement_signature_service")
        assert service is not None
        assert isinstance(service, SupplementaryAgreementSignatureService)


class TestSupplementaryAgreementBasicService:
    """测试补充协议基础服务"""

    def test_generate_with_agreement(self):
        """测试有补充协议时的生成"""
        service = SupplementaryAgreementBasicService()

        # 创建模拟的补充协议
        mock_agreement = Mock()
        mock_agreement.name = "测试补充协议"

        context_data = {"supplementary_agreement": mock_agreement}

        result = service.generate(context_data)

        assert "补充协议名称" in result
        assert result["补充协议名称"] == "测试补充协议"
        assert "年份" in result
        assert result["年份"] == str(date.today().year)

    def test_generate_without_agreement(self):
        """测试没有补充协议时的生成"""
        service = SupplementaryAgreementBasicService()

        context_data = {}

        result = service.generate(context_data)

        assert "补充协议名称" in result
        assert result["补充协议名称"] == ""
        assert "年份" in result
        assert result["年份"] == str(date.today().year)

    def test_get_current_year(self):
        """测试获取当前年份"""
        service = SupplementaryAgreementBasicService()
        year = service.get_current_year()
        assert year == str(date.today().year)


class TestSupplementaryAgreementPrincipalService:
    """测试补充协议委托人服务"""

    def test_generate_with_data(self):
        """测试有数据时的生成"""
        service = SupplementaryAgreementPrincipalService()

        # 创建模拟数据
        mock_contract = Mock()
        mock_agreement = Mock()

        context_data = {"contract": mock_contract, "supplementary_agreement": mock_agreement}

        # 模拟方法返回值
        service._get_agreement_principals = Mock(return_value=[])
        service._get_contract_principals = Mock(return_value=[])
        service._find_new_principals = Mock(return_value=([], []))
        service.format_principal_info = Mock(return_value="委托人信息")
        service.format_principal_clause = Mock(return_value="")

        result = service.generate(context_data)

        assert "委托人信息" in result
        assert "委托人主体信息条款" in result

    def test_format_principal_info_single(self):
        """测试单个委托人信息格式化"""
        service = SupplementaryAgreementPrincipalService()

        # 创建模拟客户
        mock_client = Mock()
        mock_client.name = "张三"

        service._format_client_details = Mock(return_value=["身份证号码：123456789012345678"])

        result = service.format_principal_info([mock_client])

        assert "甲方：张三" in result
        assert "身份证号码：123456789012345678" in result

    def test_format_principal_info_multiple(self):
        """测试多个委托人信息格式化"""
        service = SupplementaryAgreementPrincipalService()

        # 创建模拟客户
        mock_client1 = Mock()
        mock_client1.name = "张三"
        mock_client2 = Mock()
        mock_client2.name = "李四"

        service._format_client_details = Mock(return_value=["详细信息"])

        result = service.format_principal_info([mock_client1, mock_client2])

        assert "甲方一：张三" in result
        assert "甲方二：李四" in result

    def test_format_principal_clause_no_new(self):
        """测试无新增委托人时的条款生成"""
        service = SupplementaryAgreementPrincipalService()

        result = service.format_principal_clause([], [])

        assert result == ""

    def test_format_principal_clause_with_new(self):
        """测试有新增委托人时的条款生成"""
        service = SupplementaryAgreementPrincipalService()

        existing = [Mock()]  # 1个现有委托人
        new = [Mock()]  # 1个新增委托人

        result = service.format_principal_clause(existing, new)

        assert "甲方二" in result
        assert "新增" in result
        assert "共同甲方" in result


class TestSupplementaryAgreementOpposingService:
    """测试补充协议对方当事人服务"""

    def test_generate_with_data(self):
        """测试有数据时的生成"""
        service = SupplementaryAgreementOpposingService()

        mock_agreement = Mock()
        context_data = {"supplementary_agreement": mock_agreement}

        service._get_opposing_parties = Mock(return_value=[])
        service.format_opposing_party_clause = Mock(return_value="")

        result = service.generate(context_data)

        assert "对方当事人主体信息条款" in result


class TestSupplementaryAgreementSignatureService:
    """测试补充协议签名服务"""

    def test_generate_with_data(self):
        """测试有数据时的生成"""
        service = SupplementaryAgreementSignatureService()

        mock_agreement = Mock()
        mock_contract = Mock()
        mock_contract.specified_date = date.today()

        context_data = {"supplementary_agreement": mock_agreement, "contract": mock_contract}

        service._get_agreement_principals = Mock(return_value=[])
        service.format_signature_info = Mock(return_value="签名信息")

        result = service.generate(context_data)

        assert "委托人签名盖章信息" in result
