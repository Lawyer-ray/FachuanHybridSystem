"""
Django Admin E2E 测试 — 导航结构

验证 Hub 页面、侧边栏、导航链接等 UI 导航功能。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_navigation.py -v
    pytest tests/e2e/tests/test_navigation.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 1. 办案 Hub 页面加载
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_case_handling_hub_loads(admin_page: Page, base_url: str) -> None:
    """访问 /admin/case-handling/，验证 Hub 页面渲染，包含办案卡片。"""
    admin_page.goto(f"{base_url}/admin/case-handling/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 页面主体应包含 case-handling-page 容器
    expect(admin_page.locator(".case-handling-page")).to_be_visible()
    # 应有至少一张 tool-card（当事人 / 合同 / 案件）
    cards = admin_page.locator(".tool-card")
    expect(cards.first).to_be_visible()
    assert cards.count() >= 1, "Hub page should contain at least one tool card"


# ------------------------------------------------------------------
# 2. 其他工具 Hub 页面加载
# ------------------------------------------------------------------

def test_other_tools_hub_loads(admin_page: Page, base_url: str) -> None:
    """访问 /admin/automation/other-tools/，验证工具聚合页渲染。"""
    admin_page.goto(f"{base_url}/admin/automation/other-tools/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 页面主体应包含 other-tools-page 容器
    expect(admin_page.locator(".other-tools-page")).to_be_visible()
    # 应有工具卡片
    cards = admin_page.locator(".tool-card")
    expect(cards.first).to_be_visible()


# ------------------------------------------------------------------
# 3. 侧边栏包含预期分区
# ------------------------------------------------------------------

def test_sidebar_has_expected_sections(admin_page: Page, base_url: str) -> None:
    """验证侧边栏包含虚拟菜单（办案、其他工具）以及 reminders。"""
    # 访问任意 admin 页面以触发侧边栏渲染
    admin_page.goto(f"{base_url}/admin/")
    admin_page.wait_for_load_state("domcontentloaded")
    sidebar = admin_page.locator("#nav-sidebar")
    # 侧边栏应在 DOM 中（可能隐藏在窄屏，但 DOM 应存在）
    expect(sidebar).to_be_attached()
    sidebar_text = sidebar.inner_text()
    # 虚拟「办案」菜单应出现
    assert "办案" in sidebar_text, (
        f"Sidebar should contain '办案', got: {sidebar_text[:200]}"
    )
    # reminders 区域应出现（提醒日历 / 重要日期提醒）
    assert "提醒" in sidebar_text, (
        f"Sidebar should contain '提醒', got: {sidebar_text[:200]}"
    )


# ------------------------------------------------------------------
# 4. Hub 页面卡片链接可导航
# ------------------------------------------------------------------

def test_case_handling_hub_links_work(
    admin_page: Page, base_url: str
) -> None:
    """在办案 Hub 页面点击一个子链接（如 客户/当事人），验证跳转正确。"""
    admin_page.goto(f"{base_url}/admin/case-handling/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 找到包含「当事人」的子链接
    link = admin_page.locator("a.child-link, a.tool-name").filter(
        has_text="当事人"
    ).first
    expect(link).to_be_visible()
    link.click()
    admin_page.wait_for_load_state("domcontentloaded")
    # 跳转后 URL 应包含 client（当事人管理的 app_label）
    url = admin_page.url
    assert "client" in url.lower(), (
        f"Expected URL to contain 'client' after clicking '当事人' link, got: {url}"
    )


# ------------------------------------------------------------------
# 5. 日历页为默认着陆页
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_calendar_is_default_landing(
    admin_page: Page, base_url: str
) -> None:
    """登录后直接访问 /admin/，验证最终 URL 包含 reminder 或 calendar。"""
    admin_page.goto(f"{base_url}/admin/")
    admin_page.wait_for_load_state("domcontentloaded")
    url = admin_page.url
    assert "reminder" in url.lower() or "calendar" in url.lower(), (
        f"Expected landing URL to contain 'reminder' or 'calendar', got: {url}"
    )
