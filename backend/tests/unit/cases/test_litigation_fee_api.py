"""
诉讼费用计算 API 单元测试

测试 API 层的请求处理和响应格式，包括：
- cause_of_action_id 参数传递
- 特殊案件类型字段返回
- 显示控制字段返回

Requirements: 8.1, 8.2, 8.3, 8.4
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch

from apps.cases.api.litigation_fee_api import (
    FeeCalculationRequest,
    FeeCalculationResponse,
    calculate_fee,
)
from apps.core.exceptions import ValidationException


class TestFeeCalculationRequest:
    """费用计算请求 Schema 测试"""

    def test_request_with_cause_of_action_id(self):
        """测试请求包含 cause_of_action_id 参数"""
        # Requirements: 8.1
        request = FeeCalculationRequest(
            target_amount=100000,
            cause_of_action_id=123,
        )
        
        assert request.cause_of_action_id == 123
        assert request.target_amount == 100000

    def test_request_without_cause_of_action_id(self):
        """测试请求不包含 cause_of_action_id 参数"""
        request = FeeCalculationRequest(
            target_amount=100000,
        )
        
        assert request.cause_of_action_id is None

    def test_request_all_fields(self):
        """测试请求包含所有字段"""
        request = FeeCalculationRequest(
            target_amount=100000,
            preservation_amount=50000,
            case_type="civil",
            cause_of_action="合同纠纷",
            cause_of_action_id=456,
        )
        
        assert request.target_amount == 100000
        assert request.preservation_amount == 50000
        assert request.case_type == "civil"
        assert request.cause_of_action == "合同纠纷"
        assert request.cause_of_action_id == 456


class TestFeeCalculationResponse:
    """费用计算响应 Schema 测试"""

    def test_response_special_case_type_field(self):
        """测试响应包含 special_case_type 字段"""
        # Requirements: 8.3
        response = FeeCalculationResponse(
            special_case_type="personality_rights",
            fee_display_text="案件受理费：100-500元",
        )
        
        assert response.special_case_type == "personality_rights"

    def test_response_fee_display_text_field(self):
        """测试响应包含 fee_display_text 字段"""
        # Requirements: 8.4
        response = FeeCalculationResponse(
            fee_display_text="申请撤销仲裁裁决费用：400元",
        )
        
        assert response.fee_display_text == "申请撤销仲裁裁决费用：400元"

    def test_response_fee_range_fields(self):
        """测试响应包含费用范围字段"""
        response = FeeCalculationResponse(
            fee_range_min=100,
            fee_range_max=500,
        )
        
        assert response.fee_range_min == 100
        assert response.fee_range_max == 500

    def test_response_show_fields(self):
        """测试响应包含显示控制字段"""
        response = FeeCalculationResponse(
            show_acceptance_fee=True,
            show_half_fee=True,
            show_payment_order_fee=False,
        )
        
        assert response.show_acceptance_fee is True
        assert response.show_half_fee is True
        assert response.show_payment_order_fee is False

    def test_response_default_show_fields(self):
        """测试响应显示控制字段默认值"""
        response = FeeCalculationResponse()
        
        assert response.show_acceptance_fee is True
        assert response.show_half_fee is True
        assert response.show_payment_order_fee is False


@pytest.mark.django_db
class TestCalculateFeeEndpoint:
    """calculate_fee 端点测试"""

    def test_calculate_fee_with_cause_of_action_id(self):
        """测试传递 cause_of_action_id 参数"""
        # Requirements: 8.1, 8.2
        from apps.core.models import CauseOfAction
        
        # 创建测试案由（人格权纠纷）
        cause = CauseOfAction.objects.create(
            code="9001",
            name="人格权纠纷",
        )
        
        # 创建请求
        request_data = FeeCalculationRequest(
            target_amount=100000,
            cause_of_action_id=cause.id,
        )
        
        # 创建 Mock HTTP 请求
        mock_request = Mock()
        
        # 调用端点
        response = calculate_fee(mock_request, request_data)
        
        # 验证响应包含特殊案件类型
        assert response.special_case_type == "personality_rights"
        assert response.fee_range_min is not None
        assert response.fee_range_max is not None

    def test_calculate_fee_returns_special_case_type(self):
        """测试返回特殊案件类型字段"""
        # Requirements: 8.3
        from apps.core.models import CauseOfAction
        
        # 创建测试案由（知识产权合同纠纷）
        cause = CauseOfAction.objects.create(
            code="9300",
            name="知识产权合同纠纷",
        )
        
        request_data = FeeCalculationRequest(
            cause_of_action_id=cause.id,
        )
        
        mock_request = Mock()
        response = calculate_fee(mock_request, request_data)
        
        assert response.special_case_type == "ip"

    def test_calculate_fee_returns_fee_display_text(self):
        """测试返回特殊费用显示文本"""
        # Requirements: 8.4
        from apps.core.models import CauseOfAction
        
        # 创建测试案由（申请撤销仲裁裁决）
        cause = CauseOfAction.objects.create(
            code="test_revoke",
            name="申请撤销仲裁裁决",
        )
        
        request_data = FeeCalculationRequest(
            cause_of_action_id=cause.id,
        )
        
        mock_request = Mock()
        response = calculate_fee(mock_request, request_data)
        
        assert response.special_case_type == "revoke_arbitration"
        assert response.fee_display_text is not None
        assert "400" in response.fee_display_text

    def test_calculate_fee_payment_order_show_fields(self):
        """测试支付令案件显示控制字段"""
        from apps.core.models import CauseOfAction
        
        # 创建测试案由（申请支付令）
        cause = CauseOfAction.objects.create(
            code="test_payment",
            name="申请支付令",
        )
        
        request_data = FeeCalculationRequest(
            target_amount=100000,
            cause_of_action_id=cause.id,
        )
        
        mock_request = Mock()
        response = calculate_fee(mock_request, request_data)
        
        assert response.special_case_type == "payment_order"
        assert response.show_acceptance_fee is True
        assert response.show_half_fee is True
        assert response.show_payment_order_fee is True

    def test_calculate_fee_fixed_fee_show_fields(self):
        """测试固定费用案件显示控制字段"""
        from apps.core.models import CauseOfAction
        
        # 创建测试案由（劳动争议）
        cause = CauseOfAction.objects.create(
            code="test_labor",
            name="劳动争议",
        )
        
        request_data = FeeCalculationRequest(
            cause_of_action_id=cause.id,
        )
        
        mock_request = Mock()
        response = calculate_fee(mock_request, request_data)
        
        assert response.special_case_type == "labor_dispute"
        assert response.show_acceptance_fee is False
        assert response.show_half_fee is False
        assert response.show_payment_order_fee is False
        assert response.fixed_fee == 10

    def test_calculate_fee_without_cause_of_action_id(self):
        """测试不传递 cause_of_action_id 参数"""
        request_data = FeeCalculationRequest(
            target_amount=100000,
        )
        
        mock_request = Mock()
        response = calculate_fee(mock_request, request_data)
        
        # 普通案件，无特殊类型
        assert response.special_case_type is None
        assert response.acceptance_fee is not None
        assert response.show_payment_order_fee is False

    def test_calculate_fee_negative_amount_validation(self):
        """测试负数金额验证"""
        request_data = FeeCalculationRequest(
            target_amount=-100,
        )
        
        mock_request = Mock()
        
        with pytest.raises(ValidationException) as exc_info:
            calculate_fee(mock_request, request_data)
        
        assert "涉案金额不能为负数" in str(exc_info.value)

    def test_calculate_fee_negative_preservation_validation(self):
        """测试负数保全金额验证"""
        request_data = FeeCalculationRequest(
            preservation_amount=-100,
        )
        
        mock_request = Mock()
        
        with pytest.raises(ValidationException) as exc_info:
            calculate_fee(mock_request, request_data)
        
        assert "财产保全金额不能为负数" in str(exc_info.value)

    def test_calculate_fee_with_child_cause(self):
        """测试子案由继承父案由特殊类型"""
        # Requirements: 8.2
        from apps.core.models import CauseOfAction
        
        # 创建父案由（人格权纠纷）
        parent_cause = CauseOfAction.objects.create(
            code="9001",
            name="人格权纠纷",
        )
        
        # 创建子案由
        child_cause = CauseOfAction.objects.create(
            code="9001001",
            name="生命权纠纷",
            parent=parent_cause,
        )
        
        request_data = FeeCalculationRequest(
            cause_of_action_id=child_cause.id,
        )
        
        mock_request = Mock()
        response = calculate_fee(mock_request, request_data)
        
        # 子案由应该继承父案由的特殊类型
        assert response.special_case_type == "personality_rights"

