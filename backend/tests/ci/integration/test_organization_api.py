"""Organization API integration tests."""

from __future__ import annotations

import json

import pytest
from django.core.cache import cache

from apps.organization.models import AccountCredential, LawFirm, Lawyer, Team


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear cache before each test to avoid rate limiting."""
    cache.clear()
    yield


def _get_user_firm():
    """Get the law firm of the authenticated user."""
    user = Lawyer.objects.get(username="testuser")
    return user.law_firm


# ===================================================================
# Auth API
# ===================================================================


@pytest.mark.django_db
def test_login_success(api_client, law_firm):
    Lawyer.objects.create_user(username="logintest", password="testpass123", law_firm=law_firm)
    resp = api_client.post(
        "/api/v1/organization/login",
        data=json.dumps({"username": "logintest", "password": "testpass123"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["user"]["username"] == "logintest"


@pytest.mark.django_db
def test_login_wrong_password(api_client, law_firm):
    Lawyer.objects.create_user(username="wrongpw", password="correctpass", law_firm=law_firm)
    resp = api_client.post(
        "/api/v1/organization/login",
        data=json.dumps({"username": "wrongpw", "password": "wrongpass"}),
        content_type="application/json",
    )
    # May return 401 (auth failure), 429 (rate limit), or 200 (with success=False)
    assert resp.status_code in (200, 401, 429)
    # 缓存已清空、单次错误密码请求，实际走 AuthenticationError → 401 错误信封
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "INVALID_CREDENTIALS"
    assert body["message"] == "用户名或密码错误"
    assert "user" not in body  # 认证失败不得泄露用户数据


@pytest.mark.django_db
def test_logout(authenticated_client):
    resp = authenticated_client.post("/api/v1/organization/logout")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
def test_me(authenticated_client):
    resp = authenticated_client.get("/api/v1/organization/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testuser"


@pytest.mark.django_db
def test_register_first_user(api_client):
    resp = api_client.post(
        "/api/v1/organization/register",
        data=json.dumps({"username": "firstuser", "password": "testpass123", "real_name": "第一个用户"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@pytest.mark.django_db
def test_register_duplicate_username(api_client, law_firm):
    Lawyer.objects.create_user(username="dupuser", password="testpass123", law_firm=law_firm)
    resp = api_client.post(
        "/api/v1/organization/register",
        data=json.dumps({"username": "dupuser", "password": "testpass123"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    # 安全审计防枚举：模糊文案，不单独确认用户名存在性
    assert data["message"] == "注册信息无效或用户名已存在"


@pytest.mark.django_db
def test_register_short_password(api_client):
    """注册密码统一走 AUTH_PASSWORD_VALIDATORS（安全审计：密码策略统一）。"""
    resp = api_client.post(
        "/api/v1/organization/register",
        data=json.dumps({"username": "shortpwuser", "password": "123"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "密码" in data["message"]


@pytest.mark.django_db
def test_register_numeric_password_rejected(api_client):
    """满足长度但纯数字的密码同样被 NumericPasswordValidator 拒绝。"""
    resp = api_client.post(
        "/api/v1/organization/register",
        data=json.dumps({"username": "numpwuser", "password": "12345678"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "密码" in data["message"]


# ===================================================================
# LawFirm CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_lawfirms(authenticated_client):
    resp = authenticated_client.get("/api/v1/organization/lawfirms")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.django_db
def test_create_lawfirm(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/organization/lawfirms",
        data=json.dumps({"name": "新律所", "address": "北京市朝阳区"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "新律所"
    assert LawFirm.objects.filter(id=data["id"]).exists()


@pytest.mark.django_db
def test_get_lawfirm_detail(authenticated_client):
    firm = _get_user_firm()
    resp = authenticated_client.get(f"/api/v1/organization/lawfirms/{firm.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "测试律所"


@pytest.mark.django_db
def test_update_lawfirm(authenticated_client):
    firm = _get_user_firm()
    resp = authenticated_client.put(
        f"/api/v1/organization/lawfirms/{firm.id}",
        data=json.dumps({"name": "更新后的律所"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "更新后的律所"


@pytest.mark.django_db
def test_delete_lawfirm(authenticated_client):
    firm = LawFirm.objects.create(name="待删除律所")
    resp = authenticated_client.delete(f"/api/v1/organization/lawfirms/{firm.id}")
    # May return 403 if user doesn't own this firm
    assert resp.status_code in (200, 403)
    # 超管用户删除无律师/无团队的律所：200 + 真实落库删除
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert not LawFirm.objects.filter(id=firm.id).exists()


# ===================================================================
# Lawyer CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_lawyers(authenticated_client):
    resp = authenticated_client.get("/api/v1/organization/lawyers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.django_db
def test_create_lawyer(authenticated_client):
    firm = _get_user_firm()
    # 端点签名含 File 参数（license_pdf/avatar），契约要求 multipart 表单且
    # Schema 字段嵌套在 payload 键下（JSON 字符串）；平铺 JSON/表单一律 422
    resp = authenticated_client.post(
        "/api/v1/organization/lawyers",
        {
            "payload": json.dumps(
                {"username": "newlawyer", "password": "testpass123", "real_name": "新律师", "law_firm_id": firm.id}
            )
        },
    )
    # May return 422 if multipart form is required for file upload fields
    assert resp.status_code in (200, 422)
    # 正确契约编码下应创建成功
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "newlawyer"
    assert data["real_name"] == "新律师"
    created = Lawyer.objects.filter(username="newlawyer").first()
    assert created is not None  # 写操作真实落库
    assert created.law_firm_id == firm.id


@pytest.mark.django_db
def test_get_lawyer_detail(authenticated_client):
    user = Lawyer.objects.get(username="testuser")
    resp = authenticated_client.get(f"/api/v1/organization/lawyers/{user.id}")
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"


@pytest.mark.django_db
def test_update_lawyer(authenticated_client):
    user = Lawyer.objects.get(username="testuser")
    # 端点签名含 File 参数，契约要求 multipart 表单 + payload 嵌套 JSON 字符串
    # （test client 的 put(dict) 默认 urlencoded，须手工构造 multipart 体）
    from django.test.client import MULTIPART_CONTENT, encode_multipart

    multipart_body = encode_multipart(
        boundary="BoUnDaRyStRiNg",
        data={"payload": json.dumps({"real_name": "更新后的名字"})},
    )
    resp = authenticated_client.put(
        f"/api/v1/organization/lawyers/{user.id}",
        multipart_body,
        content_type=MULTIPART_CONTENT,
    )
    # May return 422 if multipart form is required
    assert resp.status_code in (200, 422)
    # 正确契约编码下应更新成功
    assert resp.status_code == 200
    assert resp.json()["real_name"] == "更新后的名字"
    user.refresh_from_db()
    assert user.real_name == "更新后的名字"  # 写操作真实落库


@pytest.mark.django_db
def test_delete_lawyer(authenticated_client):
    firm = _get_user_firm()
    lawyer = Lawyer.objects.create_user(username="deletelawyer", password="testpass123", law_firm=firm)
    resp = authenticated_client.delete(f"/api/v1/organization/lawyers/{lawyer.id}")
    assert resp.status_code in (200, 403)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert not Lawyer.objects.filter(id=lawyer.id).exists()


# ===================================================================
# Team CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_teams(authenticated_client):
    firm = _get_user_firm()
    Team.objects.create(name="测试团队", team_type="lawyer", law_firm=firm)
    resp = authenticated_client.get("/api/v1/organization/teams")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(t["name"] == "测试团队" for t in data)


@pytest.mark.django_db
def test_create_team(authenticated_client):
    firm = _get_user_firm()
    resp = authenticated_client.post(
        "/api/v1/organization/teams",
        data=json.dumps({"name": "新建团队", "team_type": "lawyer", "law_firm_id": firm.id}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "新建团队"
    assert Team.objects.filter(id=data["id"]).exists()


@pytest.mark.django_db
def test_get_team_detail(authenticated_client):
    firm = _get_user_firm()
    team = Team.objects.create(name="详情团队", team_type="lawyer", law_firm=firm)
    resp = authenticated_client.get(f"/api/v1/organization/teams/{team.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "详情团队"


@pytest.mark.django_db
def test_update_team(authenticated_client):
    firm = _get_user_firm()
    team = Team.objects.create(name="更新前", team_type="lawyer", law_firm=firm)
    resp = authenticated_client.put(
        f"/api/v1/organization/teams/{team.id}",
        data=json.dumps({"name": "更新后", "team_type": "biz", "law_firm_id": firm.id}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "更新后"


@pytest.mark.django_db
def test_delete_team(authenticated_client):
    firm = _get_user_firm()
    team = Team.objects.create(name="待删除", team_type="lawyer", law_firm=firm)
    resp = authenticated_client.delete(f"/api/v1/organization/teams/{team.id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert not Team.objects.filter(id=team.id).exists()


# ===================================================================
# Account Credential CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_credentials(authenticated_client):
    user = Lawyer.objects.get(username="testuser")
    AccountCredential.objects.create(
        lawyer=user, site_name="测试站点", account="test@example.com", password="encrypted"
    )
    resp = authenticated_client.get("/api/v1/organization/credentials")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.django_db
def test_create_credential(authenticated_client):
    user = Lawyer.objects.get(username="testuser")
    resp = authenticated_client.post(
        "/api/v1/organization/credentials",
        data=json.dumps(
            {"lawyer_id": user.id, "site_name": "新站点", "account": "new@example.com", "password": "secret"}
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["site_name"] == "新站点"


@pytest.mark.django_db
def test_get_credential_detail(authenticated_client):
    user = Lawyer.objects.get(username="testuser")
    cred = AccountCredential.objects.create(
        lawyer=user, site_name="详情站点", account="detail@example.com", password="enc"
    )
    resp = authenticated_client.get(f"/api/v1/organization/credentials/{cred.id}")
    assert resp.status_code == 200
    assert resp.json()["site_name"] == "详情站点"


@pytest.mark.django_db
def test_update_credential(authenticated_client):
    user = Lawyer.objects.get(username="testuser")
    cred = AccountCredential.objects.create(lawyer=user, site_name="更新前", account="up@example.com", password="enc")
    resp = authenticated_client.put(
        f"/api/v1/organization/credentials/{cred.id}",
        data=json.dumps({"site_name": "更新后", "account": "updated@example.com"}),
        content_type="application/json",
    )
    # May return 500 if password field is not directly updatable
    assert resp.status_code in (200, 500)
    # 服务层支持 site_name/account 直接更新：200 + 真实落库
    assert resp.status_code == 200
    data = resp.json()
    assert data["site_name"] == "更新后"  # 本用例创建的凭证锚点
    assert data["account"] == "updated@example.com"
    assert "password" not in data  # 凭证密文不得出现在响应中
    cred.refresh_from_db()
    assert cred.site_name == "更新后"
    assert cred.account == "updated@example.com"


@pytest.mark.django_db
def test_delete_credential(authenticated_client):
    user = Lawyer.objects.get(username="testuser")
    cred = AccountCredential.objects.create(lawyer=user, site_name="待删除", account="del@example.com", password="enc")
    resp = authenticated_client.delete(f"/api/v1/organization/credentials/{cred.id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert not AccountCredential.objects.filter(id=cred.id).exists()


# ===================================================================
# Password Reset
# ===================================================================


@pytest.mark.django_db
def test_password_reset_request_invalid_email(api_client):
    resp = api_client.post(
        "/api/v1/organization/password-reset/request",
        data=json.dumps({"email": "notanemail"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
