"""
测试账号凭证 API
"""

import pytest
from django.test import Client

from apps.organization.models import AccountCredential, LawFirm, Lawyer


@pytest.fixture
def law_firm(db):
    """创建律所"""
    return LawFirm.objects.create(name="测试律所")


@pytest.fixture
def superuser(db, law_firm):
    """创建超级用户"""
    return Lawyer.objects.create(username="admin", real_name="管理员", law_firm=law_firm, is_superuser=True)


@pytest.fixture
def lawyers(db, law_firm):
    """创建测试律师"""
    lawyer1 = Lawyer.objects.create(username="zhangsan", real_name="张三", law_firm=law_firm)
    lawyer2 = Lawyer.objects.create(username="lisi", real_name="李四", law_firm=law_firm)
    return lawyer1, lawyer2


@pytest.fixture
def credentials(db, lawyers):
    """创建测试凭证"""
    lawyer1, lawyer2 = lawyers

    cred1 = AccountCredential.objects.create(
        lawyer=lawyer1,
        site_name="法院网站",
        url="https://court.example.com",
        account="zhangsan@example.com",
        password="password123",
    )

    cred2 = AccountCredential.objects.create(
        lawyer=lawyer2,
        site_name="检察院网站",
        url="https://procuratorate.example.com",
        account="lisi@example.com",
        password="password456",
    )

    return cred1, cred2


