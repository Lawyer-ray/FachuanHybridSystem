"""
Django Admin E2E 测试 — 认证流程

验证登录、登出、未认证重定向等核心认证路径。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_auth.py -v
    pytest tests/e2e/tests/test_auth.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect

# 使用 conftest.py 中的 E2E_USERNAME / E2E_PASSWORD
E2E_USERNAME = "e2e_admin"
E2E_PASSWORD = "E2Etest@2026"


# ------------------------------------------------------------------
# 1. 登录页加载
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_login_page_loads(page: Page, base_url: str) -> None:
    """访问 /admin/login/，验证登录表单元素可见。"""
    page.goto(f"{base_url}/admin/login/")
    page.wait_for_load_state("networkidle")
    # 登录页有 CSS 滑入动画 + 登录/注册两个表单，选择可见的元素
    expect(page.locator("#id_username").first).to_be_visible(timeout=10000)
    expect(page.locator("#id_password").first).to_be_visible(timeout=10000)
    expect(page.locator("button[type='submit']").first).to_be_visible(timeout=10000)


# ------------------------------------------------------------------
# 2. 登录成功
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_login_success(page: Page, base_url: str, e2e_user) -> None:
    """填写正确凭据并提交，验证跳转到 admin 后台（日历页）。"""
    page.goto(f"{base_url}/admin/login/")
    page.wait_for_load_state("networkidle")
    page.locator("#id_username").first.fill(E2E_USERNAME)
    page.locator("#id_password").first.fill(E2E_PASSWORD)
    page.locator("button[type='submit']").first.click(force=True)
    # 登录成功后应跳转到 admin 区域
    page.wait_for_url("**/admin/**", timeout=15000)
    # 不应停留在登录页
    expect(page.locator("#id_username").first).not_to_be_visible()


# ------------------------------------------------------------------
# 3. 错误密码
# ------------------------------------------------------------------

def test_login_invalid_password(page: Page, base_url: str, e2e_user) -> None:
    """使用错误密码登录，验证错误提示出现。"""
    page.goto(f"{base_url}/admin/login/")
    page.wait_for_load_state("networkidle")
    page.locator("#id_username").first.fill(E2E_USERNAME)
    page.locator("#id_password").first.fill("wrong_password_123!")
    page.locator("button[type='submit']").first.click(force=True)
    # 等待页面响应
    page.wait_for_load_state("domcontentloaded")
    # Django admin 登录失败会显示 errornote 或 errorlist
    error = page.locator(".errornote, .errorlist")
    expect(error.first).to_be_visible(timeout=10000)


# ------------------------------------------------------------------
# 4. 登出
# ------------------------------------------------------------------

def test_logout(page: Page, admin_page: Page, base_url: str) -> None:
    """登录后访问登出页面，验证跳转回登录页。"""
    # admin_page 已登录（由 conftest fixture）
    admin_page.goto(f"{base_url}/admin/logout/")
    # Django admin 登出页有确认表单，点击确认按钮
    confirm_btn = admin_page.locator(
        "input[type='submit'], button[type='submit']"
    )
    if confirm_btn.count() > 0:
        confirm_btn.first.click()
        admin_page.wait_for_load_state("domcontentloaded")
    # 确认登出后能访问登录页（不再受保护）
    admin_page.goto(f"{base_url}/admin/login/")
    admin_page.wait_for_load_state("networkidle")
    expect(admin_page.locator("#id_username").first).to_be_visible(timeout=10000)


# ------------------------------------------------------------------
# 5. 未认证重定向到登录页
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_unauthenticated_redirect_to_login(page: Page, base_url: str) -> None:
    """未登录时访问 /admin/，验证重定向到登录页。"""
    page.goto(f"{base_url}/admin/")
    # 应被重定向到登录页
    page.wait_for_load_state("networkidle")
    expect(page.locator("#id_username").first).to_be_visible(timeout=10000)
    expect(page.locator("#id_password").first).to_be_visible(timeout=10000)


# ------------------------------------------------------------------
# 6. 登录后 /admin/ 重定向到日历页
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_admin_index_redirects_to_calendar(
    admin_page: Page, base_url: str
) -> None:
    """已登录用户访问 /admin/，验证重定向到提醒日历页面。"""
    admin_page.goto(f"{base_url}/admin/")
    # 等待重定向完成
    admin_page.wait_for_load_state("domcontentloaded")
    # URL 应包含 reminder 或 calendar 关键字
    url = admin_page.url
    assert "reminder" in url.lower() or "calendar" in url.lower(), (
        f"Expected URL to contain 'reminder' or 'calendar', got: {url}"
    )
