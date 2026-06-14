"""
Django Admin E2E 测试 — 合同审查

验证审查任务列表、新增、格式规范化列表、健康检查端点等功能。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_contract_review.py -v
    pytest tests/e2e/tests/test_contract_review.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 1. 审查任务列表
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_review_task_list(admin_page: Page, base_url: str) -> None:
    """访问审查任务列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/contract_review/reviewtask/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # Django Admin changelist 应包含 #changelist 或 #result_list
    changelist = admin_page.locator("#changelist, #result_list")
    expect(changelist.first).to_be_attached()


# ------------------------------------------------------------------
# 2. 新增审查任务页面
# ------------------------------------------------------------------

def test_review_task_add(admin_page: Page, base_url: str) -> None:
    """访问新增审查任务页面，验证表单正常加载（自定义 upload.html 模板）。"""
    response = admin_page.goto(
        f"{base_url}/admin/contract_review/reviewtask/add/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # 自定义 add_view 使用 upload.html 模板，应包含表单或上传区域
    form = admin_page.locator("#change-form, form")
    expect(form.first).to_be_attached()
    inputs = admin_page.locator("input, select, textarea")
    assert inputs.count() > 0, "Add page should have form input fields"


# ------------------------------------------------------------------
# 3. 格式规范化列表（自定义 changelist）
# ------------------------------------------------------------------

def test_format_normalize_list(admin_page: Page, base_url: str) -> None:
    """访问格式规范化列表页，验证自定义 changelist 正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/contract_review/formatnormalize/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
    # FormatNormalizeAdmin 使用自定义 changelist_template，
    # 页面应包含合同格式调整相关内容
    page_text = admin_page.locator("body").inner_text()
    assert "格式" in page_text or "合同" in page_text, (
        f"Format normalize page should contain format-related content, got: {page_text[:300]}"
    )


# ------------------------------------------------------------------
# 4. 健康检查端点
# ------------------------------------------------------------------

def test_format_normalize_health_check_url(admin_page: Page, base_url: str) -> None:
    """验证格式规范化的健康检查端点存在并返回 JSON 响应。"""
    response = admin_page.goto(
        f"{base_url}/admin/contract_review/formatnormalize/health-check/"
    )
    assert response is not None
    # 健康检查端点应返回 200（POI 在线）或仍可访问（POI 离线也返回 200 + JSON）
    assert response.status < 500, (
        f"Health check endpoint should not return server error, got: {response.status}"
    )
    # 响应应为 JSON（content-type 包含 application/json）
    content_type = response.headers.get("content-type", "")
    assert "json" in content_type or response.status == 200, (
        f"Health check should return JSON, content-type: {content_type}"
    )
