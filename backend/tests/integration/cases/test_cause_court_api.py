"""
案由和法院数据 API 集成测试
"""

import pytest
from django.test import Client
from django.contrib.auth import get_user_model


@pytest.mark.django_db
class TestCauseCourtAPI:
    """案由和法院数据 API 集成测试"""

    def setup_method(self):
        """设置测试客户端"""
        self.client = Client()
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(username="admin", password="pass", email="a@example.com")
        self.client.force_login(self.user)

    def test_get_causes_api_endpoint_exists(self):
        """测试案由API端点存在"""
        response = self.client.get('/api/v1/cases/causes-data?case_type=civil')
        # API应该返回200或其他有效状态码，不应该是404
        assert response.status_code != 404

    def test_get_courts_api_endpoint_exists(self):
        """测试法院API端点存在"""
        response = self.client.get('/api/v1/cases/courts-data')
        # API应该返回200或其他有效状态码，不应该是404
        assert response.status_code != 404

    def test_causes_api_with_case_type_parameter(self):
        """测试案由API接受case_type参数"""
        response = self.client.get('/api/v1/cases/causes-data?case_type=civil')
        # 应该能够处理case_type参数，不返回500错误
        assert response.status_code != 500

    def test_causes_api_with_search_parameter(self):
        """测试案由API接受search参数"""
        response = self.client.get('/api/v1/cases/causes-data?case_type=civil&search=买卖')
        # 应该能够处理search参数，不返回500错误
        assert response.status_code != 500

    def test_courts_api_with_search_parameter(self):
        """测试法院API接受search参数"""
        response = self.client.get('/api/v1/cases/courts-data?search=顺德')
        # 应该能够处理search参数，不返回500错误
        assert response.status_code != 500

    def test_causes_api_returns_json(self):
        """测试案由API返回JSON格式"""
        response = self.client.get('/api/v1/cases/causes-data?case_type=civil')
        if response.status_code == 200:
            # 如果成功，应该返回JSON
            assert 'application/json' in response['Content-Type']

    def test_courts_api_returns_json(self):
        """测试法院API返回JSON格式"""
        response = self.client.get('/api/v1/cases/courts-data?search=法院')
        if response.status_code == 200:
            # 如果成功，应该返回JSON
            assert 'application/json' in response['Content-Type']

    def test_causes_api_can_search_by_code_and_returns_raw_name(self):
        from apps.core.models import CauseOfAction

        CauseOfAction.objects.create(code="9131", name="合同纠纷", case_type="civil", is_active=True, is_deprecated=False)
        resp = self.client.get("/api/v1/cases/causes-data?search=9131")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data and data[0]["code"] == "9131"
        assert data[0]["raw_name"] == "合同纠纷"

    def test_courts_api_can_search_by_code(self):
        from apps.core.models import Court

        Court.objects.create(code="Q25", name="丁青县人民法院", is_active=True)
        resp = self.client.get("/api/v1/cases/courts-data?search=Q25")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data and data[0]["id"] == "Q25"
