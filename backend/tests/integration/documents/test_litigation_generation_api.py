"""
诉讼文书生成 API 测试

测试起诉状和答辩状生成 API 的基本功能。
"""

from unittest.mock import Mock, patch

import pytest
from django.test import Client

from apps.documents.services.generation.schemas import ComplaintOutput, DefenseOutput, PartyInfo


@pytest.fixture
def api_client():
    """创建 Django 测试客户端"""
    return Client()


@pytest.fixture
def mock_complaint_output():
    """模拟起诉状输出"""
    return ComplaintOutput(
        title="民事起诉状",
        parties=[
            PartyInfo(name="张三", role="原告", id_number="", address=""),
            PartyInfo(name="李四", role="被告", id_number="", address=""),
        ],
        litigation_request="请求判令被告支付欠款10万元",
        facts_and_reasons="原告与被告于2023年签订借款合同...",
        evidence=["借款合同", "转账记录"],
    )


@pytest.fixture
def mock_defense_output():
    """模拟答辩状输出"""
    return DefenseOutput(
        title="民事答辩状",
        parties=[
            PartyInfo(name="张三", role="原告", id_number="", address=""),
            PartyInfo(name="李四", role="被告", id_number="", address=""),
        ],
        defense_opinion="原告诉讼请求不成立",
        defense_reasons="被告已经按约定履行还款义务...",
        evidence=["还款凭证", "银行流水"],
    )


class TestComplaintGenerationAPI:
    """起诉状生成 API 测试"""

    @patch("apps.documents.api.litigation_generation_api._get_litigation_generation_service")
    def test_generate_complaint_success(self, mock_get_service, api_client, mock_complaint_output):
        """测试成功生成起诉状"""
        # 模拟服务
        mock_service = Mock()
        mock_service.generate_complaint.return_value = mock_complaint_output
        mock_get_service.return_value = mock_service

        # 发送请求
        response = api_client.post(
            "/api/v1/documents/litigation/complaint/generate",
            data={
                "cause_of_action": "民间借贷纠纷",
                "plaintiff": "张三",
                "defendant": "李四",
                "litigation_request": "请求判令被告支付欠款10万元",
                "facts_and_reasons": "原告与被告于2023年签订借款合同...",
                "case_id": 123,
            },
            content_type="application/json",
        )

        # 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "duration_ms" in data
        assert data["data"]["title"] == "民事起诉状"

        # 验证服务被调用
        mock_service.generate_complaint.assert_called_once()

    @patch("apps.documents.api.litigation_generation_api._get_litigation_generation_service")
    def test_generate_complaint_validation_error(self, mock_get_service, api_client):
        """测试验证错误处理"""
        from apps.core.exceptions import ValidationException

        # 模拟服务抛出验证异常
        mock_service = Mock()
        mock_service.generate_complaint.side_effect = ValidationException(
            message="JSON 解析失败", code="JSON_PARSE_ERROR"
        )
        mock_get_service.return_value = mock_service

        # 发送请求
        response = api_client.post(
            "/api/v1/documents/litigation/complaint/generate",
            data={
                "cause_of_action": "民间借贷纠纷",
                "plaintiff": "张三",
                "defendant": "李四",
                "litigation_request": "请求判令被告支付欠款10万元",
                "facts_and_reasons": "原告与被告于2023年签订借款合同...",
            },
            content_type="application/json",
        )

        # 验证响应
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "error" in data
        assert data["error_code"] == "JSON_PARSE_ERROR"


class TestDefenseGenerationAPI:
    """答辩状生成 API 测试"""

    @patch("apps.documents.api.litigation_generation_api._get_litigation_generation_service")
    def test_generate_defense_success(self, mock_get_service, api_client, mock_defense_output):
        """测试成功生成答辩状"""
        # 模拟服务
        mock_service = Mock()
        mock_service.generate_defense.return_value = mock_defense_output
        mock_get_service.return_value = mock_service

        # 发送请求
        response = api_client.post(
            "/api/v1/documents/litigation/defense/generate",
            data={
                "cause_of_action": "民间借贷纠纷",
                "plaintiff": "张三",
                "defendant": "李四",
                "defense_opinion": "原告诉讼请求不成立",
                "defense_reasons": "被告已经按约定履行还款义务...",
                "case_id": 123,
            },
            content_type="application/json",
        )

        # 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "duration_ms" in data
        assert data["data"]["title"] == "民事答辩状"

        # 验证服务被调用
        mock_service.generate_defense.assert_called_once()

    @patch("apps.documents.api.litigation_generation_api._get_litigation_generation_service")
    def test_generate_defense_llm_timeout(self, mock_get_service, api_client):
        """测试 LLM 超时错误处理"""
        from apps.core.llm.exceptions import LLMTimeoutError

        # 模拟服务抛出超时异常
        mock_service = Mock()
        mock_service.generate_defense.side_effect = LLMTimeoutError(
            message="LLM 请求超时", code="LLM_TIMEOUT", timeout_seconds=30.0
        )
        mock_get_service.return_value = mock_service

        # 发送请求
        response = api_client.post(
            "/api/v1/documents/litigation/defense/generate",
            data={
                "cause_of_action": "民间借贷纠纷",
                "plaintiff": "张三",
                "defendant": "李四",
                "defense_opinion": "原告诉讼请求不成立",
                "defense_reasons": "被告已经按约定履行还款义务...",
            },
            content_type="application/json",
        )

        # 验证响应
        assert response.status_code == 504
        data = response.json()
        assert data["success"] is False
        assert "error" in data
        assert data["error_code"] == "LLM_TIMEOUT"
        assert data["timeout_seconds"] == 30.0
