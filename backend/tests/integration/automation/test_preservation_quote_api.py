"""
财产保全询价 API 测试

测试 RESTful API 接口的功能：
- 创建询价任务
- 列表查询
- 获取详情
- 执行任务
"""

from decimal import Decimal

import pytest
from django.test import Client
from ninja_jwt.tokens import AccessToken

from apps.automation.models import PreservationQuote, QuoteStatus
from apps.organization.models import AccountCredential, LawFirm, Lawyer


@pytest.fixture
def api_client():
    """创建 API 客户端"""
    return Client()


@pytest.fixture
def auth_token(db):
    """创建认证 Token"""
    # 创建律所
    law_firm = LawFirm.objects.create(
        name="测试律所",
        social_credit_code="91440000TEST123456",
    )

    # 创建律师
    lawyer = Lawyer.objects.create(
        username="test_lawyer",
        real_name="测试律师",
        license_no="14401202012345678",
        law_firm=law_firm,
    )

    # 生成 JWT Token
    token = AccessToken.for_user(lawyer)
    return str(token)


@pytest.fixture
def credential(db):
    """创建测试凭证"""
    law_firm = LawFirm.objects.create(
        name="测试律所",
        social_credit_code="91440000TEST123456",
    )

    lawyer = Lawyer.objects.create(
        username="test_lawyer_cred",
        real_name="测试律师",
        law_firm=law_firm,
    )

    credential = AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="court_zxfw",
        account="test_account",
        password="test_password",
    )

    return credential


