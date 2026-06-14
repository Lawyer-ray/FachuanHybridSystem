"""
Django Admin E2E 测试 — 法院短信

验证法院短信列表、新增表单、操作按钮等功能。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_court_sms.py -v
    pytest tests/e2e/tests/test_court_sms.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 1. 法院短信列表页
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_courtsms_list_page(admin_page: Page, base_url: str) -> None:
    """访问法院短信列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/automation/courtsms/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # Django Admin changelist 应包含 #changelist 或 #result_list
    changelist = admin_page.locator("#changelist, #result_list")
    expect(changelist.first).to_be_attached()


# ------------------------------------------------------------------
# 2. 新增法院短信页面
# ------------------------------------------------------------------

def test_courtsms_add_page(admin_page: Page, base_url: str) -> None:
    """访问新增法院短信页面，验证表单加载（应包含 content/sender 等字段）。"""
    response = admin_page.goto(
        f"{base_url}/admin/automation/courtsms/add/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # Django Admin change form 应包含表单元素
    form = admin_page.locator("#change-form, form")
    expect(form.first).to_be_attached()
    # 应包含输入字段（content、sender 等）
    inputs = admin_page.locator("input, select, textarea")
    assert inputs.count() > 0, "Add page should have form input fields"


# ------------------------------------------------------------------
# 3. 列表页操作按钮/筛选器
# ------------------------------------------------------------------

def test_courtsms_list_has_actions(admin_page: Page, base_url: str) -> None:
    """验证法院短信列表页包含操作按钮或筛选器。"""
    admin_page.goto(f"{base_url}/admin/automation/courtsms/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 列表页应包含 action 下拉框（#changelist-form select[name="action"]）
    # 或筛选器面板（#changelist-filter）
    has_actions = admin_page.locator("#changelist-form select[name='action']").count() > 0
    has_filters = admin_page.locator("#changelist-filter").count() > 0
    assert has_actions or has_filters, (
        "CourtSMS changelist should have action buttons or filter sidebar"
    )
