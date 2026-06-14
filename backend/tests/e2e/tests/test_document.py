"""
Django Admin E2E 测试 — 文档模板管理

验证文书模板列表、新增、文件夹模板、外部模板、代理事项规则等页面。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_document.py -v
    pytest tests/e2e/tests/test_document.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 1. 文书模板列表
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_document_template_list(admin_page: Page, base_url: str) -> None:
    """访问文书模板列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/documents/documenttemplate/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # Django Admin changelist 应包含 #changelist 或 #result_list
    changelist = admin_page.locator("#changelist, #result_list")
    expect(changelist.first).to_be_attached()


# ------------------------------------------------------------------
# 2. 新增文书模板页面
# ------------------------------------------------------------------

def test_document_template_add(admin_page: Page, base_url: str) -> None:
    """访问新增文书模板页面，验证表单正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/documents/documenttemplate/add/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # Django Admin change form 应包含表单元素
    form = admin_page.locator("#change-form, form")
    expect(form.first).to_be_attached()
    # 应包含输入字段
    inputs = admin_page.locator("input, select, textarea")
    assert inputs.count() > 0, "Add page should have form input fields"


# ------------------------------------------------------------------
# 3. 文件夹模板列表
# ------------------------------------------------------------------

def test_folder_template_list(admin_page: Page, base_url: str) -> None:
    """访问文件夹模板列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/documents/foldertemplate/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    changelist = admin_page.locator("#changelist, #result_list")
    expect(changelist.first).to_be_attached()


# ------------------------------------------------------------------
# 4. 外部模板列表
# ------------------------------------------------------------------

def test_external_template_list(admin_page: Page, base_url: str) -> None:
    """访问外部模板列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/documents/externaltemplate/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    changelist = admin_page.locator("#changelist, #result_list")
    expect(changelist.first).to_be_attached()


# ------------------------------------------------------------------
# 5. 代理事项规则列表
# ------------------------------------------------------------------

def test_proxy_matter_rule_list(admin_page: Page, base_url: str) -> None:
    """访问代理事项规则列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/documents/proxymatterrule/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    changelist = admin_page.locator("#changelist, #result_list")
    expect(changelist.first).to_be_attached()
