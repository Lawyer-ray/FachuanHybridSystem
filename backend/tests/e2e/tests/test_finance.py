"""
Django Admin E2E 测试 — 金融工具

验证 LPR 利率列表、LPR 计算器等金融工具页面。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_finance.py -v
    pytest tests/e2e/tests/test_finance.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 1. LPR 利率列表
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_lpr_rate_list(admin_page: Page, base_url: str) -> None:
    """访问 LPR 利率列表页，验证页面正常加载。"""
    response = admin_page.goto(f"{base_url}/admin/finance/lprrate/")
    assert response is not None
    assert response.status < 500  # No server error
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 2. LPR 计算器页面
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_lpr_calculator_page(admin_page: Page, base_url: str) -> None:
    """访问 LPR 计算器页面，验证页面正常加载。"""
    response = admin_page.goto(f"{base_url}/admin/finance/calculator/")
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 3. LPR 计算器表单
# ------------------------------------------------------------------

def test_lpr_calculator_has_form(admin_page: Page, base_url: str) -> None:
    """验证 LPR 计算器页面包含输入字段（本金、日期范围等）。"""
    admin_page.goto(f"{base_url}/admin/finance/calculator/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 计算器页面应包含 input 元素（本金、日期、利率等字段）
    inputs = admin_page.locator("input, select, textarea")
    assert inputs.count() > 0, "Calculator page should have form input fields"