@pytest.mark.django_db
class TestPreservationQuoteAPI:
    """财产保全询价 API 测试"""

    def test_create_quote_success(self, api_client, auth_token, credential):
        """测试创建询价任务成功"""
        response = api_client.post(
            "/api/v1/automation/preservation-quotes",
            data={
                "preserve_amount": 100000.00,
                "corp_id": "440100",
                "category_id": "1",
                "credential_id": credential.id,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        assert response.status_code == 200
        data = response.json()

        # 验证响应数据
        assert float(data["preserve_amount"]) == 100000.00
        assert data["corp_id"] == "440100"
        assert data["category_id"] == "1"
        assert data["credential_id"] == credential.id
        assert data["status"] == QuoteStatus.PENDING
        assert data["total_companies"] == 0
        assert data["success_count"] == 0
        assert data["failed_count"] == 0

        # 验证数据库记录
        quote = PreservationQuote.objects.get(id=data["id"])
        assert quote.preserve_amount == Decimal("100000.00")
        assert quote.status == QuoteStatus.PENDING

    def test_create_quote_validation_error(self, api_client, auth_token, credential):
        """测试创建询价任务验证失败（Pydantic Schema 验证）"""
        # 保全金额为负数（Pydantic 会在 Schema 层验证）
        response = api_client.post(
            "/api/v1/automation/preservation-quotes",
            data={
                "preserve_amount": -1000.00,
                "corp_id": "440100",
                "category_id": "1",
                "credential_id": credential.id,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        # Pydantic validation errors return 422
        assert response.status_code == 422

    def test_create_quote_empty_corp_id(self, api_client, auth_token, credential):
        """测试创建询价任务 - 法院 ID 为空（Pydantic Schema 验证）"""
        response = api_client.post(
            "/api/v1/automation/preservation-quotes",
            data={
                "preserve_amount": 100000.00,
                "corp_id": "",
                "category_id": "1",
                "credential_id": credential.id,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        # Pydantic validation errors return 422
        assert response.status_code == 422

    def test_list_quotes_empty(self, api_client, auth_token):
        """测试列表查询 - 空列表"""
        response = api_client.get(
            "/api/v1/automation/preservation-quotes",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total_pages"] == 0
        assert len(data["items"]) == 0

    def test_list_quotes_with_data(self, api_client, auth_token, credential):
        """测试列表查询 - 有数据"""
        # 创建测试数据
        quote1 = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=credential.id,
            status=QuoteStatus.PENDING,
        )

        quote2 = PreservationQuote.objects.create(
            preserve_amount=Decimal("200000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=credential.id,
            status=QuoteStatus.SUCCESS,
            total_companies=5,
            success_count=5,
            failed_count=0,
        )

        response = api_client.get(
            "/api/v1/automation/preservation-quotes",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total_pages"] == 1
        assert len(data["items"]) == 2

        # 验证排序（最新的在前）
        assert data["items"][0]["id"] == quote2.id
        assert data["items"][1]["id"] == quote1.id

    def test_list_quotes_pagination(self, api_client, auth_token, credential):
        """测试列表查询 - 分页"""
        # 创建 25 条测试数据
        for i in range(25):
            PreservationQuote.objects.create(
                preserve_amount=Decimal("100000.00"),
                corp_id="440100",
                category_id="1",
                credential_id=credential.id,
                status=QuoteStatus.PENDING,
            )

        # 第一页
        response = api_client.get(
            "/api/v1/automation/preservation-quotes?page=1&page_size=10",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 25
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total_pages"] == 3
        assert len(data["items"]) == 10

        # 第二页
        response = api_client.get(
            "/api/v1/automation/preservation-quotes?page=2&page_size=10",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["page"] == 2
        assert len(data["items"]) == 10

        # 第三页
        response = api_client.get(
            "/api/v1/automation/preservation-quotes?page=3&page_size=10",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["page"] == 3
        assert len(data["items"]) == 5

    def test_list_quotes_filter_by_status(self, api_client, auth_token, credential):
        """测试列表查询 - 按状态筛选"""
        # 创建不同状态的任务
        PreservationQuote.objects.create(
            preserve_amount=Decimal("100000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=credential.id,
            status=QuoteStatus.PENDING,
        )

        PreservationQuote.objects.create(
            preserve_amount=Decimal("200000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=credential.id,
            status=QuoteStatus.SUCCESS,
        )

        PreservationQuote.objects.create(
            preserve_amount=Decimal("300000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=credential.id,
            status=QuoteStatus.SUCCESS,
        )

        # 筛选成功的任务
        response = api_client.get(
            "/api/v1/automation/preservation-quotes?status=success",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert all(item["status"] == QuoteStatus.SUCCESS for item in data["items"])

    def test_get_quote_success(self, api_client, auth_token, credential):
        """测试获取询价详情成功"""
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=credential.id,
            status=QuoteStatus.PENDING,
        )

        response = api_client.get(
            f"/api/v1/automation/preservation-quotes/{quote.id}",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == quote.id
        assert float(data["preserve_amount"]) == 100000.00
        assert data["corp_id"] == "440100"
        assert data["status"] == QuoteStatus.PENDING
        assert "quotes" in data
        assert isinstance(data["quotes"], list)

    def test_get_quote_not_found(self, api_client, auth_token):
        """测试获取询价详情 - 不存在"""
        response = api_client.get(
            "/api/v1/automation/preservation-quotes/99999",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["code"] == "NOT_FOUND"
        assert "errors" in data

    def test_api_requires_authentication(self, api_client):
        """测试 API 需要认证"""
        # 不带 Token 访问
        response = api_client.get("/api/v1/automation/preservation-quotes")

        assert response.status_code == 401

    def test_list_quotes_invalid_page(self, api_client, auth_token):
        """测试列表查询 - 无效页码（Service 层验证）"""
        response = api_client.get(
            "/api/v1/automation/preservation-quotes?page=0",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        # Service layer validation errors return 400 with BusinessError format
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["code"] == "VALIDATION_ERROR"
        assert "errors" in data
        assert "page" in data["errors"]

    def test_list_quotes_invalid_page_size(self, api_client, auth_token):
        """测试列表查询 - 无效每页数量（Service 层验证）"""
        response = api_client.get(
            "/api/v1/automation/preservation-quotes?page_size=200",
            HTTP_AUTHORIZATION=f"Bearer {auth_token}",
        )

        # Service layer validation errors return 400 with BusinessError format
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["code"] == "VALIDATION_ERROR"
        assert "errors" in data
        assert "page_size" in data["errors"]

    def test_execute_quote_not_found(self, api_client, auth_token):
        """测试执行询价任务 - 任务不存在

        Note: This test is skipped because async endpoints cannot be tested
        with Django's test client in a synchronous context.
        """
        pytest.skip("Async endpoint testing requires async test client")
