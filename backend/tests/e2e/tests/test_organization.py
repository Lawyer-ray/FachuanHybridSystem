"""
Django Admin E2E 测试 — 组织管理

验证律师、律所、团队、账号凭证、用户、分组等组织管理页面。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_organization.py -v
    pytest tests/e2e/tests/test_organization.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 1. 律师列表
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_lawyer_list(admin_page: Page, base_url: str) -> None:
    """访问律师列表页，验证页面正常加载。"""
    response = admin_page.goto(f"{base_url}/admin/organization/lawyer/")
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 2. 律师添加页
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_lawyer_add_page(admin_page: Page, base_url: str) -> None:
    """访问律师添加页，验证表单包含用户名和密码字段。"""
    response = admin_page.goto(f"{base_url}/admin/organization/lawyer/add/")
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # 验证添加页面包含用户名和密码输入字段
    username_field = admin_page.locator("#id_username")
    expect(username_field).to_be_visible()
    password_field = admin_page.locator("#id_password1, #id_password")
    expect(password_field.first).to_be_visible()


# ------------------------------------------------------------------
# 3. 律所列表
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_lawfirm_list(admin_page: Page, base_url: str) -> None:
    """访问律所列表页，验证页面正常加载。"""
    response = admin_page.goto(f"{base_url}/admin/organization/lawfirm/")
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 4. 团队列表
# ------------------------------------------------------------------

def test_team_list(admin_page: Page, base_url: str) -> None:
    """访问团队列表页，验证页面正常加载。"""
    response = admin_page.goto(f"{base_url}/admin/organization/team/")
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 5. 账号凭证列表
# ------------------------------------------------------------------

def test_account_credential_list(admin_page: Page, base_url: str) -> None:
    """访问账号凭证列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/organization/accountcredential/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 6. 账号凭证添加页
# ------------------------------------------------------------------

def test_account_credential_add(admin_page: Page, base_url: str) -> None:
    """访问账号凭证添加页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/organization/accountcredential/add/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 7. 用户列表
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_user_list(admin_page: Page, base_url: str) -> None:
    """访问用户列表页，验证页面正常加载。"""
    response = admin_page.goto(f"{base_url}/admin/auth/user/")
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 8. 用户添加页
# ------------------------------------------------------------------

def test_user_add_page(admin_page: Page, base_url: str) -> None:
    """访问用户添加页，验证页面正常加载。"""
    response = admin_page.goto(f"{base_url}/admin/auth/user/add/")
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 9. 分组列表
# ------------------------------------------------------------------

def test_group_list(admin_page: Page, base_url: str) -> None:
    """访问分组列表页，验证页面正常加载。"""
    response = admin_page.goto(f"{base_url}/admin/auth/group/")
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