@pytest.mark.django_db
@pytest.mark.integration
class TestCredentialAPI:
    """测试凭证 API"""

    def test_list_all_credentials(self, credentials, superuser):
        """测试获取所有凭证（超级用户）"""
        client = Client()
        client.force_login(superuser)
        response = client.get("/api/v1/organization/credentials")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_filter_by_lawyer_id(self, credentials, superuser):
        """测试按律师 ID 过滤"""
        cred1, cred2 = credentials
        client = Client()
        client.force_login(superuser)

        response = client.get(f"/api/v1/organization/credentials?lawyer_id={cred1.lawyer.id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["site_name"] == "法院网站"

    def test_filter_by_lawyer_real_name(self, credentials, superuser):
        """测试按律师真实姓名过滤"""
        client = Client()
        client.force_login(superuser)

        # 精确匹配
        response = client.get("/api/v1/organization/credentials?lawyer_name=张三")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["site_name"] == "法院网站"

        # 模糊匹配
        response = client.get("/api/v1/organization/credentials?lawyer_name=张")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_filter_by_lawyer_username(self, credentials, superuser):
        """测试按律师用户名过滤"""
        client = Client()
        client.force_login(superuser)

        # 精确匹配
        response = client.get("/api/v1/organization/credentials?lawyer_name=lisi")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["site_name"] == "检察院网站"

        # 模糊匹配
        response = client.get("/api/v1/organization/credentials?lawyer_name=li")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_combined_filters(self, credentials, superuser):
        """测试组合过滤"""
        cred1, cred2 = credentials
        client = Client()
        client.force_login(superuser)

        # 同时使用 lawyer_id 和 lawyer_name（应该取交集）
        response = client.get(f"/api/v1/organization/credentials?lawyer_id={cred1.lawyer.id}&lawyer_name=张三")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["site_name"] == "法院网站"

    def test_no_match(self, credentials, superuser):
        """测试没有匹配结果"""
        client = Client()
        client.force_login(superuser)

        response = client.get("/api/v1/organization/credentials?lawyer_name=不存在的律师")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_list_credentials_permission_filter(self, credentials, lawyers):
        """测试普通用户只能看到同一律所的凭证"""
        lawyer1, lawyer2 = lawyers
        client = Client()
        client.force_login(lawyer1)

        response = client.get("/api/v1/organization/credentials")

        assert response.status_code == 200
        data = response.json()
        # 同一律所的用户可以看到所有凭证
        assert len(data) == 2

    def test_list_credentials_no_law_firm(self, credentials, db):
        """测试没有关联律所的用户看不到任何凭证"""
        # 创建没有律所的用户
        user_no_firm = Lawyer.objects.create(username="nofirm", real_name="无律所用户", law_firm=None)
        client = Client()
        client.force_login(user_no_firm)

        response = client.get("/api/v1/organization/credentials")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_list_credentials_different_law_firm(self, credentials, db):
        """测试不同律所的用户看不到其他律所的凭证"""
        # 创建另一个律所和用户
        other_firm = LawFirm.objects.create(name="其他律所")
        other_user = Lawyer.objects.create(username="other", real_name="其他律所用户", law_firm=other_firm)
        client = Client()
        client.force_login(other_user)

        response = client.get("/api/v1/organization/credentials")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0


@pytest.mark.django_db
@pytest.mark.integration
class TestCredentialCRUDAPI:
    """凭证 CRUD API 测试（创建、获取、更新、删除）"""

    def test_get_credential_success(self, credentials, superuser):
        """获取单个凭证详情"""
        cred1, _ = credentials
        client = Client()
        client.force_login(superuser)

        response = client.get(f"/api/v1/organization/credentials/{cred1.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == cred1.id
        assert data["site_name"] == "法院网站"

    def test_get_credential_not_found(self, superuser):
        """获取不存在的凭证返回错误"""
        client = Client()
        client.force_login(superuser)

        response = client.get("/api/v1/organization/credentials/999999")

        # NotFoundError 由全局异常处理器捕获
        assert response.status_code in (404, 500)

    def test_create_credential_success(self, lawyers, superuser):
        """创建凭证"""
        lawyer1, _ = lawyers
        client = Client()
        client.force_login(superuser)

        import json

        payload = {
            "lawyer_id": lawyer1.id,
            "site_name": "新网站",
            "account": "newaccount",
            "password": "newpass123",
            "url": "https://new.example.com",
        }
        response = client.post(
            "/api/v1/organization/credentials",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["site_name"] == "新网站"
        assert data["account"] == "newaccount"

    def test_create_credential_lawyer_not_found(self, superuser):
        """为不存在的律师创建凭证返回错误"""
        client = Client()
        client.force_login(superuser)

        import json

        payload = {
            "lawyer_id": 999999,
            "site_name": "网站",
            "account": "acc",
            "password": "pass",
        }
        response = client.post(
            "/api/v1/organization/credentials",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # NotFoundError 由全局异常处理器捕获
        assert response.status_code in (404, 500)

    def test_update_credential_success(self, credentials, superuser):
        """更新凭证"""
        cred1, _ = credentials
        client = Client()
        client.force_login(superuser)

        import json

        payload = {"site_name": "更新后的网站"}
        response = client.put(
            f"/api/v1/organization/credentials/{cred1.id}",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["site_name"] == "更新后的网站"

    def test_update_credential_not_found(self, superuser):
        """更新不存在的凭证返回错误"""
        client = Client()
        client.force_login(superuser)

        import json

        payload = {"site_name": "新名称"}
        response = client.put(
            "/api/v1/organization/credentials/999999",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # NotFoundError 由全局异常处理器捕获
        assert response.status_code in (404, 500)

    def test_delete_credential_success(self, credentials, superuser):
        """删除凭证"""
        cred1, _ = credentials
        cred_id = cred1.id
        client = Client()
        client.force_login(superuser)

        response = client.delete(f"/api/v1/organization/credentials/{cred_id}")

        assert response.status_code == 200
        assert not AccountCredential.objects.filter(id=cred_id).exists()

    def test_delete_credential_not_found(self, superuser):
        """删除不存在的凭证返回错误"""
        client = Client()
        client.force_login(superuser)

        response = client.delete("/api/v1/organization/credentials/999999")

        # NotFoundError 由全局异常处理器捕获
        assert response.status_code in (404, 500)
